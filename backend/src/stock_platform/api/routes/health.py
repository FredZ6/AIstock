from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from stock_platform.api.dependencies import get_settings
from stock_platform.settings import Settings

router = APIRouter(prefix="/api/v1", tags=["system"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    mode: Literal["fixture", "paper", "test"]
    trading: Literal["paper_only"] = "paper_only"


@router.get("/health", response_model=HealthResponse)
def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    return HealthResponse(mode=settings.environment)
