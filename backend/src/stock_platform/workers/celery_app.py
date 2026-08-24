from celery import Celery  # type: ignore[import-untyped]
from celery.schedules import crontab  # type: ignore[import-untyped]

from stock_platform.settings import Settings

settings = Settings()
celery_app: Celery = Celery("stock_platform", broker=settings.redis_url)
celery_app.conf.update(
    task_ignore_result=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=False,
    timezone="UTC",
    enable_utc=True,
    imports=(
        "stock_platform.workers.schedules",
        "stock_platform.workers.research_tasks",
        "stock_platform.workers.portfolio_tasks",
        "stock_platform.workers.review_tasks",
        "stock_platform.workers.ingestion_tasks",
    ),
    task_routes={
        "stock_platform.workers.ingestion_tasks.run_alpaca_ingestion_job": {
            "queue": "ingestion-low"
        }
    },
)

from stock_platform.workers.schedules import beat_schedule  # noqa: E402

celery_app.conf.beat_schedule = {
    **beat_schedule,
    "dispatch-normalization-outbox": {
        "task": "stock_platform.workers.ingestion_tasks.dispatch_normalization_outbox",
        "schedule": 30.0,
    },
    "report-minio-orphans": {
        "task": "stock_platform.workers.ingestion_tasks.report_minio_orphans",
        "schedule": 3600.0,
    },
    "dispatch-alpaca-ingestion-jobs": {
        "task": "stock_platform.workers.ingestion_tasks.dispatch_alpaca_ingestion_jobs",
        "schedule": 15.0,
    },
    "schedule-alpaca-watchlist-ingestion": {
        "task": "stock_platform.workers.schedules.schedule_alpaca_watchlist_ingestion",
        "schedule": 60.0,
    },
    "schedule-alpaca-daily-ingestion": {
        "task": "stock_platform.workers.schedules.schedule_alpaca_daily_ingestion",
        "schedule": crontab(minute=0, hour=21, day_of_week="1-5"),
    },
}
