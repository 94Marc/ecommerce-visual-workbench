import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.rules.models import PlatformCode
from app.rules.schemas import (
    PlatformCategoryCreate,
    PlatformCategoryRead,
    PlatformCreate,
    PlatformMarketCreate,
    PlatformMarketRead,
    PlatformRead,
    PlatformRuleCreate,
    PlatformRuleRead,
    RuleResolutionRequest,
    RuleVersionCreate,
)
from app.rules.service import DuplicateRuleError, RuleNotFoundError, RuleService

router = APIRouter(prefix="/platform-rules", tags=["platform-rules"])


def service(session: Session = Depends(get_session)) -> RuleService:
    return RuleService(session)


@router.get("/platforms", response_model=list[PlatformRead])
def list_platforms(rules: RuleService = Depends(service)):
    return rules.list_platforms()


@router.post("/platforms", response_model=PlatformRead, status_code=status.HTTP_201_CREATED)
def create_platform(data: PlatformCreate, rules: RuleService = Depends(service)):
    return _handle(lambda: rules.create_platform(data))


@router.get("/markets", response_model=list[PlatformMarketRead])
def list_markets(
    platform_id: uuid.UUID | None = Query(default=None), rules: RuleService = Depends(service)
):
    return rules.list_markets(platform_id)


@router.post("/markets", response_model=PlatformMarketRead, status_code=status.HTTP_201_CREATED)
def create_market(data: PlatformMarketCreate, rules: RuleService = Depends(service)):
    return _handle(lambda: rules.create_market(data))


@router.get("/categories", response_model=list[PlatformCategoryRead])
def list_categories(
    market_id: uuid.UUID | None = Query(default=None), rules: RuleService = Depends(service)
):
    return rules.list_categories(market_id)


@router.post(
    "/categories", response_model=PlatformCategoryRead, status_code=status.HTTP_201_CREATED
)
def create_category(data: PlatformCategoryCreate, rules: RuleService = Depends(service)):
    return _handle(lambda: rules.create_category(data))


@router.post("", response_model=PlatformRuleRead, status_code=status.HTTP_201_CREATED)
def create_rule(data: PlatformRuleCreate, rules: RuleService = Depends(service)):
    return _handle(lambda: rules.create_rule(data))


@router.get("", response_model=list[PlatformRuleRead])
def list_rules(
    platform: PlatformCode | None = Query(default=None), rules: RuleService = Depends(service)
):
    return rules.list_rules(platform)


@router.post(
    "/{rule_id}/versions", response_model=PlatformRuleRead, status_code=status.HTTP_201_CREATED
)
def add_rule_version(
    rule_id: uuid.UUID, data: RuleVersionCreate, rules: RuleService = Depends(service)
):
    return _handle(lambda: rules.add_version(rule_id, data))


@router.post("/resolve", response_model=PlatformRuleRead)
def resolve_rule(data: RuleResolutionRequest, rules: RuleService = Depends(service)):
    try:
        return rules.resolve(**data.model_dump())
    except RuleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _handle(operation):
    try:
        return operation()
    except DuplicateRuleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
