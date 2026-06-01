from typing import Any, Callable
from dataclasses import dataclass, field


@dataclass
class SignalResult:
    ticker: str
    score: float
    details: dict = field(default_factory=dict)


@dataclass
class SignalDef:
    name: str
    tier: int
    fetch_fn: Callable
    weight: float
    weight_ceiling: float = 1.0

    def run(self, tickers, config):
        try:
            candidates = self.fetch_fn(tickers, config)
            return [SignalResult(ticker=c["ticker"], score=c.get("score", 0), details=c) for c in (candidates or [])]
        except Exception:
            return []


ARCH_DIMS_ORDERED = [
    "valuation", "insider", "fund_13f", "social", "catalyst", "technicals", "niche",
    "short_interest", "earnings", "financial_health", "analyst_targets",
    "institutional", "dividend_quality", "seasonality", "macro_exposure",
]
