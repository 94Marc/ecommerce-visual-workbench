import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.jobs.queue import JobDispatcher, get_job_dispatcher
from app.reviews.schemas import ReviewCreate, ReviewOutcome, ReviewRead, ReviewUpdate
from app.reviews.service import ReviewInvariantError, ReviewNotFoundError, ReviewService

router = APIRouter(prefix="/asset-versions/{asset_version_id}/reviews", tags=["reviews"])


def service(
    session: Session = Depends(get_session),
    dispatcher: JobDispatcher = Depends(get_job_dispatcher),
) -> ReviewService:
    return ReviewService(session, dispatcher)


@router.post("", response_model=ReviewOutcome, status_code=status.HTTP_201_CREATED)
def create_review(
    asset_version_id: uuid.UUID,
    data: ReviewCreate,
    reviews: ReviewService = Depends(service),
):
    try:
        result = reviews.decide(asset_version_id, data)
        return {"review": result.review, "regenerated_job": result.regenerated_job}
    except ReviewNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ReviewInvariantError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("", response_model=list[ReviewRead])
def list_reviews(asset_version_id: uuid.UUID, reviews: ReviewService = Depends(service)):
    return reviews.list_reviews(asset_version_id)


@router.get("/{review_id}", response_model=ReviewRead)
def get_review(
    asset_version_id: uuid.UUID,
    review_id: uuid.UUID,
    reviews: ReviewService = Depends(service),
):
    try:
        return reviews.get_review(review_id, asset_version_id)
    except ReviewNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{review_id}", response_model=ReviewRead)
def update_review(
    asset_version_id: uuid.UUID,
    review_id: uuid.UUID,
    data: ReviewUpdate,
    reviews: ReviewService = Depends(service),
):
    try:
        return reviews.update_review(review_id, data, asset_version_id)
    except ReviewNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_review(
    asset_version_id: uuid.UUID,
    review_id: uuid.UUID,
    reviews: ReviewService = Depends(service),
):
    try:
        reviews.delete_review(review_id, asset_version_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ReviewNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
