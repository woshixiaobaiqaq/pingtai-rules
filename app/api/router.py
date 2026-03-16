from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import audit, rules

api_router = APIRouter()
api_router.include_router(audit.router, tags=["audit"])
api_router.include_router(rules.router, tags=["rules"])

