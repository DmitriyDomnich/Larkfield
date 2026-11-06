# Extraction eval — 2026-11-06 16:59 UTC

- Model: `eu.anthropic.claude-sonnet-4-6`
- Documents: 30 (29 labelled)
- Concurrency: 1
- Prices (USD per million tokens): input 3.30, output 16.50

## Summary

| Metric | Value |
| --- | --- |
| Documents with every field correct | 27/29 (93.1%) |
| E10 failed with a reason | yes |
| Cost per document | $0.025692 |
| Total cost (estimated before run) | $0.770755 ($0.604600) |
| Documents needing more than one attempt | 2 |
| Tokens in / out | 132762 / 20160 |
| Latency p50 / p95 | 3.9 s / 20.9 s |

## Per-field accuracy

| Field | Correct |
| --- | --- |
| document_type | 29/29 (100.0%) |
| vendor_name | 29/29 (100.0%) |
| vendor_tax_id | 29/29 (100.0%) |
| document_number | 29/29 (100.0%) |
| document_date | 29/29 (100.0%) |
| document_time | 29/29 (100.0%) |
| currency | 29/29 (100.0%) |
| line_items | 28/29 (96.6%) |
| subtotal | 29/29 (100.0%) |
| tax_amount | 29/29 (100.0%) |
| tip_amount | 29/29 (100.0%) |
| total | 29/29 (100.0%) |
| category | 27/29 (93.1%) |

## Mismatches

| Doc | Field | Expected | Got |
| --- | --- | --- | --- |
| D20 | category | training | other |
| E01 | line_items | 45 items | 45 items<br>unit_price differs on 4: Briefumschläge C4, 250 Stück: 21.50 vs null; Toner farbig, Set CMY, LX-500: 142.00 vs null; Akten-Vernichtungsbeutel, 50 Stück: 12.40 vs null; and 1 more |
| E01 | category | other | accessories |

## Per document

| Doc | Outcome | Fields correct | Attempts | Latency | Tokens in / out | Cost | Detail |
| --- | --- | --- | --- | --- | --- | --- | --- |
| D01 | extracted | 13/13 (100.0%) | 1 | 3.9 s | 3788 / 413 | $0.019315 |  |
| D02 | extracted | 13/13 (100.0%) | 1 | 4.6 s | 3798 / 499 | $0.020767 |  |
| D03 | extracted | 13/13 (100.0%) | 1 | 4.7 s | 3648 / 585 | $0.021691 |  |
| D04 | extracted | 13/13 (100.0%) | 1 | 4.6 s | 3592 / 546 | $0.020863 |  |
| D05 | extracted | 13/13 (100.0%) | 1 | 3.8 s | 3799 / 421 | $0.019483 |  |
| D06 | extracted | 13/13 (100.0%) | 1 | 2.9 s | 3802 / 295 | $0.017414 |  |
| D07 | extracted | 13/13 (100.0%) | 1 | 3.9 s | 3802 / 371 | $0.018668 |  |
| D08 | extracted | 13/13 (100.0%) | 1 | 4.0 s | 3788 / 370 | $0.018605 |  |
| D09 | extracted | 13/13 (100.0%) | 1 | 3.9 s | 3799 / 399 | $0.019120 |  |
| D10 | extracted | 13/13 (100.0%) | 1 | 4.2 s | 3799 / 415 | $0.019384 |  |
| D11 | extracted | 13/13 (100.0%) | 1 | 3.6 s | 3778 / 360 | $0.018407 |  |
| D12 | extracted | 13/13 (100.0%) | 1 | 4.1 s | 3778 / 372 | $0.018605 |  |
| D13 | extracted | 13/13 (100.0%) | 1 | 3.7 s | 3816 / 372 | $0.018731 |  |
| D14 | extracted | 13/13 (100.0%) | 1 | 3.4 s | 3799 / 363 | $0.018526 |  |
| D15 | extracted | 13/13 (100.0%) | 1 | 3.7 s | 3799 / 366 | $0.018576 |  |
| D16 | extracted | 13/13 (100.0%) | 1 | 5.8 s | 3814 / 638 | $0.023113 |  |
| D17 | extracted | 13/13 (100.0%) | 1 | 4.3 s | 3816 / 413 | $0.019407 |  |
| D18 | extracted | 13/13 (100.0%) | 1 | 3.8 s | 3778 / 367 | $0.018523 |  |
| D19 | extracted | 13/13 (100.0%) | 1 | 3.6 s | 3799 / 434 | $0.019698 |  |
| D20 | extracted | 12/13 (92.3%) | 1 | 3.8 s | 3812 / 357 | $0.018470 |  |
| E01 | extracted | 11/13 (84.6%) | 2 | 30.4 s | 13561 / 4266 | $0.115140 |  |
| E02 | extracted | 13/13 (100.0%) | 2 | 20.9 s | 13067 / 2982 | $0.092324 |  |
| E03 | extracted | 13/13 (100.0%) | 1 | 15.0 s | 5353 / 1884 | $0.048751 |  |
| E04 | extracted | 13/13 (100.0%) | 1 | 3.9 s | 3802 / 428 | $0.019609 |  |
| E05 | extracted | 13/13 (100.0%) | 1 | 3.6 s | 3778 / 442 | $0.019760 |  |
| E06 | extracted | 13/13 (100.0%) | 1 | 3.6 s | 3519 / 421 | $0.018559 |  |
| E07 | extracted | 13/13 (100.0%) | 1 | 3.5 s | 3328 / 366 | $0.017021 |  |
| E08 | extracted | 13/13 (100.0%) | 1 | 3.8 s | 3788 / 383 | $0.018820 |  |
| E09 | extracted | 13/13 (100.0%) | 1 | 4.2 s | 3784 / 493 | $0.020622 |  |
| E10 | unreadable | - | 1 | 2.4 s | 3178 / 139 | $0.012781 | The receipt is cut off at the bottom: the amount for "Müsli-Becher" is missing, and the subtotal, tax and total are not visible. Please provide a complete image of the receipt |
