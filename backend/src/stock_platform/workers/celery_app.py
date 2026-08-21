from celery import Celery  # type: ignore[import-untyped]

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
    ),
)

from stock_platform.workers.schedules import beat_schedule  # noqa: E402

celery_app.conf.beat_schedule = beat_schedule
