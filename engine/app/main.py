# FastAPI entrypoint — instantiates the app and mounts all routers
from fastapi import FastAPI
from .config import settings
from .api.health import router as health_router
from .api.routes import router as main_router

app = FastAPI(
    title="Tickr",
    version="0.1.0",
    description="Bloomberg-lite equity research terminal — AI-native fundamentals, filings, and analysis.",
)

app.include_router(health_router)
app.include_router(main_router, prefix="/api/v1")
