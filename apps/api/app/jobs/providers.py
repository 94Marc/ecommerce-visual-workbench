import base64
import binascii
import io
import json
import shutil
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import httpx
from PIL import Image, UnidentifiedImageError

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
    workflow_id: str | None = None
    workflow_file: str | None = None
    negative_prompt: str | None = None
    generation_mode: str = "STRICT"
    seed: int | None = None
    workflow_parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ImageTransformationRequest:
    job_id: str
    source: ReferenceImage
    timeout_seconds: int
    mode: str = "CONSERVATIVE"
    tile: int | None = None


@dataclass(frozen=True)
class ImageGenerationResult:
    content: bytes
    filename: str
    mime_type: str
    width: int
    height: int
    provider_request_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


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
            metadata={"mock": True},
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
                    ("image[]", (item.filename, item.content, item.mime_type))
                    for item in request.references
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
        _raise_for_response(response, "OpenAI", request_id)
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
            metadata={"generation_mode": request.generation_mode, "seed": request.seed},
        )


class ComfyUIImageGenerationProvider:
    """HTTP adapter for an independent ComfyUI service using API-format workflows."""

    name = "comfyui"
    model = "workflow-api-v1"

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.Client | None = None,
        workflow_loader: Callable[[str], dict[str, Any]] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings or get_settings()
        self.client = client or httpx.Client()
        self.workflow_loader = workflow_loader or self._load_workflow
        self.sleep = sleep

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        if not self.settings.comfyui_enabled or not self.settings.comfyui_base_url:
            raise ProviderUnavailableError(self.name)
        if not request.workflow_file:
            raise ImageProviderError(
                "a ComfyUI workflow is required", code="workflow_required", retryable=False
            )
        base_url = self.settings.comfyui_base_url.rstrip("/")
        try:
            uploaded = [
                self._upload_reference(base_url, item, request.timeout_seconds)
                for item in request.references
            ]
            document = self.workflow_loader(request.workflow_file)
            replacements: dict[str, Any] = {
                "{{prompt}}": request.prompt,
                "{{negative_prompt}}": request.negative_prompt or "",
                "{{seed}}": request.seed if request.seed is not None else 0,
                "{{width}}": request.width,
                "{{height}}": request.height,
                "{{generation_mode}}": request.generation_mode,
            }
            replacements.update(
                {f"{{{{{key}}}}}": value for key, value in request.workflow_parameters.items()}
            )
            for index, image_name in enumerate(uploaded):
                replacements[f"{{{{reference_image_{index}}}}}"] = image_name
            api_prompt = _replace_workflow_values(document.get("prompt", document), replacements)
            client_id = f"workbench-{uuid.uuid4()}"
            response = self.client.post(
                f"{base_url}/prompt",
                json={"prompt": api_prompt, "client_id": client_id},
                timeout=request.timeout_seconds,
            )
            _raise_for_response(response, self.name)
            prompt_id = str(response.json()["prompt_id"])
            image_descriptor = self._wait_for_output(
                base_url, prompt_id, request.timeout_seconds
            )
            image_response = self.client.get(
                f"{base_url}/view",
                params=image_descriptor,
                timeout=request.timeout_seconds,
            )
            _raise_for_response(image_response, self.name, prompt_id)
        except httpx.TimeoutException as exc:
            raise ImageProviderError(
                "ComfyUI request timed out",
                code="timeout",
                retryable=True,
            ) from exc
        except httpx.TransportError as exc:
            raise ImageProviderError(
                "ComfyUI transport error",
                code="transport_error",
                retryable=True,
            ) from exc
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ImageProviderError(
                "ComfyUI returned an invalid response",
                code="invalid_response",
                retryable=False,
            ) from exc

        width, height, mime_type = _inspect_image(image_response.content)
        filename = str(image_descriptor.get("filename") or f"comfyui-{prompt_id}.png")
        return ImageGenerationResult(
            content=image_response.content,
            filename=filename,
            mime_type=mime_type,
            width=width,
            height=height,
            provider_request_id=prompt_id,
            metadata={
                "workflow_id": request.workflow_id,
                "workflow_file": request.workflow_file,
                "generation_mode": request.generation_mode,
                "seed": request.seed,
                "reference_count": len(uploaded),
            },
        )

    def _upload_reference(
        self, base_url: str, reference: ReferenceImage, timeout_seconds: int
    ) -> str:
        response = self.client.post(
            f"{base_url}/upload/image",
            files={"image": (reference.filename, reference.content, reference.mime_type)},
            data={"overwrite": "false", "type": "input"},
            timeout=timeout_seconds,
        )
        _raise_for_response(response, self.name)
        payload = response.json()
        subfolder = str(payload.get("subfolder") or "").strip("/")
        name = str(payload["name"])
        return f"{subfolder}/{name}" if subfolder else name

    def _wait_for_output(
        self, base_url: str, prompt_id: str, timeout_seconds: int
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            response = self.client.get(
                f"{base_url}/history/{prompt_id}",
                timeout=max(0.1, deadline - time.monotonic()),
            )
            _raise_for_response(response, self.name, prompt_id)
            history = response.json().get(prompt_id)
            if history:
                status = history.get("status", {})
                if status.get("status_str") == "error" or status.get("completed") is False:
                    raise ImageProviderError(
                        "ComfyUI workflow execution failed",
                        code="workflow_failed",
                        retryable=False,
                        request_id=prompt_id,
                    )
                for output in history.get("outputs", {}).values():
                    images = output.get("images", [])
                    if images:
                        return dict(images[0])
            self.sleep(self.settings.comfyui_poll_interval_seconds)
        raise ImageProviderError(
            "ComfyUI workflow timed out",
            code="timeout",
            retryable=True,
            request_id=prompt_id,
        )

    def _load_workflow(self, workflow_file: str) -> dict[str, Any]:
        root = Path(self.settings.comfyui_workflow_root).resolve()
        path = (root / workflow_file).resolve()
        if root != path and root not in path.parents:
            raise ImageProviderError(
                "workflow path is outside the registry root",
                code="invalid_workflow_path",
                retryable=False,
            )
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ImageProviderError(
                "registered workflow file was not found",
                code="workflow_not_found",
                retryable=False,
            ) from exc


class RembgBackgroundRemovalProvider:
    name = "rembg"
    model = "u2net"

    def __init__(
        self,
        settings: Settings | None = None,
        backend: Callable[[bytes], bytes] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.backend = backend

    def remove_background(
        self, request: ImageTransformationRequest
    ) -> ImageGenerationResult:
        if not self.settings.rembg_enabled:
            raise ProviderUnavailableError(self.name)
        backend = self.backend or self._load_backend()
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rembg")
        future = executor.submit(backend, request.source.content)
        try:
            processed = future.result(timeout=request.timeout_seconds)
        except FutureTimeoutError as exc:
            future.cancel()
            raise ImageProviderError(
                "rembg processing timed out", code="timeout", retryable=True
            ) from exc
        except Exception as exc:
            raise ImageProviderError(
                "rembg processing failed", code="processing_error", retryable=True
            ) from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        try:
            with Image.open(io.BytesIO(processed)) as image:
                rgba = image.convert("RGBA")
                width, height = rgba.size
                buffer = io.BytesIO()
                rgba.save(buffer, format="PNG", optimize=True)
        except (UnidentifiedImageError, OSError, TypeError) as exc:
            raise ImageProviderError(
                "rembg returned an invalid image",
                code="invalid_image",
                retryable=False,
            ) from exc
        request_id = f"rembg-{uuid.uuid4()}"
        return ImageGenerationResult(
            content=buffer.getvalue(),
            filename=f"cutout-{request.job_id}.png",
            mime_type="image/png",
            width=width,
            height=height,
            provider_request_id=request_id,
            metadata={
                "transparent": True,
                "source_asset_version_id": request.source.asset_version_id,
            },
        )

    @staticmethod
    def _load_backend() -> Callable[[bytes], bytes]:
        try:
            from rembg import remove
        except ImportError as exc:
            raise ProviderUnavailableError("rembg") from exc
        return remove


class RealESRGANUpscaleProvider:
    name = "realesrgan"

    def __init__(
        self,
        settings: Settings | None = None,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.model = self.settings.realesrgan_model
        self.runner = runner or subprocess.run

    def upscale(self, request: ImageTransformationRequest) -> ImageGenerationResult:
        if not self.settings.realesrgan_enabled:
            raise ProviderUnavailableError(self.name)
        executable = shutil.which(self.settings.realesrgan_executable)
        if executable is None and self.runner is subprocess.run:
            raise ProviderUnavailableError(self.name)
        executable = executable or self.settings.realesrgan_executable
        scale = 4 if request.mode == "4X" else 2
        tile = request.tile if request.tile is not None else self.settings.realesrgan_tile
        source_width, source_height, _ = _inspect_image(request.source.content)
        with tempfile.TemporaryDirectory(
            prefix="workbench-realesrgan-",
            dir=self.settings.image_processing_temp_dir,
        ) as directory:
            source_path = Path(directory) / "source.png"
            output_path = Path(directory) / "output.png"
            source_path.write_bytes(request.source.content)
            command = [
                executable,
                "-i",
                str(source_path),
                "-o",
                str(output_path),
                "-n",
                self.model,
                "-s",
                str(scale),
                "-t",
                str(tile),
                "-f",
                "png",
            ]
            try:
                completed = self.runner(
                    command,
                    timeout=request.timeout_seconds,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise ImageProviderError(
                    "Real-ESRGAN processing timed out", code="timeout", retryable=True
                ) from exc
            except OSError as exc:
                raise ProviderUnavailableError(self.name) from exc
            if completed.returncode != 0:
                error = (completed.stderr or completed.stdout or "processing failed")[-1000:]
                raise ImageProviderError(
                    f"Real-ESRGAN {error}", code="processing_error", retryable=True
                )
            if not output_path.is_file():
                raise ImageProviderError(
                    "Real-ESRGAN did not create an output image",
                    code="missing_output",
                    retryable=False,
                )
            content = output_path.read_bytes()

        width, height, mime_type = _inspect_image(content)
        request_id = f"realesrgan-{uuid.uuid4()}"
        return ImageGenerationResult(
            content=content,
            filename=f"upscaled-{request.job_id}.png",
            mime_type=mime_type,
            width=width,
            height=height,
            provider_request_id=request_id,
            metadata={
                "mode": request.mode,
                "tile": tile,
                "source_width": source_width,
                "source_height": source_height,
                "output_width": width,
                "output_height": height,
                "texture_policy": "conservative",
            },
        )


def get_image_generation_provider(
    settings: Settings | None = None,
) -> ImageGenerationProvider:
    configured = settings or get_settings()
    if configured.image_generation_provider == "openai":
        if configured.openai_api_key:
            return OpenAIImageGenerationProvider(configured)
        return MockImageGenerationProvider()
    if configured.image_generation_provider == "comfyui":
        return ComfyUIImageGenerationProvider(configured)
    return MockImageGenerationProvider()


def get_background_removal_provider(
    settings: Settings | None = None,
) -> BackgroundRemovalProvider:
    return RembgBackgroundRemovalProvider(settings or get_settings())


def get_image_upscale_provider(settings: Settings | None = None) -> ImageUpscaleProvider:
    return RealESRGANUpscaleProvider(settings or get_settings())


def get_configured_provider_identity(settings: Settings | None = None) -> tuple[str, str]:
    provider = get_image_generation_provider(settings)
    return provider.name, provider.model


def _raise_for_response(
    response: httpx.Response, provider: str, request_id: str | None = None
) -> None:
    if not response.is_error:
        return
    try:
        payload = response.json()
        detail = payload.get("error") or payload.get("detail") or payload
        message = detail.get("message") if isinstance(detail, dict) else str(detail)
        code = detail.get("code") if isinstance(detail, dict) else None
    except ValueError:
        message = response.text or f"{provider} request failed"
        code = None
    raise ImageProviderError(
        str(message)[:1000],
        code=str(code or f"http_{response.status_code}")[:80],
        retryable=response.status_code == 429 or response.status_code >= 500,
        request_id=request_id,
    )


def _inspect_image(content: bytes) -> tuple[int, int, str]:
    try:
        with Image.open(io.BytesIO(content)) as image:
            width, height = image.size
            detected_format = (image.format or "").lower()
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageProviderError(
            "provider output is not a readable image",
            code="invalid_image",
            retryable=False,
        ) from exc
    mime_type = "image/jpeg" if detected_format == "jpeg" else f"image/{detected_format}"
    return width, height, mime_type


def _replace_workflow_values(value: Any, replacements: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: _replace_workflow_values(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_workflow_values(item, replacements) for item in value]
    if isinstance(value, str):
        return replacements.get(value, value)
    return value
