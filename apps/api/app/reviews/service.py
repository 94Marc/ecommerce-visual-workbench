import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assets.models import AssetVersion
from app.jobs.models import GenerationJob, JobStatus
from app.jobs.queue import JobDispatcher
from app.jobs.schemas import GenerationJobCreate
from app.jobs.service import JobService
from app.reviews.models import Review, ReviewDecision
from app.reviews.schemas import ReviewCreate


class ReviewNotFoundError(LookupError):
    pass


class ReviewInvariantError(ValueError):
    pass


@dataclass(frozen=True)
class ReviewResult:
    review: Review
    regenerated_job: GenerationJob | None = None


class ReviewService:
    def __init__(self, session: Session, dispatcher: JobDispatcher):
        self.session = session
        self.dispatcher = dispatcher

    def decide(self, asset_version_id: uuid.UUID, data: ReviewCreate) -> ReviewResult:
        version = self.session.get(AssetVersion, asset_version_id)
        if version is None:
            raise ReviewNotFoundError(f"asset version {asset_version_id} not found")
        job = self.session.scalar(
            select(GenerationJob)
            .where(GenerationJob.output_version_id == asset_version_id)
            .order_by(GenerationJob.completed_at.desc())
            .limit(1)
        )
        if job is None or job.status is not JobStatus.COMPLETED:
            raise ReviewInvariantError("only completed generation outputs can be reviewed")

        review = Review(
            asset_version_id=asset_version_id,
            generation_job_id=job.id,
            **data.model_dump(),
        )
        self.session.add(review)
        self.session.commit()
        self.session.refresh(review)

        regenerated_job = None
        if data.decision is ReviewDecision.REGENERATE:
            regenerated_job = JobService(self.session, self.dispatcher).create_job(
                GenerationJobCreate(
                    source_version_id=job.source_version_id,
                    platform=job.platform,
                    market=job.market,
                    category=job.category,
                    image_slot=job.image_slot,
                    parameters={**job.parameters, "regenerated_from_review_id": str(review.id)},
                )
            )
        return ReviewResult(review=review, regenerated_job=regenerated_job)

    def list_reviews(self, asset_version_id: uuid.UUID) -> list[Review]:
        return list(
            self.session.scalars(
                select(Review)
                .where(Review.asset_version_id == asset_version_id)
                .order_by(Review.created_at.desc())
            )
        )

    def latest_decision(self, asset_version_id: uuid.UUID) -> ReviewDecision | None:
        review = self.session.scalar(
            select(Review)
            .where(Review.asset_version_id == asset_version_id)
            .order_by(Review.created_at.desc())
            .limit(1)
        )
        return review.decision if review else None
