import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.jobs.schemas import GenerationJobRead
from app.reviews.models import RejectReason, ReviewDecision


class ReviewCreate(BaseModel):
    decision: ReviewDecision
    reason: RejectReason | None = None
    reviewer: str = Field(min_length=1, max_length=120)
    comment: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def rejection_has_reason_and_comment(self):
        if self.decision in {ReviewDecision.REJECTED, ReviewDecision.REGENERATE}:
            if self.reason is None:
                raise ValueError("reject reason is required")
            if not self.comment or not self.comment.strip():
                raise ValueError("review comment is required")
        return self


class ReviewRead(ReviewCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_version_id: uuid.UUID
    generation_job_id: uuid.UUID
    is_deleted: bool
    deleted_at: datetime | None
    created_at: datetime


class ReviewOutcome(BaseModel):
    review: ReviewRead
    regenerated_job: GenerationJobRead | None = None


class ReviewUpdate(BaseModel):
    reviewer: str | None = Field(default=None, min_length=1, max_length=120)
    reason: RejectReason | None = None
    comment: str | None = Field(default=None, max_length=2000)
