# Phase 4: real image processing providers

Phase 4 keeps one auditable task ledger for background removal, upscaling and generated listing
images. A task records its provider, workflow, generation mode, references, request ID, attempts,
duration, output metadata and immutable output AssetVersion.

## Routing

| Task type | Provider route | Output behavior |
| --- | --- | --- |
| `REMOVE_BACKGROUND` | rembg | New `CUTOUT` asset with transparent PNG version |
| `UPSCALE` | Real-ESRGAN | Append a version to a derived asset; an ORIGINAL source creates a `CLOSEUP` derived asset |
| `GENERATE_SCENE` | ComfyUI or OpenAI | New `SCENE` version, default `BALANCED` |
| `GENERATE_USAGE` | ComfyUI or OpenAI | New `USAGE` version, default `BALANCED` |
| `GENERATE_BACKGROUND` | ComfyUI or OpenAI | New platform image, default `CREATIVE` |
| `GENERATE_DETAIL` | ComfyUI or OpenAI | New detail/closeup/dimension/package version, default `STRICT` |
| `GENERATE_MAIN` | ComfyUI or OpenAI | New `MAIN` version, default `STRICT` |

Generation tasks still resolve and pin an existing `RuleVersion`. Transformation tasks do not
invent a platform rule. No provider overwrites its source object.

## rembg

Install the optional local runtime and enable it explicitly:

```shell
python -m pip install -e ".[dev,image-processing]"
```

```dotenv
BACKGROUND_REMOVAL_PROVIDER=rembg
REMBG_ENABLED=true
```

The import is lazy. When the optional package or its model runtime is absent, the task fails with
`provider_unavailable`. Processing and timeout failures are persisted and follow the configured
retry policy. Output is normalized to RGBA PNG.

## Real-ESRGAN

Install `realesrgan-ncnn-vulkan` separately and place it on `PATH`, or set its full executable path.
The main application does not bundle or impersonate the binary.

```dotenv
IMAGE_UPSCALE_PROVIDER=realesrgan
REALESRGAN_ENABLED=true
REALESRGAN_EXECUTABLE=C:\tools\realesrgan\realesrgan-ncnn-vulkan.exe
REALESRGAN_MODEL=realesrgan-x4plus
REALESRGAN_TILE=256
```

`CONSERVATIVE` is the default and uses a 2× scale with the conservative product-texture policy.
`2X` and `4X` are explicit scale choices. Tile size can be overridden per task. The ledger stores
source and output dimensions, tile, mode and model. Set `IMAGE_PROCESSING_TEMP_DIR` when the system
temporary directory is not writable.

## ComfyUI

Run ComfyUI as an independent service and enable the HTTP adapter:

```dotenv
IMAGE_GENERATION_PROVIDER=comfyui
COMFYUI_ENABLED=true
COMFYUI_BASE_URL=http://127.0.0.1:8188
COMFYUI_WORKFLOW_ROOT=workflows/comfyui
```

The adapter uses `/upload/image`, `/prompt`, `/history/{prompt_id}` and `/view`. Every selected
reference is uploaded; registered API-format workflows bind `{{reference_image_0}}` and may bind
additional uploaded references as `{{reference_image_1}}`, and so on. Prompt, negative prompt,
seed, mode, width, height and workflow defaults are substituted before submission.

The first registry entries are:

- `product_scene`
- `product_usage`
- `product_background`
- `product_detail`
- `product_main_white`

Their versioned files live in `workflows/comfyui/`. The sample workflows use the checkpoint name
`sd_xl_base_1.0.safetensors`; change the registry defaults to a checkpoint actually installed by
your ComfyUI deployment. Missing workflow files, HTTP errors and workflow execution failures are
reported explicitly. The application never falls back to mock when ComfyUI is selected.

## API operation

List workflows:

```http
GET /api/v1/generation-jobs/workflows
```

Create a background-removal task:

```json
POST /api/v1/generation-jobs/tasks
{
  "source_version_id": "<asset-version-uuid>",
  "task_type": "REMOVE_BACKGROUND"
}
```

Create a ComfyUI main-image task:

```json
POST /api/v1/generation-jobs/tasks
{
  "source_version_id": "<original-version-uuid>",
  "reference_asset_version_ids": ["<front-uuid>", "<side-uuid>"],
  "task_type": "GENERATE_MAIN",
  "workflow_id": "10000000-0000-4000-8000-000000000005",
  "platform": "temu",
  "market": "US",
  "category": "*",
  "image_slot": "MAIN",
  "generation_mode": "STRICT",
  "prompt": "Create a faithful white-background main image",
  "negative_prompt": "changed logo, changed color, extra parts",
  "seed": 42
}
```

The Redis worker processes the queued UUID. The development-only endpoint
`POST /api/v1/generation-jobs/{job_id}/process` runs the same configured routing synchronously.

## Test and secret policy

Automated tests force `IMAGE_GENERATION_PROVIDER=mock` and disable rembg, Real-ESRGAN and ComfyUI.
Provider tests use injected local backends or HTTP transports and never call a paid or external
service. `.env.example` contains no real key. Keep `.env`, model files and provider credentials out
of Git.
