from pydantic import Field

from app.core.config import Settings


class WorkerSettings(Settings):
    extraction_queue_url: str = Field(min_length=1)
    bedrock_model_id: str = Field(min_length=1)

    extraction_max_receives: int = 3
    extraction_max_pages: int = 10
