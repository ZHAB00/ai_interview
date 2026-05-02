
"""Celery application instance for async tasks.

Uses Redis as the message broker. Tasks are defined in celery_tasks.py.
"""

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "ai_interview",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

# Autodiscover tasks
celery_app.autodiscover_tasks(["app.services.celery_tasks"], force=True)
