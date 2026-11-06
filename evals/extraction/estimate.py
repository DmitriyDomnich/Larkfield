import io
import json

from PIL import Image

from app.extraction.pages import PageImage
from app.extraction.prompts import SYSTEM_PROMPT, USER_INSTRUCTION, extraction_tools
from evals.extraction.models import EvalDocument, TokenUsage

# anthropic's image token estimate: pixels / 750, images resized down to about 1.15 megapixels
IMAGE_PIXELS_PER_TOKEN = 750
MAX_IMAGE_PIXELS = 1_150_000
CHARS_PER_TOKEN = 4
TOOL_USE_OVERHEAD_TOKENS = 350
OUTPUT_OVERHEAD_TOKENS = 300


def prompt_tokens() -> int:
    tools = json.dumps(extraction_tools())
    chars = len(SYSTEM_PROMPT) + len(USER_INSTRUCTION) + len(tools)
    return chars // CHARS_PER_TOKEN + TOOL_USE_OVERHEAD_TOKENS


def image_tokens(page: PageImage) -> int:
    with Image.open(io.BytesIO(page.data)) as image:
        width, height = image.size
    return min(width * height, MAX_IMAGE_PIXELS) // IMAGE_PIXELS_PER_TOKEN


def estimate_usage(document: EvalDocument) -> TokenUsage:
    if not document.pages:
        return TokenUsage()
    label_chars = len(document.label.model_dump_json()) if document.label else 0
    return TokenUsage(
        input_tokens=prompt_tokens() + sum(image_tokens(page) for page in document.pages),
        output_tokens=label_chars // CHARS_PER_TOKEN + OUTPUT_OVERHEAD_TOKENS,
    )
