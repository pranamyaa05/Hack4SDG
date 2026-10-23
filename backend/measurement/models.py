from __future__ import annotations

from typing import Literal
from uuid import uuid4

from pydantic import Field, model_validator

from backend.contracts import Contract, Measurement

Dimension = Literal[
    "handle_width",
    "handle_thickness",
    "covered_length",
    "hole_spacing",
    "hole_diameter",
]


class Observation(Contract):
    id: str = Field(default_factory=lambda: str(uuid4()))
    dimension: Dimension
    value_mm: float = Field(gt=0, le=1000)
    sigma_mm: float = Field(gt=0, le=1000)
    method: Literal["photo_on_sheet", "paper_strip", "manual_ruler", "manual_caliper"]
    evidence_ids: list[str] = Field(min_length=1)
    confirmed_by_user: bool
    notes: list[str] = Field(default_factory=list)


class Calibration(Contract):
    id: str = Field(default_factory=lambda: str(uuid4()))
    sheet_version: Literal["1"] = "1"
    marker_ids: list[int]
    homography: list[list[float]]
    reprojection_rms_mm: float
    leave_one_marker_out_rms_mm: float
    pixels_per_mm: Literal[10] = 10
    quality: Literal["good", "acceptable"]
    scale_check_passed: Literal[True] = True
    coverage_mm: list[list[float]]
    image_width: int
    image_height: int
    warnings: list[str]


class Workspace(Contract):
    mode: Literal["manual", "photo"]
    calibration: Calibration | None = None
    selections: dict = Field(default_factory=dict)
    observations: list[Observation] = Field(default_factory=list)
    measurements: dict[str, Measurement] = Field(default_factory=dict)
    conflicts: dict[str, list[str]] = Field(default_factory=dict)
    assumptions: list[str] = Field(
        default_factory=lambda: [
            "Uncertainty floors and agreement thresholds are provisional; validate with caliper reference data.",
            "Repeated readings using the same method do not constitute independent cross-checks.",
            "Photo scale describes the sheet plane; object height and lens distortion can add bias.",
        ]
    )


class RevisionBody(Contract):
    expected_revision: int = Field(ge=0)


class StartRequest(RevisionBody):
    mode: Literal["manual", "photo"]


class ManualRequest(RevisionBody):
    dimension: Dimension
    value_mm: float = Field(gt=0, le=1000)
    instrument: Literal["manual_ruler", "manual_caliper"]
    resolution_mm: float = Field(gt=0, le=10)
    uncertainty_mm: float | None = Field(default=None, gt=0, le=100)
    confirmed_by_user: Literal[True]


class Point(Contract):
    x_mm: float = Field(ge=0, le=210)
    y_mm: float = Field(ge=0, le=297)


class RegionRequest(RevisionBody):
    calibration_id: str
    start: Point
    end: Point
    half_width_mm: float = Field(gt=1, le=40)
    confirmed_by_user: Literal[True]
    object_height_bound_mm: float = Field(gt=0, le=50)
    camera_distance_lower_bound_mm: float = Field(ge=250, le=3000)


class HoleRequest(RevisionBody):
    calibration_id: str
    first: Point
    second: Point
    coplanar_confirmed: Literal[True]
    confirmed_by_user: Literal[True]
    click_uncertainty_mm: float = Field(ge=0.25, le=5, default=0.5)


class PerimeterRequest(RevisionBody):
    perimeter_mm: float = Field(gt=0, le=500)
    perimeter_uncertainty_mm: float = Field(ge=0.25, le=10, default=1)
    shape: Literal["ellipse", "rounded_rectangle"]
    corner_radius_mm: float | None = Field(default=None, ge=0, le=20)
    corner_radius_uncertainty_mm: float = Field(ge=0.1, le=5, default=0.5)
    confirmed_by_user: Literal[True]

    @model_validator(mode="after")
    def corner_required(self):
        if self.shape == "rounded_rectangle" and self.corner_radius_mm is None:
            raise ValueError(
                "Confirm a corner-radius estimate for a rounded rectangle, or enter thickness manually"
            )
        return self
