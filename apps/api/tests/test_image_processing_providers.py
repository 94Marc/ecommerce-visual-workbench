import io
import json
import subprocess
import time
from pathlib import Path

import httpx
import pytest
from app.assets.models import AssetType, AssetVersion
from app.assets.service import AssetService
from app.catalog.schemas import ProductCreate
from app.catalog.service import CatalogService
from app.core.config import Settings
from app.jobs.models import JobStatus, TaskType
from app.jobs.providers import (
    ComfyUIImageGenerationProvider,
    ImageGenerationRequest,
    ImageProviderError,
    ImageTransformationRequest,
    ProviderUnavailableError,
    RealESRGANUpscaleProvider,
    ReferenceImage,
    RembgBackgroundRemovalProvider,
)
from app.jobs.schemas import ImageProcessingTaskCreate
from app.jobs.service import JobService
from app.jobs.worker import GenerationWorker
from PIL import Image

from tests.conftest import MemoryJobDispatcher, MemoryObjectStorage


def png(width: int = 8, height: int = 6, *, alpha: bool = False) -> bytes:
    buffer = io.BytesIO()
    mode = "RGBA" if alpha else "RGB"
    color = (30, 80, 120, 0) if alpha else (30, 80, 120)
    Image.new(mode, (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


def reference(content: bytes | None = None) -> ReferenceImage:
    return ReferenceImage("version-1", content or png(), "product.png", "image/png")


def transformation_request(**changes) -> ImageTransformationRequest:
    values = {
        "job_id": "job-1",
        "source": reference(),
        "timeout_seconds": 2,
    }
    values.update(changes)
    return ImageTransformationRequest(**values)


def generation_request(**changes) -> ImageGenerationRequest:
    values = {
        "job_id": "job-1",
        "prompt": "keep the blue mug unchanged",
        "references": (reference(), reference()),
        "size": "1024x1024",
        "width": 1024,
        "height": 1024,
        "quality": "medium",
        "output_format": "png",
        "timeout_seconds": 2,
        "workflow_id": "workflow-1",
        "workflow_file": "test.json",
        "negative_prompt": "distorted logo",
        "generation_mode": "STRICT",
        "seed": 42,
        "workflow_parameters": {
            "checkpoint": "test.safetensors",
            "steps": 20,
        },
    }
    values.update(changes)
    return ImageGenerationRequest(**values)


def test_rembg_outputs_real_transparent_png():
    provider = RembgBackgroundRemovalProvider(
        Settings(rembg_enabled=True), backend=lambda _: png(alpha=True)
    )

    result = provider.remove_background(transformation_request())

    with Image.open(io.BytesIO(result.content)) as image:
        assert image.mode == "RGBA"
        assert image.getextrema()[3] == (0, 0)
    assert result.mime_type == "image/png"
    assert result.metadata["transparent"] is True
    assert result.provider_request_id.startswith("rembg-")


def test_rembg_timeout_is_retryable():
    def slow_backend(_: bytes) -> bytes:
        time.sleep(0.05)
        return png(alpha=True)

    provider = RembgBackgroundRemovalProvider(
        Settings(rembg_enabled=True), backend=slow_backend
    )

    with pytest.raises(ImageProviderError) as error:
        provider.remove_background(transformation_request(timeout_seconds=0.001))

    assert error.value.code == "timeout"
    assert error.value.retryable is True


def test_disabled_rembg_is_explicitly_unavailable():
    with pytest.raises(ProviderUnavailableError) as error:
        RembgBackgroundRemovalProvider(Settings(rembg_enabled=False)).remove_background(
            transformation_request()
        )
    assert error.value.code == "provider_unavailable"


def test_realesrgan_cli_records_dimensions_tile_and_mode(monkeypatch):
    commands: list[list[str]] = []
    files: dict[str, bytes] = {}

    class TemporaryWorkspace:
        def __enter__(self):
            return "virtual-workspace"

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(
        "app.jobs.providers.tempfile.TemporaryDirectory",
        lambda **_kwargs: TemporaryWorkspace(),
    )
    monkeypatch.setattr(Path, "write_bytes", lambda self, data: files.__setitem__(str(self), data))
    monkeypatch.setattr(Path, "read_bytes", lambda self: files[str(self)])
    monkeypatch.setattr(Path, "is_file", lambda self: str(self) in files)

    def runner(command, **_kwargs):
        commands.append(command)
        output = Path(command[command.index("-o") + 1])
        output.write_bytes(png(32, 24))
        return subprocess.CompletedProcess(command, 0, "", "")

    provider = RealESRGANUpscaleProvider(
        Settings(
            realesrgan_enabled=True,
            realesrgan_tile=128,
        ),
        runner=runner,
    )
    result = provider.upscale(transformation_request(mode="4X", tile=64))

    assert result.width == 32
    assert result.height == 24
    assert result.metadata == {
        "mode": "4X",
        "tile": 64,
        "source_width": 8,
        "source_height": 6,
        "output_width": 32,
        "output_height": 24,
        "texture_policy": "conservative",
    }
    assert commands[0][commands[0].index("-s") + 1] == "4"


def test_comfyui_http_workflow_uploads_references_and_downloads_output():
    submitted = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/upload/image":
            return httpx.Response(200, json={"name": f"ref-{len(submitted)}.png"})
        if request.url.path == "/prompt":
            submitted.update(json.loads(request.content))
            return httpx.Response(200, json={"prompt_id": "prompt-42"})
        if request.url.path == "/history/prompt-42":
            return httpx.Response(
                200,
                json={
                    "prompt-42": {
                        "status": {"completed": True},
                        "outputs": {"8": {"images": [{"filename": "out.png"}]}},
                    }
                },
            )
        if request.url.path == "/view":
            return httpx.Response(200, content=png(64, 64))
        raise AssertionError(request.url)

    workflow = {
        "prompt": {
            "1": {"inputs": {"text": "{{prompt}}", "seed": "{{seed}}"}},
            "2": {"inputs": {"image": "{{reference_image_0}}"}},
        }
    }
    provider = ComfyUIImageGenerationProvider(
        Settings(comfyui_enabled=True, comfyui_base_url="http://comfy.test"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        workflow_loader=lambda _: workflow,
        sleep=lambda _: None,
    )

    result = provider.generate(generation_request())

    assert result.provider_request_id == "prompt-42"
    assert result.width == result.height == 64
    assert submitted["prompt"]["1"]["inputs"]["seed"] == 42
    assert submitted["prompt"]["2"]["inputs"]["image"].startswith("ref-")
    assert result.metadata["reference_count"] == 2


def test_comfyui_poll_timeout_is_retryable():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/upload/image":
            return httpx.Response(200, json={"name": "ref.png"})
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "slow"})
        if request.url.path == "/history/slow":
            return httpx.Response(200, json={})
        raise AssertionError(request.url)

    provider = ComfyUIImageGenerationProvider(
        Settings(
            comfyui_enabled=True,
            comfyui_base_url="http://comfy.test",
            comfyui_poll_interval_seconds=0,
        ),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        workflow_loader=lambda _: {"prompt": {}},
        sleep=lambda _: None,
    )
    with pytest.raises(ImageProviderError) as error:
        provider.generate(generation_request(timeout_seconds=0))
    assert error.value.code == "timeout"
    assert error.value.retryable is True


def test_worker_routes_rembg_and_preserves_original_version(session):
    storage = MemoryObjectStorage()
    dispatcher = MemoryJobDispatcher()
    product = CatalogService(session).create_product(
        ProductCreate(name="Blue mug", category="kitchen", color="blue")
    )
    original = AssetService(session, storage).create_original(
        product.id, png(), "mug.png", "image/png", width=8, height=6
    )
    source = original.versions[0]
    original_bytes = storage.get(source.object_key)
    job = JobService(session, dispatcher).create_processing_task(
        ImageProcessingTaskCreate(
            source_version_id=source.id,
            task_type=TaskType.REMOVE_BACKGROUND,
        )
    )
    provider = RembgBackgroundRemovalProvider(
        Settings(rembg_enabled=True), backend=lambda _: png(alpha=True)
    )

    completed = GenerationWorker(
        session, storage, background_provider=provider
    ).process(job.id)

    output = session.get(AssetVersion, completed.output_version_id)
    assert completed.status is JobStatus.COMPLETED
    assert completed.provider == "rembg"
    assert completed.output_metadata["transparent"] is True
    assert output.id != source.id
    assert output.source_version_id == source.id
    assert output.asset.asset_type is AssetType.CUTOUT
    assert storage.get(source.object_key) == original_bytes
    assert session.get(AssetVersion, source.id).checksum_sha256 == source.checksum_sha256


class AlwaysTimeoutRembg:
    name = "rembg"
    model = "test"

    def remove_background(self, _request):
        raise ImageProviderError("timeout", code="timeout", retryable=True)


def test_worker_retries_retryable_processing_failure(session):
    storage = MemoryObjectStorage()
    product = CatalogService(session).create_product(
        ProductCreate(name="Blue mug", category="kitchen")
    )
    source = AssetService(session, storage).create_original(
        product.id, png(), "mug.png", "image/png"
    ).versions[0]
    job = JobService(session, MemoryJobDispatcher()).create_processing_task(
        ImageProcessingTaskCreate(
            source_version_id=source.id,
            task_type=TaskType.REMOVE_BACKGROUND,
        )
    )

    failed = GenerationWorker(
        session, storage, background_provider=AlwaysTimeoutRembg()
    ).process(job.id)

    assert failed.status is JobStatus.FAILED
    assert failed.failure_code == "timeout"
    assert failed.attempt_count == failed.max_attempts == 3


def test_processing_task_and_workflow_registry_routes(client):
    product = client.post(
        "/api/v1/products", json={"name": "Mug", "category": "kitchen"}
    ).json()
    created = client.post(
        f"/api/v1/products/{product['id']}/assets/original",
        files={"file": ("mug.png", png(), "image/png")},
    ).json()
    source_id = created["versions"][0]["id"]

    response = client.post(
        "/api/v1/generation-jobs/tasks",
        json={"source_version_id": source_id, "task_type": "REMOVE_BACKGROUND"},
    )
    workflows = client.get("/api/v1/generation-jobs/workflows")

    assert response.status_code == 201
    assert response.json()["task_type"] == "REMOVE_BACKGROUND"
    assert response.json()["provider"] == "rembg"
    assert workflows.status_code == 200
    assert {item["name"] for item in workflows.json()} >= {
        "product_scene",
        "product_usage",
        "product_background",
        "product_detail",
        "product_main_white",
    }
