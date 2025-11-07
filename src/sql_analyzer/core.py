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
    subquery_count: int
    complexity_score: int
    risks: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_read_only(self) -> bool:
        return self.statement_type == "SELECT"


@dataclass(frozen=True)
class OptimizationHint:
    hint: str
    detail: str


class SqlQueryAnalyzer:
    def __init__(self, dialect: str = "postgres") -> None:
        self._dialect = dialect

    def analyze(self, sql: str) -> QueryAnalysis:
        try:
            expression = sqlglot.parse_one(sql, read=self._dialect)
        except Exception as exc:
            raise AnalyzerError(f"parse failure: {exc}") from exc

        statement_type = type(expression).__name__.upper()
        tables = self._collect_tables(expression)
        where_columns = tuple(sorted({
            col.name for col in expression.find_all(exp.Column)
            if col.find_ancestor(exp.Where)
        }))
        select_columns = tuple(
            col.name for col in expression.find_all(exp.Column)
            if col.find_ancestor(exp.Select) and not col.find_ancestor(exp.Where)
        )
        return QueryAnalysis(
            statement_type=statement_type,
            tables=tuple(tables),
            where_columns=where_columns,
            select_columns=select_columns,
            has_aggregate=any(True for _ in expression.find_all(exp.AggFunc)),
            has_group_by=expression.find(exp.Group) is not None,
            has_order_by=expression.find(exp.Order) is not None,
            limit=self._extract_limit(expression),
            cte_count=len(list(expression.find_all(exp.CTE))),
            subquery_count=len(list(expression.find_all(exp.Subquery))),
            complexity_score=self._complexity(expression),
            risks=self._detect_risks(sql),
        )

