"""Data models for screener using Pydantic."""

from pydantic import BaseModel, Field
from typing import Optional, Literal
from enum import Enum


class CriterionType(str, Enum):
    """Type of screening criterion."""
    FUNDAMENTAL = "fundamental"
    TECHNICAL = "technical"


class Operator(str, Enum):
    """Comparison operators."""
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    EQ = "=="
    NE = "!="


class CriterionConfig(BaseModel):
    """Single screening criterion from config."""
    type: CriterionType
    metric: str
    operator: Operator
    value: float


class ScreenerConfig(BaseModel):
    """Main screener configuration."""
    market: str
    universe: dict
    criteria: list[CriterionConfig]
    ranking: dict[str, float] = Field(default_factory=dict)
    news: dict = Field(default_factory=lambda: {"enabled": False})
    output: dict = Field(default_factory=lambda: {"format": ["markdown"], "max_results": 50})


class FilterResult(BaseModel):
    """Result of filtering a single stock."""
    symbol: str
    passed: bool
    scores: dict[str, float] = Field(default_factory=dict)
    failures: list[str] = Field(default_factory=list)
    rank_score: Optional[float] = None


class StockScore(BaseModel):
    """Component scores for a stock."""
    value_score: float = 0.0
    quality_score: float = 0.0
    momentum_score: float = 0.0
