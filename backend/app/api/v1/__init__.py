"""API v1 router — aggregates all endpoint routers."""

from fastapi import APIRouter

from app.api.v1.endpoints import crawl, crawl_configs, health, scrape

api_router = APIRouter()

api_router.include_router(
    health.router, prefix="/health", tags=["health"]
)
api_router.include_router(
    crawl_configs.router, prefix="/crawl-configs", tags=["crawl-configs"]
)
api_router.include_router(
    scrape.router, prefix="/scrape", tags=["scraping"]
)
api_router.include_router(
    crawl.router, prefix="/crawl", tags=["crawling"]
)
