from fastapi import FastAPI

from app.api.ingestion import router as ingestion_router
from app.api.protocols import router as protocols_router
from app.api.rules import router as rules_router
from app.api.sse import router as sse_router
from app.api.tasks import router as tasks_router
from app.api.routes import router as testing_router
from app.mock_api.router import router as mock_api_router


def create_app() -> FastAPI:
    app = FastAPI(title="InvariantFlow", version="0.1.0")
    app.include_router(mock_api_router)
    app.include_router(testing_router)
    app.include_router(ingestion_router)
    app.include_router(rules_router)
    app.include_router(sse_router)
    app.include_router(tasks_router)
    app.include_router(protocols_router)
    return app


app = create_app()
