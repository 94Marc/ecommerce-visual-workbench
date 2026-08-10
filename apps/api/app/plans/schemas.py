import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.rules.models import ImageSlot

PLAN_IMAGE_TYPES = {
    ImageSlot.MAIN,
    ImageSlot.DETAIL,
    ImageSlot.DIMENSION,
    ImageSlot.SCENE,
    ImageSlot.USAGE,
    ImageSlot.PACKAGE,
    ImageSlot.CLOSEUP,
}


class AssetSlotInput(BaseModel):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,79}$")
    image_type: ImageSlot
    label: str | None = Field(default=None, max_length=160)

    @field_validator("image_type")
    @classmethod
    def generated_type_only(cls, value: ImageSlot) -> ImageSlot:
        if value not in PLAN_IMAGE_TYPES:
            raise ValueError("image type is not available in a visual plan")
        return value


class ProductVisualPlanCreate(BaseModel):
    product_id: uuid.UUID
    platform_id: uuid.UUID
    rule_version_id: uuid.UUID
    name: str = Field(min_length=1, max_length=160)
    market: str = Field(min_length=1, max_length=32)
    category: str = Field(min_length=1, max_length=120)
    requested_outputs: dict[ImageSlot, int]
    slots: list[AssetSlotInput] | None = None

    @field_validator("requested_outputs")
    @classmethod
    def valid_outputs(cls, value: dict[ImageSlot, int]) -> dict[ImageSlot, int]:
        if not value:
            raise ValueError("at least one image type is required")
        if any(kind not in PLAN_IMAGE_TYPES for kind in value):
            raise ValueError("visual plans only support production image types")
        if any(count < 1 or count > 50 for count in value.values()):
            raise ValueError("each image quantity must be between 1 and 50")
        return value

    @model_validator(mode="after")
    def custom_slots_match_quantities(self):
        if self.slots is None:
            return self
        if len({slot.code for slot in self.slots}) != len(self.slots):
            raise ValueError("asset slot codes must be unique")
        actual = {kind: 0 for kind in self.requested_outputs}
        for slot in self.slots:
            if slot.image_type not in actual:
                raise ValueError(f"slot type {slot.image_type} is not requested")
            actual[slot.image_type] += 1
        if actual != self.requested_outputs:
            raise ValueError("custom asset slots must match requested output quantities")
        return self


class ProductVisualPlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    requested_outputs: dict[ImageSlot, int] | None = None
    slots: list[AssetSlotInput] | None = None

    @field_validator("requested_outputs")
    @classmethod
    def valid_outputs(cls, value):
        return value if value is None else ProductVisualPlanCreate.valid_outputs(value)


class AssetSlotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    product_visual_plan_id: uuid.UUID
    code: str
    image_type: ImageSlot
    position: int
    label: str | None
    created_at: datetime
    updated_at: datetime


class ProductVisualPlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    product_id: uuid.UUID
    platform_id: uuid.UUID
    rule_version_id: uuid.UUID
    name: str
    market: str
    category: str
    requested_outputs: dict[str, int]
    slots: list[AssetSlotRead]
    created_at: datetime
    updated_at: datetime
