import io
import json
from typing import Any

from app.core.metrics import ClaimMetrics


class RecordingMetrics(ClaimMetrics):
    """The real EMF lines, written to a buffer instead of stdout"""

    def __init__(self) -> None:
        self.output = io.StringIO()
        super().__init__("test", self.output)

    def lines(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.output.getvalue().splitlines()]

    def values(self, metric_name: str) -> list[tuple[str, str, int]]:
        """(stage, claim_id, value) of every line that carries the metric"""
        return [
            (line["Stage"], line["claim_id"], line[metric_name])
            for line in self.lines()
            if metric_name in line
        ]
