import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.jobs.schemas import GenerationJobRead
from app.reviews.models import ReviewDecision


class ReviewCreate(BaseModel):
    decision: ReviewDecision
    reviewer: str = Field(min_length=1, max_length=120)
    comment: str | None = Field(default=None, max_length=2000)


class ReviewRead(ReviewCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_version_id: uuid.UUID
    generation_job_id: uuid.UUID
    created_at: datetime


class ReviewOutcome(BaseModel):
    review: ReviewRead
    regenerated_job: GenerationJobRead | None = None
