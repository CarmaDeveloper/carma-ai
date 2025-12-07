from fastapi import APIRouter

from app.api.v1.routers import chatbot, reports, ingestion, comprehend

api_router_v1 = APIRouter(prefix="/v1")

api_router_v1.include_router(chatbot.router, tags=["chatbot"])
api_router_v1.include_router(reports.router, tags=["reports"])
api_router_v1.include_router(ingestion.router, tags=["ingestion"])
api_router_v1.include_router(comprehend.router, tags=["comprehend"])
