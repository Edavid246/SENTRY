"""FastAPI application factory."""

from fastapi import FastAPI

from app.api.assistant import router as assistant_router
from app.api.correlation import router as correlation_router
from app.api.dashboard import router as dashboard_router
from app.api.endpoints import router as api_router
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Defence Gateway AI MVP — all data is fictitious demo data.",
    )
    application.include_router(api_router)
    application.include_router(assistant_router)
    application.include_router(dashboard_router)
    application.include_router(correlation_router)

    @application.get("/healthz", tags=["system"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
