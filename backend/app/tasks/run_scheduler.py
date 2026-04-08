"""Standalone scheduler entrypoint — runs as a separate process.

Usage: python -m app.tasks.run_scheduler
This prevents duplicate job execution when running multi-worker gunicorn.
"""

import asyncio
import logging
import signal
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


async def main():
    from app.tasks.scheduler import start_scheduler, stop_scheduler

    logger.info("Starting standalone scheduler process...")
    start_scheduler()

    stop_event = asyncio.Event()

    def _shutdown(sig, frame):
        logger.info("Received signal %s, shutting down scheduler...", sig)
        stop_event.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        await stop_event.wait()
    finally:
        stop_scheduler()
        logger.info("Scheduler stopped cleanly.")


if __name__ == "__main__":
    asyncio.run(main())
