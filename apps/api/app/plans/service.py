from __future__ import annotations

import uuid
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.models import Product
from app.plans.models import AssetSlot, ProductVisualPlan
from app.plans.schemas import AssetSlotInput, ProductVisualPlanCreate, ProductVisualPlanUpdate
from app.rules.models import Platform, RuleVersion


class VisualPlanNotFoundError(LookupError):
    pass


class VisualPlanValidationError(ValueError):
    pass


class VisualPlanService:
    def __init__(self, session: Session):
        self.session = session

    def create(self, data: ProductVisualPlanCreate) -> ProductVisualPlan:
        self._validate_references(data.product_id, data.platform_id, data.rule_version_id)
        plan = ProductVisualPlan(
            **data.model_dump(exclude={"slots", "requested_outputs"}),
            requested_outputs={key.value: value for key, value in data.requested_outputs.items()},
        )
        self.session.add(plan)
        self.session.flush()
        self._replace_slots(plan, data.slots)
        self.session.commit()
        self.session.refresh(plan)
        return plan

    def get(self, plan_id: uuid.UUID) -> ProductVisualPlan:
        plan = self.session.get(ProductVisualPlan, plan_id)
        if plan is None:
            raise VisualPlanNotFoundError(f"visual plan {plan_id} not found")
        return plan

    def list(self, product_id: uuid.UUID | None = None) -> list[ProductVisualPlan]:
        statement = select(ProductVisualPlan)
        if product_id:
            statement = statement.where(ProductVisualPlan.product_id == product_id)
        return list(self.session.scalars(statement.order_by(ProductVisualPlan.created_at.desc())))

    def update(self, plan_id: uuid.UUID, data: ProductVisualPlanUpdate) -> ProductVisualPlan:
        plan = self.get(plan_id)
        for key, value in data.model_dump(
            exclude_unset=True, exclude={"slots", "requested_outputs"}
        ).items():
            setattr(plan, key, value)
        if data.requested_outputs is not None:
            requested = {key.value: value for key, value in data.requested_outputs.items()}
            self._validate_slot_counts(requested, data.slots)
            plan.requested_outputs = requested
            self._replace_slots(plan, data.slots)
        elif data.slots is not None:
            self._validate_slot_counts(plan.requested_outputs, data.slots)
            self._replace_slots(plan, data.slots)
        self.session.commit()
        self.session.refresh(plan)
        return plan

    def delete(self, plan_id: uuid.UUID) -> None:
        self.session.delete(self.get(plan_id))
        self.session.commit()

    def _validate_references(
        self, product_id: uuid.UUID, platform_id: uuid.UUID, rule_version_id: uuid.UUID
    ) -> None:
        if self.session.get(Product, product_id) is None:
            raise VisualPlanNotFoundError(f"product {product_id} not found")
        platform = self.session.get(Platform, platform_id)
        if platform is None:
            raise VisualPlanNotFoundError(f"platform {platform_id} not found")
        version = self.session.get(RuleVersion, rule_version_id)
        if version is None:
            raise VisualPlanNotFoundError(f"rule version {rule_version_id} not found")
        if version.platform != platform.code:
            raise VisualPlanValidationError("rule version does not belong to selected platform")

    def _replace_slots(
        self, plan: ProductVisualPlan, custom_slots: list[AssetSlotInput] | None
    ) -> None:
        plan.slots.clear()
        self.session.flush()
        inputs = custom_slots or [
            AssetSlotInput(code=f"{kind}_{index:02d}", image_type=kind)
            for kind, count in plan.requested_outputs.items()
            for index in range(1, count + 1)
        ]
        for position, item in enumerate(inputs, start=1):
            plan.slots.append(
                AssetSlot(
                    code=item.code, image_type=item.image_type, position=position, label=item.label
                )
            )

    @staticmethod
    def _validate_slot_counts(outputs: dict[str, int], slots: list[AssetSlotInput] | None) -> None:
        if slots is not None and dict(Counter(slot.image_type.value for slot in slots)) != outputs:
            raise VisualPlanValidationError(
                "custom asset slots must match requested output quantities"
            )
