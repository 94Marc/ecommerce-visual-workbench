from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Ecommerce Visual Workbench"
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./workbench.db"
    redis_url: str = "redis://localhost:6379/0"
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "workbench"
    s3_secret_key: str = "workbench-secret"
    s3_bucket: str = "product-assets"
    s3_region: str = "us-east-1"
    image_generation_provider: str = "mock"
    image_generation_timeout_seconds: int = 120
    image_generation_max_attempts: int = 3
    image_generation_quality: str = "medium"
    image_generation_output_format: str = "png"
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_image_model: str = "gpt-image-2"
    background_removal_provider: str = "rembg"
    image_upscale_provider: str = "realesrgan"
    rembg_enabled: bool = False
    realesrgan_enabled: bool = False
    comfyui_enabled: bool = False
    comfyui_base_url: str | None = None
    comfyui_poll_interval_seconds: float = 0.5
    comfyui_workflow_root: str = "workflows/comfyui"
    rembg_service_url: str | None = None
    realesrgan_service_url: str | None = None
    realesrgan_executable: str = "realesrgan-ncnn-vulkan"
    realesrgan_model: str = "realesrgan-x4plus"
    realesrgan_tile: int = 256
    image_processing_temp_dir: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
