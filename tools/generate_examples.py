"""Generate explicitly illustrative packages, never physical validation results."""

import json
from pathlib import Path

from backend.design.models import ManufacturingSpec
from backend.design.package import build_package


def main():
    root = Path(__file__).resolve().parent.parent
    folder = root / "sample_data" / "generated_examples"
    folder.mkdir(exist_ok=True)
    for index, track in enumerate(("adapt", "repair"), 1):
        data = json.loads(
            (root / f"sample_data/{track}_example/design_spec.json").read_text(
                encoding="utf-8"
            )
        )
        data.update(
            schema_version="1.1.0",
            design_id=f"00000000-0000-4000-8000-{index:012d}",
            example=True,
            variant="balanced",
            material="TPU" if track == "adapt" else "PETG",
            cross_section="oval",
        )
        if track == "repair":
            data["parameters"]["bar_width_mm"] = 12
            data["mounting"] = dict(
                bolt_diameter_mm=3,
                face_thickness_mm=16,
                bolt_length_mm=70,
                nut_height_mm=3,
                confirmed_by_user=True,
            )
        spec = ManufacturingSpec.model_validate(data)
        if (folder / spec.design_id).exists():
            print(f"{track}: illustrative package already exists; left unchanged")
            continue
        build_package(spec, folder)
        print(
            f"{track}: {folder / spec.design_id}/package.zip (EXAMPLE, not physically measured)"
        )


if __name__ == "__main__":
    main()
