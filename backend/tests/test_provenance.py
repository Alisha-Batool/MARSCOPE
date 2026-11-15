import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from backend import main
from backend.provenance import (
    ProvenanceError,
    build_provenance_report,
    load_manifest,
    verify_product,
)


def make_manifest(product_filename: str, checksum: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "manifest_id": "test-provenance",
        "source_dataset": {
            "record_id": "test-source",
            "original_asset": {
                "filename": "source.tif",
                "availability_at_capture": "not_packaged",
                "checksum": {"status": "not_computed"},
            },
        },
        "processing_pipeline": [],
        "derived_products": [
            {
                "record_id": "test-product",
                "filename": product_filename,
                "media_type": "application/octet-stream",
                "checksum": {"sha256": checksum},
            }
        ],
    }


class ProvenanceTests(unittest.TestCase):
    def test_loads_project_manifest_and_records_unverified_source_checksum(self):
        manifest_path = (
            Path(__file__).resolve().parents[1]
            / "data"
            / "processed"
            / "provenance.json"
        )

        manifest = load_manifest(manifest_path)

        self.assertEqual(manifest["manifest_id"], "ares-jezero-terrain-provenance-v1")
        self.assertEqual(
            manifest["source_dataset"]["original_asset"]["checksum"]["status"],
            "not_computed",
        )
        self.assertEqual(len(manifest["derived_products"]), 5)

    def test_missing_manifest_is_explicit(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(ProvenanceError, "not found"):
                load_manifest(Path(temporary_directory) / "missing.json")

    def test_invalid_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            manifest_path = Path(temporary_directory) / "invalid.json"
            manifest_path.write_text('{"schema_version": 7}', encoding="utf-8")

            with self.assertRaisesRegex(ProvenanceError, "Unsupported"):
                load_manifest(manifest_path)

    def test_product_checksum_is_verified_and_mismatch_is_reported(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            product_dir = Path(temporary_directory)
            product_path = product_dir / "product.bin"
            product_path.write_bytes(b"first content")
            expected = hashlib.sha256(b"first content").hexdigest()
            product = make_manifest("product.bin", expected)["derived_products"][0]

            verified = verify_product(product, product_dir)
            self.assertEqual(verified["verification_status"], "verified")
            self.assertEqual(verified["checksum_status"], "verified")

            product_path.write_bytes(b"changed content")
            mismatch = verify_product(product, product_dir)
            self.assertEqual(mismatch["verification_status"], "mismatch")
            self.assertEqual(mismatch["checksum_status"], "mismatch")

    def test_missing_product_is_reported_without_failing_manifest_load(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            product = make_manifest("missing.bin", "a" * 64)["derived_products"][0]

            status = verify_product(product, Path(temporary_directory))

            self.assertFalse(status["available"])
            self.assertEqual(status["verification_status"], "missing")

    def test_provenance_api_response_includes_manifest_and_product_status(self):
        report = main.provenance()

        self.assertEqual(report["manifest_status"], "loaded")
        self.assertEqual(
            report["manifest"]["manifest_id"],
            "ares-jezero-terrain-provenance-v1",
        )
        statuses = {
            product["record_id"]: product
            for product in report["product_verification"]
        }
        self.assertEqual(
            statuses["jezero-slope-raster"]["verification_status"],
            "verified",
        )
        self.assertEqual(
            statuses["jezero-traversability-5-12-18-raster"][
                "verification_status"
            ],
            "verified",
        )
        self.assertEqual(
            report["source_asset_status"]["checksum_status"],
            "not_computed",
        )

    def test_provenance_api_returns_service_unavailable_for_missing_manifest(self):
        with patch.object(
            main,
            "PROVENANCE_FILE",
            Path("missing-provenance.json"),
        ):
            with self.assertRaises(HTTPException) as raised:
                main.provenance()

        self.assertEqual(raised.exception.status_code, 503)

    def test_terrain_summary_adds_provenance_without_removing_existing_fields(self):
        summary = main.terrain_summary()

        self.assertIn("source", summary)
        self.assertIn("mean_slope_degrees", summary)
        self.assertEqual(
            summary["provenance"]["manifest_id"],
            "ares-jezero-terrain-provenance-v1",
        )

    def test_health_reports_route_planning_capability(self):
        health = main.health()

        self.assertEqual(health["status"], "ok")
        self.assertTrue(health["route_planning_available"])

    def test_missing_slope_raster_is_reported_as_unavailable(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            missing_raster = Path(temporary_directory) / "missing.tif"
            with patch.object(main, "SLOPE_FILE", missing_raster):
                health = main.health()
                with self.assertRaises(HTTPException) as raised:
                    main.slope_metadata()

        self.assertEqual(health["data_status"], "not_connected")
        self.assertEqual(raised.exception.status_code, 404)

    def test_traversability_endpoint_rebuilds_missing_classification_product(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory)
            with patch.object(main, "DATA_DIR", output_dir):
                response = main.jezero_traversability(
                    low_slope_max_degrees=5,
                    moderate_slope_max_degrees=12,
                    high_slope_max_degrees=18,
                )

            self.assertTrue(
                (output_dir / "jezero_traversability_5_12_18.tif").is_file()
            )
            self.assertTrue(
                (output_dir / "jezero_traversability_5_12_18_preview.png").is_file()
            )
            self.assertEqual(response.width, 851)
            self.assertEqual(response.height, 891)

    def test_traversability_response_accepts_nested_provenance_metadata(self):
        response = main.jezero_traversability(
            low_slope_max_degrees=5,
            moderate_slope_max_degrees=12,
            high_slope_max_degrees=18,
        )
        payload = response.model_dump()

        self.assertEqual(
            payload["analysis_metadata"]["provenance"]["manifest_id"],
            "ares-jezero-terrain-provenance-v1",
        )


if __name__ == "__main__":
    unittest.main()
