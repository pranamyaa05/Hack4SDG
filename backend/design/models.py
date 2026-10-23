from math import hypot
from typing import Literal

from pydantic import Field, model_validator

from backend.contracts import Contract, DesignSpec


class Mounting(Contract):
    method: Literal["through_bolt_and_nut"] = "through_bolt_and_nut"
    bolt_diameter_mm: float = Field(gt=0, le=8)
    face_thickness_mm: float = Field(gt=0, le=50)
    bolt_length_mm: float = Field(gt=0, le=150)
    nut_height_mm: float = Field(gt=0, le=15)
    confirmed_by_user: Literal[True]


class ManufacturingSpec(DesignSpec):
    schema_version: Literal["1.1.0"] = "1.1.0"
    variant: Literal["compact", "balanced", "large"]
    material: Literal["TPU", "PETG", "PLA"]
    cross_section: Literal["round", "oval", "flat", "unknown"]
    mounting: Mounting | None = None

    @model_validator(mode="after")
    def fabrication_gate(self):
        p = self.parameters
        if self.track.value == "adapt":
            if self.cross_section not in {"round", "oval", "flat"}:
                raise ValueError(
                    "Confirm the handle cross-section before generating CAD"
                )
            if (
                self.material != "TPU"
                and self.verification_level != "physically_verified"
            ):
                raise ValueError(
                    "Unverified sleeves currently require flexible TPU; rigid-material fit needs physical validation"
                )
            inner_radius = (
                hypot(p.inner_width_mm, p.inner_thickness_mm)
                if self.cross_section == "flat"
                else max(p.inner_width_mm, p.inner_thickness_mm)
            ) / 2
            if (
                min(p.outer_width_mm, p.outer_thickness_mm) / 2 - inner_radius
                < p.wall_min_mm
            ):
                raise ValueError("Conservative minimum-wall constraint failed")
            if self.cross_section == "round":
                w = self.measurements["handle_width"]
                t = self.measurements["handle_thickness"]
                if abs(w.value_mm - t.value_mm) > min(
                    1.5, 2.5 * hypot(w.sigma_mm, t.sigma_mm)
                ):
                    raise ValueError(
                        "Width and thickness disagree with a round cross-section; confirm oval or re-measure"
                    )
        else:
            if self.material == "TPU" or self.mounting is None:
                raise ValueError(
                    "Drawer pulls require a rigid material and confirmed through-bolt mounting"
                )
            if p.bar_width_mm < p.boss_diameter_mm:
                raise ValueError("Bar width must encompass the mounting bosses")
            m = self.mounting
            if m.bolt_diameter_mm + 0.2 > p.hole_diameter_mm:
                raise ValueError(
                    "Measured mounting hole leaves insufficient bolt clearance"
                )
            if (
                m.bolt_length_mm
                < m.face_thickness_mm
                + p.standoff_mm
                + p.bar_height_mm
                + m.nut_height_mm
                + 2
            ):
                raise ValueError(
                    "Bolt length must accommodate drawer face, stand-off, bar, nut, and 2 mm protrusion allowance"
                )
        return self


class GenerateRequest(Contract):
    expected_revision: int = Field(ge=0)
    variant: Literal["compact", "balanced", "large"] = "balanced"
    material: Literal["TPU", "PETG", "PLA"] = "TPU"
    mounting: Mounting | None = None
    parent_design_id: str | None = None


class FeedbackRequest(Contract):
    outcome: Literal["fits", "too_tight", "too_loose", "not_tested"]
    kept_in_use: bool = False
    notes: str = Field(default="", max_length=1000)
    confirmed_by_user: Literal[True]


class RefitRequest(Contract):
    consent: Literal[True]
