from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.assets.router import router as assets_router
from app.catalog.router import router as catalog_router
from app.core.config import get_settings
from app.jobs.router import router as jobs_router
from app.rules.router import router as rules_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(catalog_router, prefix=settings.api_prefix)
    app.include_router(assets_router, prefix=settings.api_prefix)
    app.include_router(rules_router, prefix=settings.api_prefix)
    app.include_router(jobs_router, prefix=settings.api_prefix)
    return app


app = create_app()
