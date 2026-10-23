from typing import Annotated, Literal
from uuid import uuid4

from pydantic import Field, model_validator

from backend.contracts import Contract

ObjectType = Literal["spoon", "fork", "knife", "drawer_handle", "other", "unknown"]
Component = Literal["handle", "drawer_mounting_holes", "other", "unknown"]
Difficulty = Literal["slipping", "pain", "cannot_wrap_fingers", "weak_grip", "other"]
ShortText = Annotated[str, Field(min_length=1, max_length=240)]


class VisionAnalysis(Contract):
    object_type: ObjectType
    component: Component
    cross_section_guess: Literal["round", "oval", "flat", "unknown"]
    handle_end_side: Literal["left", "right", "top", "bottom", "unknown"]
    confidence: Literal["low", "medium", "high"]
    visible_facts: list[ShortText] = Field(max_length=8)
    inferences: list[ShortText] = Field(max_length=8)
    suggested_difficulty: Difficulty | Literal["unknown"]


class ImageMetadata(Contract):
    id: str = Field(default_factory=lambda: str(uuid4()))
    sha256: str
    width: int
    height: int
    brightness: float
    blur_score: float
    overexposed_fraction: float
    ai_long_edge_pixels: int


class Confirmation(Contract):
    object_type: ObjectType
    component: Component
    cross_section: Literal["round", "oval", "flat", "unknown"]
    handle_intact: bool | None = None
    confirmed_by_user: Literal[True]


class Answers(Contract):
    difficulty: Difficulty | None = None
    material_preference: Literal["soft", "rigid", "no_preference"] | None = None
    hand_preference: Literal["left", "right", "either"] = "either"
    repair_case: (
        Literal["missing_pull_visible_holes", "hidden_mounting", "other", "not_sure"]
        | None
    ) = None
    surface_condition: Literal["sound", "damaged", "not_sure"] | None = None


class AnalysisWorkspace(Contract):
    image: ImageMetadata | None = None
    user_text: str = Field(default="", max_length=2000)
    analysis: VisionAnalysis | None = None
    provider: Literal["ollama", "gemini", "manual"] | None = None
    model: str | None = None
    provider_status: Literal[
        "not_run",
        "running",
        "ok",
        "unavailable",
        "invalid_response",
        "manual",
        "interrupted",
    ] = "not_run"
    attempts: int = 0
    latency_ms: float | None = None
    message: str | None = None
    cloud_consent: bool = False
    confirmation: Confirmation | None = None
    answers: Answers = Field(default_factory=Answers)
    answer_sources: dict[str, str] = Field(default_factory=dict)


class RevisionBody(Contract):
    expected_revision: int = Field(ge=0)


class AnalyzeRequest(RevisionBody):
    user_text: str | None = Field(default=None, max_length=2000)
    provider: Literal["ollama", "gemini", "manual"] | None = None
    cloud_consent: bool = False


class ConfirmRequest(Confirmation, RevisionBody):
    pass


class AnswerRequest(RevisionBody):
    difficulty: Difficulty | None = None
    material_preference: Literal["soft", "rigid", "no_preference"] | None = None
    hand_preference: Literal["left", "right", "either"] | None = None
    repair_case: (
        Literal["missing_pull_visible_holes", "hidden_mounting", "other", "not_sure"]
        | None
    ) = None
    surface_condition: Literal["sound", "damaged", "not_sure"] | None = None

    @model_validator(mode="after")
    def at_least_one(self):
        if not any(
            getattr(self, key) is not None
            for key in type(self).model_fields
            if key != "expected_revision"
        ):
            raise ValueError("Provide at least one answer")
        return self
