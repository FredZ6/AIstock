"""Celery app wrapper that isolates one agent-runtime acceptance run."""

from __future__ import annotations

import os

from stock_platform.workers.celery_app import celery_app

runtime_control_queue = os.environ["AGENT_RUNTIME_CONTROL_QUEUE"]
runtime_research_queue = os.environ["AGENT_RUNTIME_RESEARCH_QUEUE"]
redis_key_prefix = os.environ["AGENT_RUNTIME_REDIS_KEY_PREFIX"]

task_routes = dict(celery_app.conf.task_routes or {})
task_routes["stock_platform.workers.research_tasks.run_research"] = {
    "queue": runtime_research_queue
}
broker_transport_options = dict(celery_app.conf.broker_transport_options or {})
broker_transport_options["global_keyprefix"] = redis_key_prefix

celery_app.conf.update(
    broker_transport_options=broker_transport_options,
    task_default_queue=runtime_control_queue,
    task_routes=task_routes,
)
