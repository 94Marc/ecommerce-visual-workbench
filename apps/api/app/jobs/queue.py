import uuid
from typing import Protocol

from redis import Redis

from app.core.config import get_settings


class JobDispatcher(Protocol):
    def enqueue(self, job_id: uuid.UUID) -> None: ...


class RedisJobDispatcher:
    queue_name = "visual-workbench:generation-jobs"

    def __init__(self) -> None:
        self.client = Redis.from_url(get_settings().redis_url, decode_responses=True)

    def enqueue(self, job_id: uuid.UUID) -> None:
        self.client.rpush(self.queue_name, str(job_id))


def get_job_dispatcher() -> JobDispatcher:
    return RedisJobDispatcher()

