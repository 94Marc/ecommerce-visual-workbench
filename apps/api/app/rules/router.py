from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.rules.models import PlatformCode
from app.rules.schemas import PlatformRuleCreate, PlatformRuleRead, RuleResolutionRequest
from app.rules.service import DuplicateRuleError, RuleNotFoundError, RuleService

router = APIRouter(prefix="/platform-rules", tags=["platform-rules"])


def service(session: Session = Depends(get_session)) -> RuleService:
    return RuleService(session)


@router.post("", response_model=PlatformRuleRead, status_code=status.HTTP_201_CREATED)
def create_rule(data: PlatformRuleCreate, rules: RuleService = Depends(service)):
    try:
        return rules.create_rule(data)
    except DuplicateRuleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("", response_model=list[PlatformRuleRead])
def list_rules(
    platform: PlatformCode | None = Query(default=None),
    rules: RuleService = Depends(service),
):
    return rules.list_rules(platform)


@router.post("/resolve", response_model=PlatformRuleRead)
def resolve_rule(data: RuleResolutionRequest, rules: RuleService = Depends(service)):
    try:
        return rules.resolve(**data.model_dump())
    except RuleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
