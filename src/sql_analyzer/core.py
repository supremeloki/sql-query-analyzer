from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Sequence

import sqlglot
from sqlglot import exp


class AnalyzerError(Exception):
    pass


class UnsupportedStatementError(AnalyzerError):
    pass


RISK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("cartesian_join", re.compile(r"\bFROM\s+\w+\s*,\s*\w+", re.IGNORECASE)),
    ("implicit_cast", re.compile(r"\bWHERE\s+\w+\s*=\s*'", re.IGNORECASE)),
    ("select_star", re.compile(r"SELECT\s+\*", re.IGNORECASE)),
)


@dataclass(frozen=True)
class TableAccess:
    table: str
    operation: str
    joined: bool


@dataclass(frozen=True)
class QueryAnalysis:
    statement_type: str
    tables: tuple[TableAccess, ...]
    where_columns: tuple[str, ...]
    select_columns: tuple[str, ...]
    has_aggregate: bool
    has_group_by: bool
    has_order_by: bool
    limit: int | None
    cte_count: int
