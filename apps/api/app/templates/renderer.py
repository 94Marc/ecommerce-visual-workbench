import io
import math
from collections import deque
from dataclasses import dataclass
from typing import Any

from PIL import (
    Image,
    ImageChops,
    ImageColor,
    ImageDraw,
    ImageEnhance,
    ImageFont,
    ImageOps,
    ImageStat,
)

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
    metadata: dict[str, Any]


class EdgeCleanupProcessor:
    """Deterministic matte cleanup that never changes the product's alpha silhouette."""

    def process(self, image: Image.Image) -> tuple[Image.Image, dict[str, Any]]:
        rgba = image.convert("RGBA")
        alpha = rgba.getchannel("A")
        rgb = rgba.convert("RGB")
        alpha_pixels = alpha.load()
        cleaned_rgb = rgb.copy()
        cleaned_pixels = cleaned_rgb.load()
        queue: deque[tuple[int, int]] = deque()
        visited = bytearray(image.width * image.height)
        for row in range(image.height):
            for column in range(image.width):
                if alpha_pixels[column, row] >= 250:
                    queue.append((column, row))
                    visited[row * image.width + column] = 1
        processed = 0
        while queue:
            column, row = queue.popleft()
            inherited = cleaned_pixels[column, row]
            for next_column, next_row in (
                (column - 1, row),
                (column + 1, row),
                (column, row - 1),
                (column, row + 1),
            ):
                if not (0 <= next_column < image.width and 0 <= next_row < image.height):
                    continue
                index = next_row * image.width + next_column
                if visited[index]:
                    continue
                visited[index] = 1
                if alpha_pixels[next_column, next_row] > 0:
                    cleaned_pixels[next_column, next_row] = inherited
                    processed += 1
                    queue.append((next_column, next_row))
        cleaned = cleaned_rgb.convert("RGBA")
        cleaned.putalpha(alpha)
        alpha_preserved = ImageChops.difference(alpha, cleaned.getchannel("A")).getbbox() is None
        return cleaned, {
            "alpha_preserved": alpha_preserved,
            "edge_pixels_processed": processed,
            "method": "nearest_opaque_source_rgb_defringe",
        }


class ProductToneCorrection:
    MAX_EXPOSURE_STOPS = 0.12
    MAX_BRIGHTNESS_FACTOR = 1.04
    MAX_CONTRAST_FACTOR = 1.03
    MAX_CHANNEL_GAIN_DELTA = 0.025

    def process(self, image: Image.Image) -> tuple[Image.Image, dict[str, Any]]:
        rgba = image.convert("RGBA")
        alpha = rgba.getchannel("A")
        rgb = rgba.convert("RGB")
        mask = alpha.point(lambda value: 255 if value >= 128 else 0)
        stats = ImageStat.Stat(rgb, mask=mask)
        means = stats.mean
        neutral = sum(means) / 3 if means else 0
        gains = [
            max(
                1 - self.MAX_CHANNEL_GAIN_DELTA,
                min(1 + self.MAX_CHANNEL_GAIN_DELTA, neutral / mean),
            )
            if mean
            else 1.0
            for mean in means
        ]
        channels = rgb.split()
        balanced = Image.merge(
            "RGB",
            tuple(
                channel.point(lambda value, gain=gain: min(255, round(value * gain)))
                for channel, gain in zip(channels, gains, strict=True)
            ),
        )
        exposure_factor = min(2**self.MAX_EXPOSURE_STOPS, self.MAX_BRIGHTNESS_FACTOR)
        corrected = ImageEnhance.Brightness(balanced).enhance(exposure_factor)
        corrected = ImageEnhance.Contrast(corrected).enhance(self.MAX_CONTRAST_FACTOR)
        output = corrected.convert("RGBA")
        output.putalpha(alpha)
        return output, {
            "white_balance_gains": [round(value, 4) for value in gains],
            "exposure_stops": self.MAX_EXPOSURE_STOPS,
            "brightness_factor": round(exposure_factor, 4),
            "contrast_factor": self.MAX_CONTRAST_FACTOR,
            "limits": {
                "max_exposure_stops": self.MAX_EXPOSURE_STOPS,
                "max_brightness_factor": self.MAX_BRIGHTNESS_FACTOR,
                "max_contrast_factor": self.MAX_CONTRAST_FACTOR,
                "max_channel_gain_delta": self.MAX_CHANNEL_GAIN_DELTA,
            },
        }


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
        subject_fill_ratio: float | None = None,
        edge_cleanup: bool = False,
        tone_correction: bool = False,
    ) -> RenderedTemplate:
        document = TemplateDocument.model_validate(version.schema_json)
        background = version.background or {}
        color = self._color(background.get("color", "#ffffff"), 1)
        canvas = Image.new("RGBA", (version.canvas_width, version.canvas_height), color)
        metadata: dict[str, Any] = {
            "subject_fill_ratio": subject_fill_ratio,
            "edge_cleanup": edge_cleanup,
            "tone_correction": tone_correction,
            "warnings": [],
            "processors": {},
        }
        self._render_layers(
            canvas,
            document.layers,
            snapshot,
            assets,
            0,
            0,
            subject_fill_ratio,
            edge_cleanup,
            tone_correction,
            metadata,
        )
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
            metadata=metadata,
        )

    def _render_layers(
        self,
        canvas: Image.Image,
        layers: list[TemplateLayer],
        snapshot: dict[str, Any],
        assets: dict[str, AssetVersion],
        offset_x: float,
        offset_y: float,
        subject_fill_ratio: float | None,
        edge_cleanup: bool,
        tone_correction: bool,
        metadata: dict[str, Any],
    ) -> None:
        for layer in sorted(layers, key=lambda item: item.zIndex):
            if not layer.visible:
                continue
            x, y = offset_x + layer.x, offset_y + layer.y
            if layer.type is LayerType.GROUP:
                self._render_layers(
                    canvas,
                    layer.children or [],
                    snapshot,
                    assets,
                    x,
                    y,
                    subject_fill_ratio,
                    edge_cleanup,
                    tone_correction,
                    metadata,
                )
            elif layer.type is LayerType.IMAGE:
                self._render_image(
                    canvas,
                    layer,
                    assets[layer.assetSource or ""],
                    x,
                    y,
                    subject_fill_ratio,
                    edge_cleanup,
                    tone_correction,
                    metadata,
                )
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
        subject_fill_ratio: float | None,
        edge_cleanup: bool,
        tone_correction: bool,
        metadata: dict[str, Any],
    ) -> None:
        with Image.open(io.BytesIO(self.storage.get(version.object_key))) as source:
            image = source.convert("RGBA")
        if min(image.size) < 512:
            metadata["warnings"].append("SOURCE_QUALITY_LOW")
        alpha_bbox = image.getchannel("A").getbbox()
        if alpha_bbox is not None:
            image = image.crop(alpha_bbox)
        if edge_cleanup:
            image, cleanup = EdgeCleanupProcessor().process(image)
            metadata["processors"]["edge_cleanup"] = cleanup
        if tone_correction:
            image, tone = ProductToneCorrection().process(image)
            metadata["processors"]["tone_correction"] = tone
        target = (max(1, round(layer.width)), max(1, round(layer.height)))
        if subject_fill_ratio is not None:
            max_side = round(min(canvas.width, canvas.height) * subject_fill_ratio)
            target = (max_side, max_side)
        if layer.fit == "cover":
            image = ImageOps.fit(image, target, method=Image.Resampling.LANCZOS)
        elif layer.fit == "manual":
            image = image.resize(target, Image.Resampling.LANCZOS)
        else:
            scale = min(target[0] / image.width, target[1] / image.height)
            contained = (
                max(1, round(image.width * scale)),
                max(1, round(image.height * scale)),
            )
            image = image.resize(contained, Image.Resampling.LANCZOS)
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
        if subject_fill_ratio is not None:
            left = round((canvas.width - image.width) / 2)
            top = round((canvas.height - image.height) / 2)
        else:
            left = round(x + (layer.width - image.width) / 2)
            top = round(y + (layer.height - image.height) / 2)
        metadata["subject_bbox"] = [left, top, left + image.width, top + image.height]
        metadata["actual_subject_fill_ratio"] = round(
            max(image.width, image.height) / min(canvas.width, canvas.height), 4
        )
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
