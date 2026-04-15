"""Celery application instance and configuration.

Import this module in workers and beat to get the shared ``celery_app``.
"""

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "pilgrim",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.workers.tasks.scrape",
        "app.workers.tasks.schedule",
        "app.workers.tasks.callback",
    ],
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Task behaviour
    task_track_started=True,
    task_time_limit=settings.celery_task_time_limit_seconds,
    task_soft_time_limit=settings.celery_task_soft_time_limit_seconds,

    # Fair scheduling for long IO tasks
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    # Queue routing
    task_routes={
        "pilgrim.scrape.run_job": {"queue": "crawl_default"},
        "pilgrim.schedule.*": {"queue": "maintenance"},
        "pilgrim.callback.*": {"queue": "maintenance"},
        "pilgrim.maintenance.*": {"queue": "maintenance"},
    },

    # Beat schedule — polling-based scheduler
    beat_schedule={
        "check-schedules-every-30s": {
            "task": "pilgrim.schedule.check_schedules",
            "schedule": 30.0,  # seconds
        },
    },
)
