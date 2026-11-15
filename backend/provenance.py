"""Load and verify the checked-in terrain provenance manifest."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any

import rasterio
from PIL import Image

MANIFEST_VERSION = 1
MANIFEST_FILENAME = "provenance.json"
DEFAULT_PROCESSED_DIR = Path(__file__).resolve().parent / "data" / "processed"


class ProvenanceError(RuntimeError):
    """The provenance manifest is missing or invalid."""


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as manifest_file:
            manifest = json.load(manifest_file)
    except FileNotFoundError as error:
        raise ProvenanceError(f"Provenance manifest not found: {path.name}") from error
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProvenanceError(
            f"Unable to read provenance manifest: {error}"
        ) from error

    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest: Any) -> None:
    if not isinstance(manifest, dict):
        raise ProvenanceError("Provenance manifest root must be a JSON object.")
    if manifest.get("schema_version") != MANIFEST_VERSION:
        raise ProvenanceError(
            f"Unsupported provenance manifest schema_version: "
            f"{manifest.get('schema_version', 'unknown')}."
        )
    if not isinstance(manifest.get("manifest_id"), str):
        raise ProvenanceError("Provenance manifest is missing manifest_id.")
    source = manifest.get("source_dataset")
    if not isinstance(source, dict) or not isinstance(
        source.get("original_asset"), dict
    ):
        raise ProvenanceError("Provenance manifest is missing source asset metadata.")
    if not isinstance(manifest.get("processing_pipeline"), list):
        raise ProvenanceError("Provenance manifest is missing processing_pipeline.")

    products = manifest.get("derived_products")
    if not isinstance(products, list) or not products:
        raise ProvenanceError("Provenance manifest is missing derived_products.")

    seen_filenames: set[str] = set()
    seen_record_ids: set[str] = set()
    for product in products:
        if not isinstance(product, dict):
            raise ProvenanceError("Each derived product must be an object.")
        filename = product.get("filename")
        record_id = product.get("record_id")
        checksum = product.get("checksum")
        if (
            not isinstance(filename, str)
            or not filename
            or Path(filename).name != filename
        ):
            raise ProvenanceError("Product filenames must be safe base filenames.")
        if not isinstance(record_id, str) or not record_id:
            raise ProvenanceError("Each derived product needs a record_id.")
        if filename in seen_filenames or record_id in seen_record_ids:
            raise ProvenanceError("Product filenames and record_ids must be unique.")
        if not isinstance(checksum, dict):
            raise ProvenanceError(f"Product {filename} is missing checksum metadata.")
        digest = checksum.get("sha256")
        if digest is not None and (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ProvenanceError(
                f"Product {filename} has an invalid SHA-256 checksum."
            )
        seen_filenames.add(filename)
        seen_record_ids.add(record_id)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as product_file:
        for chunk in iter(lambda: product_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _metadata_matches(product_path: Path, product: dict[str, Any]) -> bool | None:
    expected = product.get("raster_metadata")
    if not isinstance(expected, dict):
        return None

    media_type = product.get("media_type")
    if media_type == "image/tiff":
        try:
            with rasterio.open(product_path) as raster:
                transform = expected.get("transform")
                if not isinstance(transform, list):
                    return False
                return (
                    raster.width == expected.get("width")
                    and raster.height == expected.get("height")
                    and raster.count == expected.get("band_count")
                    and list(raster.dtypes) == expected.get("data_types")
                    and raster.nodata == expected.get("nodata")
                    and raster.crs is not None
                    and raster.crs == rasterio.crs.CRS.from_wkt(
                        expected.get("crs_wkt", "")
                    )
                    and len(transform) == len(tuple(raster.transform))
                    and all(
                        math.isclose(actual, wanted, rel_tol=0, abs_tol=1e-9)
                        for actual, wanted in zip(
                            tuple(raster.transform),
                            transform,
                        )
                    )
                )
        except (OSError, ValueError, rasterio.errors.RasterioError):
            return False

    if media_type == "image/png":
        try:
            with Image.open(product_path) as image:
                return (
                    image.size
                    == (expected.get("width"), expected.get("height"))
                    and image.mode == expected.get("mode")
                )
        except (OSError, ValueError):
            return False

    return None


def verify_product(product: dict[str, Any], product_dir: Path) -> dict[str, Any]:
    filename = product["filename"]
    product_path = product_dir / filename
    if not product_path.is_file():
        return {
            "record_id": product["record_id"],
            "filename": filename,
            "available": False,
            "verification_status": "missing",
            "checksum_status": "not_checked",
            "metadata_status": "not_checked",
            "expected_sha256": product["checksum"].get("sha256"),
            "actual_sha256": None,
            "size_bytes": None,
        }

    expected_sha256 = product["checksum"].get("sha256")
    try:
        actual_sha256 = sha256_file(product_path) if expected_sha256 else None
        checksum_status = (
            "not_provided"
            if expected_sha256 is None
            else "verified"
            if actual_sha256 == expected_sha256
            else "mismatch"
        )
        metadata_matches = _metadata_matches(product_path, product)
    except OSError as error:
        return {
            "record_id": product["record_id"],
            "filename": filename,
            "available": True,
            "verification_status": "unreadable",
            "checksum_status": "unreadable",
            "metadata_status": "unreadable",
            "expected_sha256": expected_sha256,
            "actual_sha256": None,
            "size_bytes": product_path.stat().st_size,
            "error": str(error),
        }

    metadata_status = (
        "not_applicable"
        if metadata_matches is None
        else "verified"
        if metadata_matches
        else "mismatch"
    )
    checks_pass = (
        checksum_status in {"verified", "not_provided"}
        and metadata_status in {"verified", "not_applicable"}
    )
    return {
        "record_id": product["record_id"],
        "filename": filename,
        "available": True,
        "verification_status": "verified" if checks_pass else "mismatch",
        "checksum_status": checksum_status,
        "metadata_status": metadata_status,
        "expected_sha256": expected_sha256,
        "actual_sha256": actual_sha256,
        "size_bytes": product_path.stat().st_size,
    }


def build_provenance_report(
    manifest_path: Path = DEFAULT_PROCESSED_DIR / MANIFEST_FILENAME,
    product_dir: Path = DEFAULT_PROCESSED_DIR,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    product_status = [
        verify_product(product, product_dir)
        for product in manifest["derived_products"]
    ]
    return {
        "manifest": manifest,
        "manifest_status": "loaded",
        "source_asset_status": {
            "filename": manifest["source_dataset"]["original_asset"]["filename"],
            "availability": manifest["source_dataset"]["original_asset"][
                "availability_at_capture"
            ],
            "checksum_status": manifest["source_dataset"]["original_asset"][
                "checksum"
            ]["status"],
        },
        "product_verification": product_status,
    }


def route_provenance_references(
    manifest_path: Path = DEFAULT_PROCESSED_DIR / MANIFEST_FILENAME,
) -> dict[str, Any]:
    try:
        manifest = load_manifest(manifest_path)
    except ProvenanceError as error:
        return {
            "status": "unavailable",
            "manifest_id": "unknown",
            "reason": str(error),
        }

    products_by_id = {
        product["record_id"]: product
        for product in manifest["derived_products"]
    }
    return {
        "status": "referenced",
        "manifest_id": manifest["manifest_id"],
        "source_dataset_record_id": manifest["source_dataset"]["record_id"],
        "slope_product": products_by_id.get("jezero-slope-raster", {}).get(
            "filename", "unknown"
        ),
        "classification_product": products_by_id.get(
            "jezero-traversability-5-12-18-raster", {}
        ).get("filename", "unknown"),
        "route_algorithm": "8-connected A* over source slope raster",
        "checksum_verification": "not run during route planning",
    }


def main() -> int:
    try:
        report = build_provenance_report()
    except ProvenanceError as error:
        print(str(error), file=sys.stderr)
        return 1

    print(json.dumps(report, indent=2))
    return int(
        any(
            product["verification_status"] != "verified"
            for product in report["product_verification"]
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
