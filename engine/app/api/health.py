# /health router — liveness check, no auth required
from fastapi import APIRouter
from ..config import settings

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0", "environment": settings.ENVIRONMENT}
