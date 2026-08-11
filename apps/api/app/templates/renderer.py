import io
import math
from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFont, ImageOps

from app.assets.models import AssetVersion
from app.assets.storage import ObjectStorage
from app.templates.bindings import TemplateBindingResolver
from app.templates.models import TemplateVersion
from app.templates.schema_types import LayerType, TemplateDocument, TemplateLayer


@dataclass(frozen=True)
class RenderedTemplate:
    content: bytes
    filename: str
    mime_type: str
    width: int
    height: int


class DeterministicTemplateRenderer:
    def __init__(self, storage: ObjectStorage, bindings: TemplateBindingResolver):
        self.storage = storage
        self.bindings = bindings

    def render(
        self,
        version: TemplateVersion,
        snapshot: dict[str, Any],
        assets: dict[str, AssetVersion],
        *,
        output_format: str,
        quality: int,
    ) -> RenderedTemplate:
        document = TemplateDocument.model_validate(version.schema_json)
        background = version.background or {}
        color = self._color(background.get("color", "#ffffff"), 1)
        canvas = Image.new("RGBA", (version.canvas_width, version.canvas_height), color)
        self._render_layers(canvas, document.layers, snapshot, assets, 0, 0)
        buffer = io.BytesIO()
        if output_format == "JPEG":
            canvas.convert("RGB").save(buffer, format="JPEG", quality=quality, optimize=True)
            extension, mime_type = "jpg", "image/jpeg"
        else:
            canvas.save(buffer, format="PNG", optimize=True)
            extension, mime_type = "png", "image/png"
        return RenderedTemplate(
            content=buffer.getvalue(),
            filename=f"template-render.{extension}",
            mime_type=mime_type,
            width=version.canvas_width,
            height=version.canvas_height,
        )

    def _render_layers(
        self,
        canvas: Image.Image,
        layers: list[TemplateLayer],
        snapshot: dict[str, Any],
        assets: dict[str, AssetVersion],
        offset_x: float,
        offset_y: float,
    ) -> None:
        for layer in sorted(layers, key=lambda item: item.zIndex):
            if not layer.visible:
                continue
            x, y = offset_x + layer.x, offset_y + layer.y
            if layer.type is LayerType.GROUP:
                self._render_layers(canvas, layer.children or [], snapshot, assets, x, y)
            elif layer.type is LayerType.IMAGE:
                self._render_image(canvas, layer, assets[layer.assetSource or ""], x, y)
            elif layer.type is LayerType.TEXT:
                self._render_text(canvas, layer, snapshot, x, y)
            elif layer.type is LayerType.LINE:
                self._render_line(canvas, layer, x, y)
            elif layer.type in {LayerType.SHAPE, LayerType.ICON}:
                self._render_shape(canvas, layer, x, y)

    def _render_image(
        self,
        canvas: Image.Image,
        layer: TemplateLayer,
        version: AssetVersion,
        x: float,
        y: float,
    ) -> None:
        with Image.open(io.BytesIO(self.storage.get(version.object_key))) as source:
            image = source.convert("RGBA")
        target = (max(1, round(layer.width)), max(1, round(layer.height)))
        if layer.fit == "cover":
            image = ImageOps.fit(image, target, method=Image.Resampling.LANCZOS)
        elif layer.fit == "manual":
            image = image.resize(target, Image.Resampling.LANCZOS)
        else:
            image.thumbnail(target, Image.Resampling.LANCZOS)
        if layer.cornerRadius:
            mask = Image.new("L", image.size, 0)
            ImageDraw.Draw(mask).rounded_rectangle(
                (0, 0, image.width, image.height), radius=layer.cornerRadius, fill=255
            )
            image.putalpha(ImageChops.multiply(image.getchannel("A"), mask))
        if layer.opacity < 1:
            alpha = image.getchannel("A").point(lambda value: round(value * layer.opacity))
            image.putalpha(alpha)
        if layer.rotation:
            image = image.rotate(-layer.rotation, expand=True, resample=Image.Resampling.BICUBIC)
        left = round(x + (layer.width - image.width) / 2)
        top = round(y + (layer.height - image.height) / 2)
        canvas.alpha_composite(image, (left, top))

    def _render_text(
        self,
        canvas: Image.Image,
        layer: TemplateLayer,
        snapshot: dict[str, Any],
        x: float,
        y: float,
    ) -> None:
        text = self.bindings.resolve_text(layer.text or "", snapshot)
        font = self._font(round(layer.fontSize or 32), layer.fontWeight == "bold")
        draw = ImageDraw.Draw(canvas)
        fill = self._color(layer.fill or "#172033", layer.opacity)
        spacing = round((layer.fontSize or 32) * ((layer.lineHeight or 1.2) - 1))
        align = layer.align or "left"
        anchor_x = x
        if align == "center":
            anchor_x = x + layer.width / 2
        elif align == "right":
            anchor_x = x + layer.width
        draw.multiline_text(
            (round(anchor_x), round(y)),
            text,
            font=font,
            fill=fill,
            spacing=spacing,
            align=align,
            anchor={"left": "la", "center": "ma", "right": "ra"}[align],
        )

    def _render_line(self, canvas: Image.Image, layer: TemplateLayer, x: float, y: float) -> None:
        points = layer.points or []
        translated = [(x + points[i], y + points[i + 1]) for i in range(0, len(points), 2)]
        draw = ImageDraw.Draw(canvas)
        color = self._color(layer.stroke or "#172033", layer.opacity)
        width = max(1, round(layer.strokeWidth or 2))
        draw.line(translated, fill=color, width=width, joint="curve")
        if len(translated) >= 2 and layer.arrowStart:
            self._arrow(draw, translated[0], translated[1], color, width)
        if len(translated) >= 2 and layer.arrowEnd:
            self._arrow(draw, translated[-1], translated[-2], color, width)

    def _render_shape(self, canvas: Image.Image, layer: TemplateLayer, x: float, y: float) -> None:
        draw = ImageDraw.Draw(canvas)
        box = (round(x), round(y), round(x + layer.width), round(y + layer.height))
        fill = self._color(layer.fill or "#ffffff", layer.opacity)
        stroke = self._color(layer.stroke or layer.fill or "#ffffff", layer.opacity)
        draw.rounded_rectangle(
            box,
            radius=layer.cornerRadius or 0,
            fill=fill,
            outline=stroke,
            width=max(1, round(layer.strokeWidth or 1)),
        )
        if layer.type is LayerType.ICON and layer.icon:
            font = self._font(round(min(layer.width, layer.height) * 0.45), True)
            draw.text(
                (round(x + layer.width / 2), round(y + layer.height / 2)),
                layer.icon[:2],
                font=font,
                fill=self._color(layer.stroke or "#172033", layer.opacity),
                anchor="mm",
            )

    @staticmethod
    def _arrow(draw, tip, toward, color, width) -> None:
        angle = math.atan2(toward[1] - tip[1], toward[0] - tip[0])
        size = max(8, width * 4)
        left = (
            tip[0] + size * math.cos(angle + math.pi / 5),
            tip[1] + size * math.sin(angle + math.pi / 5),
        )
        right = (
            tip[0] + size * math.cos(angle - math.pi / 5),
            tip[1] + size * math.sin(angle - math.pi / 5),
        )
        draw.polygon([tip, left, right], fill=color)

    @staticmethod
    def _font(size: int, bold: bool):
        candidates = (
            ["DejaVuSans-Bold.ttf", "arialbd.ttf"] if bold else ["DejaVuSans.ttf", "arial.ttf"]
        )
        for name in candidates:
            try:
                return ImageFont.truetype(name, size=size)
            except OSError:
                continue
        return ImageFont.load_default(size=max(8, min(size, 64)))

    @staticmethod
    def _color(value: str, opacity: float) -> tuple[int, int, int, int]:
        red, green, blue = ImageColor.getrgb(value)
        return red, green, blue, round(255 * opacity)
