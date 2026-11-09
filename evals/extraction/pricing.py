from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ModelPrice:
    input_per_mtok: Decimal
    output_per_mtok: Decimal


# Geo and In-region Cross-region Inference
MODEL_PRICES: dict[str, ModelPrice] = {
    "eu.anthropic.claude-sonnet-4-6": ModelPrice(Decimal("3.30"), Decimal("16.50")),
}


def model_price(model_id: str) -> ModelPrice:
    try:
        return MODEL_PRICES[model_id]
    except KeyError:
        raise KeyError(f"no price for {model_id}; add it to MODEL_PRICES in {__name__}") from None
