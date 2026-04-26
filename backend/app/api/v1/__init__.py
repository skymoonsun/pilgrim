"""API v1 router — aggregates all endpoint routers."""

from fastapi import APIRouter

from app.api.v1.endpoints import activities, ai, crawl, crawl_configs, health, proxy_sources, proxies, sanitizer_configs, schedules, scrape

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
api_router.include_router(
    schedules.router, prefix="/schedules", tags=["schedules"]
)
api_router.include_router(
    ai.router, prefix="/ai", tags=["ai"]
)
api_router.include_router(
    proxy_sources.router, prefix="/proxy-sources", tags=["proxy-sources"]
)
api_router.include_router(
    proxies.router, prefix="/proxies", tags=["proxies"]
)
api_router.include_router(
    activities.router, prefix="/activities", tags=["activities"]
)
api_router.include_router(
    sanitizer_configs.router, prefix="/sanitizer-configs", tags=["sanitizer-configs"]
)
