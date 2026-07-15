import sentry_sdk
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.v1.router import router as api_v1_router
from app.core.config import settings

if settings.sentry_dsn:
    sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment, traces_sample_rate=0.1)

app = FastAPI(title="DeliveryPilot API", version="0.1.0")
app.include_router(api_v1_router)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    # Normalizes every error response to {"detail": str, "code": str}
    # (CLAUDE.md §4), whether it's one of our structured HTTPExceptions or a
    # bare one raised by FastAPI/Starlette itself (e.g. 404 on an unknown route).
    if isinstance(exc.detail, dict) and "detail" in exc.detail and "code" in exc.detail:
        body = exc.detail
    else:
        body = {"detail": str(exc.detail), "code": "http_error"}
    return JSONResponse(status_code=exc.status_code, content=body)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc.errors()), "code": "validation_error"},
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
