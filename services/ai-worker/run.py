"""Redis consumer for the environment-selected image generation provider."""

import uuid

from app.assets.storage import S3ObjectStorage
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.jobs.queue import RedisJobDispatcher
from app.jobs.worker import GenerationWorker
from redis import Redis


def run_forever() -> None:
    redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    while True:
        item = redis.blpop(RedisJobDispatcher.queue_name, timeout=5)
        if item is None:
            continue
        _, raw_job_id = item
        with SessionLocal() as session:
            GenerationWorker(session, S3ObjectStorage()).process(uuid.UUID(raw_job_id))


if __name__ == "__main__":
    run_forever()
