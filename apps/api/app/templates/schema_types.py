import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class LayerType(StrEnum):
    IMAGE = "IMAGE"
    TEXT = "TEXT"
    SHAPE = "SHAPE"
    LINE = "LINE"
    ICON = "ICON"
    GROUP = "GROUP"


class TemplateLayer(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,79}$")
    type: LayerType
    x: float = 0
    y: float = 0
    width: float = Field(default=0, ge=0)
    height: float = Field(default=0, ge=0)
    rotation: float = Field(default=0, ge=-360, le=360)
    opacity: float = Field(default=1, ge=0, le=1)
    visible: bool = True
    locked: bool = False
    zIndex: int = Field(default=0, ge=-1000, le=1000)

    text: str | None = None
    fontSize: float | None = Field(default=None, gt=0, le=1000)
    fontFamily: str | None = Field(default=None, max_length=120)
    fontWeight: Literal["normal", "medium", "semibold", "bold"] | None = None
    align: Literal["left", "center", "right"] | None = None
    lineHeight: float | None = Field(default=None, gt=0, le=5)
    fill: str | None = None
    stroke: str | None = None
    strokeWidth: float | None = Field(default=None, ge=0, le=100)

    assetSource: str | None = None
    fit: Literal["contain", "cover", "manual"] | None = None
    crop: dict[str, float] | None = None
    cornerRadius: float | None = Field(default=None, ge=0)

    points: list[float] | None = None
    dash: list[float] | None = None
    arrowStart: bool = False
    arrowEnd: bool = False
    icon: str | None = None
    children: list["TemplateLayer"] | None = None

    @model_validator(mode="after")
    def validate_type_fields(self):
        if self.type is LayerType.TEXT and self.text is None:
            raise ValueError("TEXT layers require text")
        if self.type is LayerType.IMAGE:
            if not self.assetSource:
                raise ValueError("IMAGE layers require assetSource")
            if not re.fullmatch(r"\{\{asset\.(main|cutout|closeup|package)\}\}", self.assetSource):
                raise ValueError("IMAGE assetSource must use an approved asset binding")
        if self.type is LayerType.LINE and (not self.points or len(self.points) < 4):
            raise ValueError("LINE layers require at least two points")
        if self.type is LayerType.GROUP and self.children is None:
            raise ValueError("GROUP layers require children")
        return self


class TemplateDocument(BaseModel):
    schemaVersion: Literal["1.0"] = "1.0"
    layers: list[TemplateLayer]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def unique_layer_ids(self):
        ids: list[str] = []

        def collect(layers: list[TemplateLayer]) -> None:
            for layer in layers:
                ids.append(layer.id)
                if layer.children:
                    collect(layer.children)

        collect(self.layers)
        if len(ids) != len(set(ids)):
            raise ValueError("layer ids must be unique within a template")
        return self


TemplateLayer.model_rebuild()


def validate_template_schema(value: dict[str, Any]) -> dict[str, Any]:
    return TemplateDocument.model_validate(value).model_dump(mode="json", exclude_none=True)
