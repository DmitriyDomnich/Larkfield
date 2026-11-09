"""How a document looks. The label says what it contains; a RenderSpec says how it is printed."""

from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal
from typing import Literal

from app.extraction.schemas import ExtractedExpense

Family = Literal["thermal", "card_slip", "invoice", "folio", "airline", "fine"]
Font = Literal["Helvetica", "Times-Roman", "Courier"]
Lang = Literal["de", "en"]
# qty_desc_amount:       "2 x Espresso            7,00"
# desc_qty_price_amount: "Espresso" / "  2 x 3,50   7,00"
# desc_amount:           "Espresso                7,00" (quantity on a second line when not 1)
Columns = Literal["qty_desc_amount", "desc_qty_price_amount", "desc_amount"]
Payment = Literal["none", "cash", "card"]
# line:      "enth. MwSt 19 %  2,95" / "Netto  15,55" under the total
# table:     "MwSt % | Netto | MwSt | Brutto" table after the payment
# net_total: "MwSt-Betrag 19 %: 3,01" / "Gesamtbetrag netto: 15,84" after the payment
TaxBlock = Literal["line", "table", "net_total"]

BOLD: dict[Font, str] = {
    "Helvetica": "Helvetica-Bold",
    "Times-Roman": "Times-Bold",
    "Courier": "Courier-Bold",
}

WORDS: dict[Lang, dict[str, str]] = {
    "de": {
        "total": "SUMME",
        "items_total": "Zwischensumme",
        "subtotal": "Netto",
        "tax": "MwSt",
        "tax_included": "enth. MwSt",
        "tip": "Trinkgeld",
        "date": "Datum",
        "time": "Uhrzeit",
        "number": "Beleg-Nr.",
        "tax_id": "USt-IdNr.",
        "qty": "Menge",
        "description": "Bezeichnung",
        "unit_price": "Einzelpreis",
        "amount": "Betrag",
        "invoice": "RECHNUNG",
        "invoice_number": "Rechnungsnummer",
        "invoice_date": "Rechnungsdatum",
        "pos": "Pos.",
        "page": "Seite",
        "cash": "Barzahlung",
        "change": "Rückgeld",
        "card": "Kartenzahlung",
        "gross": "Brutto",
        "tax_amount": "MwSt-Betrag",
        "net_total": "Gesamtbetrag netto",
        "entertainment_title": "Bewirtungsbeleg",
        "entertainment_law": "Angaben nach § 4 Abs. 5 Nr. 2 EStG",
    },
    "en": {
        "total": "TOTAL",
        "items_total": "Subtotal",
        "subtotal": "Net",
        "tax": "VAT",
        "tax_included": "incl. VAT",
        "tip": "Tip",
        "date": "Date",
        "time": "Time",
        "number": "Receipt no.",
        "tax_id": "VAT no.",
        "qty": "Qty",
        "description": "Description",
        "unit_price": "Unit price",
        "amount": "Amount",
        "invoice": "INVOICE",
        "invoice_number": "Invoice number",
        "invoice_date": "Invoice date",
        "pos": "#",
        "page": "Page",
        "cash": "Cash",
        "change": "Change",
        "card": "Card payment",
        "gross": "Gross",
        "tax_amount": "VAT amount",
        "net_total": "Net total",
        "entertainment_title": "Business entertainment receipt",
        "entertainment_law": "Details per Sec. 4(5) no. 2 EStG",
    },
}


@dataclass(frozen=True)
class Photo:
    """A phone photo of the printed document"""

    angle: float
    skew: float
    light: float
    keep: float = 1.0  # fraction of the page kept from the top (a cut-off photo)


@dataclass(frozen=True)
class RenderSpec:
    family: Family
    font: Font
    lang: Lang
    date_format: str
    decimal: Literal[",", "."]
    columns: Columns
    address: tuple[str, ...]
    recipient: tuple[str, ...] = ()  # bill-to block on A4 documents
    # Extra "label: value" lines: table, guests, pickup, room, booking reference
    meta: tuple[tuple[str, str], ...] = ()
    footer: tuple[str, ...] = ()
    words: tuple[tuple[str, str], ...] = ()  # overrides WORDS for this document
    tax_rate: str | None = None  # printed next to the tax amount, e.g. "19 %"
    time_label: str | None = None  # e.g. "Fahrtbeginn" on taxi receipts
    align: Literal["left", "center", "right"] = "center"
    size: float = 8.5
    currency_symbol: str | None = None  # printed after amounts, e.g. "€"; else the code before
    # Till receipt structure
    payment: Payment = "none"
    card: str = "Visa **** 4821"
    tax_block: TaxBlock = "line"
    item_codes: bool = False  # an article-code line above each item
    datetime_at: Literal["header", "footer"] = "header"
    # Label fields written by hand under the printed receipt, in order
    handwritten: tuple[Literal["tip", "total"], ...] = ()
    # Bewirtungsbeleg under the receipt: (label, value); "" is left blank
    entertainment: tuple[tuple[str, str], ...] = ()
    photo: Photo | None = None
    # Content for a document that has no label
    data: ExtractedExpense | None = None

    def word(self, key: str) -> str:
        return dict(self.words).get(key, WORDS[self.lang][key])

    @property
    def bold(self) -> str:
        return BOLD[self.font]

    @property
    def layout_key(self) -> tuple[str | bool, ...]:
        """The structure of the document; date format, decimal separator and language don't count"""
        return (
            self.family,
            self.font,
            self.columns,
            self.payment,
            self.tax_block,
            self.item_codes,
            self.datetime_at,
        )

    def money(self, value: Decimal) -> str:
        text = f"{value:,.2f}"
        if self.decimal == ",":
            text = text.replace(",", " ").replace(".", ",").replace(" ", ".")
        return text

    def price(self, value: Decimal, currency: str) -> str:
        if self.currency_symbol:
            return f"{self.money(value)} {self.currency_symbol}"
        return f"{currency} {self.money(value)}"

    def qty(self, value: Decimal) -> str:
        if value == value.to_integral_value():
            return str(int(value))
        text = f"{value.normalize():f}"
        return text.replace(".", ",") if self.decimal == "," else text

    def date(self, value: date) -> str:
        return value.strftime(self.date_format)

    @staticmethod
    def time(value: time) -> str:
        return value.strftime("%H:%M")
