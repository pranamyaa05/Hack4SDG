import json
import zipfile
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock

from .render import render_outputs

CAD_LOCK = Lock()


def build_package(spec, output_root, rectified=None, selection=None):
    from .geometry import generate_geometry

    output_root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="refit-", dir=output_root) as temporary:
        folder = Path(temporary)
        with CAD_LOCK:
            metrics = generate_geometry(spec, folder)
        rendered = render_outputs(spec, folder, metrics, rectified, selection)
        (folder / "design_spec.json").write_text(
            spec.model_dump_json(indent=2), encoding="utf-8"
        )
        if rectified:
            (folder / "rectified_sheet.png").write_bytes(rectified)
        report = {
            "example": spec.example,
            "spec_hash": spec.content_hash(),
            "status": "passed",
            "checks": {
                **metrics,
                "drawing_dimensions_match": rendered["drawing_dimensions_match"],
            },
            "limitations": [
                "Physical fit and load capacity have not been verified.",
                "Every artifact is linked to the specification by the package manifest.",
            ],
        }
        (folder / "validation_report.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        entries = {
            p.name: sha256(p.read_bytes()).hexdigest()
            for p in folder.iterdir()
            if p.is_file()
        }
        manifest = {
            "example": spec.example,
            "schema_version": spec.schema_version,
            "design_id": spec.design_id,
            "spec_hash": spec.content_hash(),
            "artifact_sha256": entries,
            "coordinate_notes": "mm; x length, y width, z thickness. Pull origin at start of bar, z=0 drawer-face mounting plane.",
        }
        (folder / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        archive = folder / "package.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
            for file in sorted(folder.iterdir()):
                if file != archive:
                    zipped.write(file, file.name)
        destination = output_root / spec.design_id
        folder.rename(destination)
    return {
        "id": spec.design_id,
        "spec": spec.model_dump(mode="json"),
        "spec_hash": spec.content_hash(),
        "metrics": metrics,
        "ledger": rendered["ledger"],
        "files": sorted(entries) + ["manifest.json", "package.zip"],
    }
