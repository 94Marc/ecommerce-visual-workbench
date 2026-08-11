import base64
import binascii
import io
from dataclasses import dataclass
from typing import Protocol

import httpx
from PIL import Image

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class ReferenceImage:
    asset_version_id: str
    content: bytes
    filename: str
    mime_type: str


@dataclass(frozen=True)
class ImageGenerationRequest:
    job_id: str
    prompt: str
    references: tuple[ReferenceImage, ...]
    size: str
    width: int
    height: int
    quality: str
    output_format: str
    timeout_seconds: int


@dataclass(frozen=True)
class ImageTransformationRequest:
    job_id: str
    source: ReferenceImage
    timeout_seconds: int


@dataclass(frozen=True)
class ImageGenerationResult:
    content: bytes
    filename: str
    mime_type: str
    width: int
    height: int
    provider_request_id: str | None = None


class ImageGenerationProvider(Protocol):
    name: str
    model: str

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult: ...


class BackgroundRemovalProvider(Protocol):
    name: str
    model: str

    def remove_background(
        self, request: ImageTransformationRequest
    ) -> ImageGenerationResult: ...


class ImageUpscaleProvider(Protocol):
    name: str
    model: str

    def upscale(self, request: ImageTransformationRequest) -> ImageGenerationResult: ...


class ImageProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        retryable: bool,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.request_id = request_id


class ProviderUnavailableError(ImageProviderError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            f"{provider} provider is not configured or available",
            code="provider_unavailable",
            retryable=False,
        )


class MockImageGenerationProvider:
    """Deterministic free provider used locally and in every automated test."""

    name = "mock"
    model = "deterministic-png-v1"

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        buffer = io.BytesIO()
        Image.new("RGB", (request.width, request.height), (245, 247, 250)).save(
            buffer, format="PNG", optimize=True
        )
        return ImageGenerationResult(
            content=buffer.getvalue(),
            filename=f"generated-{request.job_id}.png",
            mime_type="image/png",
            width=request.width,
            height=request.height,
            provider_request_id=f"mock-{request.job_id}",
        )


class OpenAIImageGenerationProvider:
    """OpenAI Image API adapter using all selected supplier angles as references."""

    name = "openai"

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        if not settings.openai_api_key:
            raise ProviderUnavailableError(self.name)
        self.settings = settings
        self.model = settings.openai_image_model
        self.client = client or httpx.Client()

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        if not request.references:
            raise ImageProviderError(
                "at least one reference image is required",
                code="missing_reference",
                retryable=False,
            )
        endpoint = f"{self.settings.openai_base_url.rstrip('/')}/images/edits"
        try:
            response = self.client.post(
                endpoint,
                headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
                data={
                    "model": self.model,
                    "prompt": request.prompt,
                    "size": request.size,
                    "quality": request.quality,
                    "output_format": request.output_format,
                },
                files=[
                    (
                        "image[]",
                        (reference.filename, reference.content, reference.mime_type),
                    )
                    for reference in request.references
                ],
                timeout=request.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise ImageProviderError(
                "image provider request timed out", code="timeout", retryable=True
            ) from exc
        except httpx.TransportError as exc:
            raise ImageProviderError(
                "image provider transport error", code="transport_error", retryable=True
            ) from exc

        request_id = response.headers.get("x-request-id")
        if response.is_error:
            try:
                error = response.json().get("error", {})
            except ValueError:
                error = {}
            code = str(error.get("code") or f"http_{response.status_code}")
            message = str(error.get("message") or "image provider request failed")
            retryable = response.status_code == 429 or response.status_code >= 500
            raise ImageProviderError(
                message[:1000], code=code[:80], retryable=retryable, request_id=request_id
            )

        try:
            payload = response.json()
            content = base64.b64decode(payload["data"][0]["b64_json"], validate=True)
        except (KeyError, IndexError, TypeError, ValueError, binascii.Error) as exc:
            raise ImageProviderError(
                "image provider returned an invalid payload",
                code="invalid_response",
                retryable=False,
                request_id=request_id,
            ) from exc

        output_format = request.output_format.lower()
        mime_type = "image/jpeg" if output_format in {"jpg", "jpeg"} else f"image/{output_format}"
        return ImageGenerationResult(
            content=content,
            filename=f"generated-{request.job_id}.{output_format}",
            mime_type=mime_type,
            width=request.width,
            height=request.height,
            provider_request_id=request_id,
        )


class ComfyUIImageGenerationProvider:
    """Explicit placeholder. It never masquerades as a working ComfyUI integration."""

    name = "comfyui"
    model = "unavailable"

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        raise ProviderUnavailableError(self.name)


class RembgBackgroundRemovalProvider:
    name = "rembg"
    model = "unavailable"

    def remove_background(
        self, request: ImageTransformationRequest
    ) -> ImageGenerationResult:
        raise ProviderUnavailableError(self.name)


class RealESRGANUpscaleProvider:
    name = "realesrgan"
    model = "unavailable"

    def upscale(self, request: ImageTransformationRequest) -> ImageGenerationResult:
        raise ProviderUnavailableError(self.name)


def get_image_generation_provider(
    settings: Settings | None = None,
) -> ImageGenerationProvider:
    configured = settings or get_settings()
    if configured.image_generation_provider == "openai":
        if configured.openai_api_key:
            return OpenAIImageGenerationProvider(configured)
        return MockImageGenerationProvider()
    if configured.image_generation_provider == "comfyui":
        return ComfyUIImageGenerationProvider()
    return MockImageGenerationProvider()


def get_background_removal_provider(
    settings: Settings | None = None,
) -> BackgroundRemovalProvider:
    configured = settings or get_settings()
    if configured.background_removal_provider == "rembg":
        return RembgBackgroundRemovalProvider()
    return RembgBackgroundRemovalProvider()


def get_image_upscale_provider(settings: Settings | None = None) -> ImageUpscaleProvider:
    configured = settings or get_settings()
    if configured.image_upscale_provider == "realesrgan":
        return RealESRGANUpscaleProvider()
    return RealESRGANUpscaleProvider()


def get_configured_provider_identity(settings: Settings | None = None) -> tuple[str, str]:
    provider = get_image_generation_provider(settings)
    return provider.name, provider.model
