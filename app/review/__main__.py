import asyncio

from app.review.worker import run_worker

if __name__ == "__main__":
    asyncio.run(run_worker())
