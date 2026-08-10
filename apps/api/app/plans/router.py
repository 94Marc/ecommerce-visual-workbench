import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.plans.schemas import (
    ProductVisualPlanCreate,
    ProductVisualPlanRead,
    ProductVisualPlanUpdate,
)
from app.plans.service import VisualPlanNotFoundError, VisualPlanService, VisualPlanValidationError

router = APIRouter(prefix="/visual-plans", tags=["visual-plans"])


def service(session: Session = Depends(get_session)) -> VisualPlanService:
    return VisualPlanService(session)


@router.post("", response_model=ProductVisualPlanRead, status_code=status.HTTP_201_CREATED)
def create_plan(data: ProductVisualPlanCreate, plans: VisualPlanService = Depends(service)):
    return _handle(lambda: plans.create(data))


@router.get("", response_model=list[ProductVisualPlanRead])
def list_plans(
    product_id: uuid.UUID | None = Query(default=None), plans: VisualPlanService = Depends(service)
):
    return plans.list(product_id)


@router.get("/{plan_id}", response_model=ProductVisualPlanRead)
def get_plan(plan_id: uuid.UUID, plans: VisualPlanService = Depends(service)):
    return _handle(lambda: plans.get(plan_id))


@router.patch("/{plan_id}", response_model=ProductVisualPlanRead)
def update_plan(
    plan_id: uuid.UUID, data: ProductVisualPlanUpdate, plans: VisualPlanService = Depends(service)
):
    return _handle(lambda: plans.update(plan_id, data))


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(plan_id: uuid.UUID, plans: VisualPlanService = Depends(service)):
    _handle(lambda: plans.delete(plan_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _handle(operation):
    try:
        return operation()
    except VisualPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VisualPlanValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
