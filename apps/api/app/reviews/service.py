import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assets.models import AssetStatus, AssetVersion
from app.core.models import utc_now
from app.jobs.models import GenerationJob, JobStatus, ValidationStatus
from app.jobs.queue import JobDispatcher
from app.jobs.service import JobService
from app.reviews.models import Review, ReviewDecision
from app.reviews.schemas import ReviewCreate, ReviewUpdate


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
        if (
            data.decision is ReviewDecision.APPROVED
            and job.validation_status is not ValidationStatus.PASSED
        ):
            raise ReviewInvariantError("output must pass its pinned platform rule before approval")

        review = Review(
            asset_version_id=asset_version_id,
            generation_job_id=job.id,
            **data.model_dump(),
        )
        self.session.add(review)
        version.status = {
            ReviewDecision.APPROVED: AssetStatus.APPROVED,
            ReviewDecision.REJECTED: AssetStatus.REJECTED,
            ReviewDecision.REGENERATE: AssetStatus.REJECTED,
        }[data.decision]
        self.session.commit()
        self.session.refresh(review)

        regenerated_job = None
        if data.decision is ReviewDecision.REGENERATE:
            regenerated_job = JobService(self.session, self.dispatcher).regenerate_job(
                job.id, data.comment
            )
            regenerated_job.parameters = {
                **regenerated_job.parameters,
                "regenerated_from_review_id": str(review.id),
            }
            self.session.commit()
            self.session.refresh(regenerated_job)
        return ReviewResult(review=review, regenerated_job=regenerated_job)

    def list_reviews(self, asset_version_id: uuid.UUID) -> list[Review]:
        return list(
            self.session.scalars(
                select(Review)
                .where(
                    Review.asset_version_id == asset_version_id,
                    Review.is_deleted.is_(False),
                )
                .order_by(Review.created_at.desc())
            )
        )

    def get_review(self, review_id: uuid.UUID, asset_version_id: uuid.UUID | None = None) -> Review:
        review = self.session.get(Review, review_id)
        if (
            review is None
            or review.is_deleted
            or (asset_version_id is not None and review.asset_version_id != asset_version_id)
        ):
            raise ReviewNotFoundError(f"review {review_id} not found")
        return review

    def update_review(
        self,
        review_id: uuid.UUID,
        data: ReviewUpdate,
        asset_version_id: uuid.UUID | None = None,
    ) -> Review:
        review = self.get_review(review_id, asset_version_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(review, field, value)
        self.session.commit()
        self.session.refresh(review)
        return review

    def delete_review(
        self, review_id: uuid.UUID, asset_version_id: uuid.UUID | None = None
    ) -> None:
        review = self.get_review(review_id, asset_version_id)
        review.is_deleted = True
        review.deleted_at = utc_now()
        self.session.commit()
        self._sync_version_status(review.asset_version_id)

    def _sync_version_status(self, asset_version_id: uuid.UUID) -> None:
        version = self.session.get(AssetVersion, asset_version_id)
        if version is None:
            return
        latest = self.session.scalar(
            select(Review)
            .where(
                Review.asset_version_id == asset_version_id,
                Review.is_deleted.is_(False),
            )
            .order_by(Review.created_at.desc())
            .limit(1)
        )
        version.status = (
            {
                ReviewDecision.APPROVED: AssetStatus.APPROVED,
                ReviewDecision.REJECTED: AssetStatus.REJECTED,
                ReviewDecision.REGENERATE: AssetStatus.REJECTED,
            }[latest.decision]
            if latest
            else AssetStatus.REVIEW
        )
        self.session.commit()

    def latest_decision(self, asset_version_id: uuid.UUID) -> ReviewDecision | None:
        review = self.session.scalar(
            select(Review)
            .where(
                Review.asset_version_id == asset_version_id,
                Review.is_deleted.is_(False),
            )
            .order_by(Review.created_at.desc())
            .limit(1)
        )
        return review.decision if review else None
