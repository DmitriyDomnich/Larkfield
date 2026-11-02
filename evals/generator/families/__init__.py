from collections.abc import Callable

from app.extraction.schemas import ExtractedExpense
from evals.generator.families import airline, card_slip, fine, folio, invoice, thermal
from evals.generator.spec import Family, RenderSpec

FAMILIES: dict[Family, Callable[[ExtractedExpense, RenderSpec], bytes]] = {
    "thermal": thermal.render,
    "card_slip": card_slip.render,
    "invoice": invoice.render,
    "folio": folio.render,
    "airline": airline.render,
    "fine": fine.render,
}
