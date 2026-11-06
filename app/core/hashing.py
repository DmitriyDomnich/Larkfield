import asyncio
import hashlib


async def file_sha256(data: bytes) -> str:
    return await asyncio.to_thread(lambda: hashlib.sha256(data).hexdigest())
