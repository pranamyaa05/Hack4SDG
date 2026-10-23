"""Versioned contracts shared by Adapt, Repair, and the mesh integration."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Track(str, Enum):
    ADAPT = "adapt"
    REPAIR = "repair"


class State(str, Enum):
    CREATED = "created"
    ANALYZING = "analyzing"
    CONFIRMING = "confirming_object"
    CLARIFYING = "clarifying"
    CALIBRATING = "calibrating"
    MEASURING = "measuring"
    RECOMMENDING = "recommending"
    SELECTED = "design_selected"
    GENERATING = "generating"
    READY = "ready"
    NEEDS_INFO = "needs_more_information"
    FAILED = "failed"


class SessionCreate(Contract):
    track: Track
    consent: Literal[True]
    language: str = Field(default="en", pattern=r"^[a-z]{2,3}(-[A-Za-z]{2,4})?$")


class Session(SessionCreate):
    id: str = Field(default_factory=lambda: str(uuid4()))
    state: State = State.CREATED
    revision: int = 0
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    pending_reason: str | None = None


class Measurement(Contract):
    value_mm: float | None = Field(default=None, gt=0)
    sigma_mm: float | None = Field(default=None, gt=0)
    status: Literal[
        "unknown", "estimated", "cross_checked", "physically_verified", "conflict"
    ]
    sources: list[
        Literal[
            "photo_on_sheet",
            "paper_strip",
            "manual_ruler",
            "manual_caliper",
            "fit_coupon",
        ]
    ] = Field(default_factory=list)
    confirmed_by_user: bool = False

    @model_validator(mode="after")
    def require_evidence(self):
        if self.status not in {"unknown", "conflict"}:
            if self.value_mm is None or self.sigma_mm is None or not self.sources:
                raise ValueError(
                    "Usable measurements need a value, uncertainty, and sources"
                )
        if self.status == "cross_checked" and len(set(self.sources)) < 2:
            raise ValueError("Cross-checking needs at least two distinct methods")
        if self.status == "physically_verified" and (
            not self.confirmed_by_user
            or not {"manual_caliper", "fit_coupon"}.intersection(self.sources)
        ):
            raise ValueError(
                "Physical verification needs confirmed caliper or fit-coupon evidence"
            )
        return self


class SleeveParameters(Contract):
    family: Literal["grip_sleeve"] = "grip_sleeve"
    inner_width_mm: float = Field(gt=0)
    inner_thickness_mm: float = Field(gt=0)
    outer_width_mm: float = Field(gt=0)
    outer_thickness_mm: float = Field(gt=0)
    length_mm: float = Field(gt=0)
    wall_min_mm: float = Field(gt=0)
    clearance_mm: float = Field(ge=0)
    slit_width_mm: float = Field(gt=0)

    @model_validator(mode="after")
    def walls(self):
        if self.outer_width_mm < self.inner_width_mm + 2 * self.wall_min_mm:
            raise ValueError("Insufficient wall along width")
        if self.outer_thickness_mm < self.inner_thickness_mm + 2 * self.wall_min_mm:
            raise ValueError("Insufficient wall along thickness")
        if self.slit_width_mm >= self.outer_width_mm:
            raise ValueError("Slit must be narrower than the sleeve")
        return self


class PullParameters(Contract):
    family: Literal["drawer_pull_bar"] = "drawer_pull_bar"
    hole_spacing_mm: float = Field(gt=0)
    hole_diameter_mm: float = Field(gt=0)
    boss_diameter_mm: float = Field(gt=0)
    bar_length_mm: float = Field(gt=0)
    bar_width_mm: float = Field(gt=0)
    bar_height_mm: float = Field(gt=0)
    standoff_mm: float = Field(gt=0)

    @model_validator(mode="after")
    def mounting(self):
        if self.boss_diameter_mm <= self.hole_diameter_mm:
            raise ValueError("Boss must surround the mounting hole")
        if self.bar_length_mm < self.hole_spacing_mm + self.boss_diameter_mm:
            raise ValueError("Bar must cover both mounting bosses")
        return self


class Coordinates(Contract):
    units: Literal["mm"] = "mm"
    origin: Literal["centre_of_start_face"] = "centre_of_start_face"
    x: Literal["length"] = "length"
    y: Literal["width"] = "width"
    z: Literal["thickness; sleeve slit on +z"] = "thickness; sleeve slit on +z"


class DesignSpec(Contract):
    schema_version: Literal["1.0.0"] = "1.0.0"
    design_id: str
    parent_design_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    example: bool = False
    track: Track
    object_type: Literal["spoon", "fork", "knife", "drawer_handle"]
    object_confirmed: bool
    difficulty: str = Field(min_length=1, max_length=500)
    parameters: Annotated[
        SleeveParameters | PullParameters, Field(discriminator="family")
    ]
    measurements: dict[str, Measurement]
    coordinate_system: Coordinates = Field(default_factory=Coordinates)
    verification_level: Literal[
        "concept",
        "dimensionally_estimated",
        "dimensionally_cross_checked",
        "physically_verified",
    ]
    disclaimers: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def evidence_gate(self):
        sleeve = self.parameters.family == "grip_sleeve"
        if (self.track == Track.ADAPT) != sleeve:
            raise ValueError("Design family must match track")
        if sleeve == (self.object_type == "drawer_handle"):
            raise ValueError("Object must match design family")
        required = (
            {"handle_width", "handle_thickness", "covered_length"}
            if sleeve
            else {"hole_spacing", "hole_diameter"}
        )
        records = [self.measurements.get(key) for key in required]
        rank = {
            "unknown": 0,
            "conflict": 0,
            "estimated": 1,
            "cross_checked": 2,
            "physically_verified": 3,
        }
        supported = min(rank[m.status] if m else 0 for m in records)
        claimed = {
            "concept": 0,
            "dimensionally_estimated": 1,
            "dimensionally_cross_checked": 2,
            "physically_verified": 3,
        }[self.verification_level]
        if claimed > supported or (claimed and not self.object_confirmed):
            raise ValueError(
                "Verification level exceeds confirmed measurement evidence"
            )
        if self.example and claimed == 3:
            raise ValueError("Illustrative examples cannot claim physical verification")
        if claimed:
            p = self.parameters
            if sleeve:
                expected = {
                    "handle_width": p.inner_width_mm - p.clearance_mm,
                    "handle_thickness": p.inner_thickness_mm - p.clearance_mm,
                    "covered_length": p.length_mm,
                }
            else:
                expected = {
                    "hole_spacing": p.hole_spacing_mm,
                    "hole_diameter": p.hole_diameter_mm,
                }
            for key, value in expected.items():
                if abs(self.measurements[key].value_mm - value) > 0.0001:
                    raise ValueError(f"Parameter disagrees with measurement: {key}")
        return self

    def content_hash(self) -> str:
        # Preserve full numeric precision; no hidden rounding of measured dimensions.
        payload = self.model_dump(mode="json", exclude={"created_at"})
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()
