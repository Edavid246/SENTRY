"""FastAPI application factory."""

from fastapi import FastAPI

from app.api.assistant import router as assistant_router
from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.cases import router as cases_router
from app.api.connected import router as connected_router
from app.api.correlation import router as correlation_router
from app.api.divisions import router as divisions_router
from app.api.documents import router as documents_router
from app.api.home import router as home_router
from app.api.records import router as records_router
from app.api.reports import router as reports_router
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Defence Gateway AI MVP — all data is fictitious demo data.",
    )
    application.include_router(auth_router)
    application.include_router(documents_router)
    application.include_router(records_router)
    application.include_router(audit_router)
    application.include_router(assistant_router)
    application.include_router(home_router)
    application.include_router(divisions_router)
    application.include_router(cases_router)
    application.include_router(reports_router)
    application.include_router(correlation_router)
    application.include_router(connected_router)

    @application.get("/healthz", tags=["system"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
