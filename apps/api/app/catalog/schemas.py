import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Dimensions(BaseModel):
    length: Decimal | None = Field(default=None, gt=0)
    width: Decimal | None = Field(default=None, gt=0)
    height: Decimal | None = Field(default=None, gt=0)
    unit: str = "cm"


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=120)
    material: str | None = Field(default=None, max_length=120)
    color: str | None = Field(default=None, max_length=120)
    dimensions: Dimensions | None = None
    weight_value: Decimal | None = Field(default=None, gt=0)
    weight_unit: str | None = Field(default=None, max_length=16)
    selling_points: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def weight_has_unit(self) -> "ProductCreate":
        if (self.weight_value is None) != (self.weight_unit is None):
            raise ValueError("weight_value and weight_unit must be provided together")
        return self


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, min_length=1, max_length=120)
    material: str | None = Field(default=None, max_length=120)
    color: str | None = Field(default=None, max_length=120)
    dimensions: Dimensions | None = None
    weight_value: Decimal | None = Field(default=None, gt=0)
    weight_unit: str | None = Field(default=None, max_length=16)
    selling_points: list[str] | None = Field(default=None, max_length=20)


class SKUCreate(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    attributes: dict[str, Any] = Field(default_factory=dict)


class SKURead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    code: str
    attributes: dict[str, Any]
    created_at: datetime


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    category: str
    material: str | None
    color: str | None
    dimensions: dict[str, Any]
    weight_value: Decimal | None
    weight_unit: str | None
    selling_points: list[str]
    is_archived: bool
    archived_at: datetime | None
    skus: list[SKURead]
    created_at: datetime
    updated_at: datetime
