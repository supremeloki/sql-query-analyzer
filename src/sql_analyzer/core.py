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

    @staticmethod
    def _collect_tables(expression: exp.Expression) -> list[TableAccess]:
        accesses: dict[str, TableAccess] = {}
        for node in expression.find_all(exp.Table):
            name = node.name
            joined = node.find_ancestor(exp.Join) is not None
            if name not in accesses:
                accesses[name] = TableAccess(table=name, operation="read", joined=joined)
            elif joined:
                accesses[name] = TableAccess(table=name, operation="read", joined=True)
        for node in expression.find_all(exp.Insert):
            target = node.find(exp.Table)
            if target is not None and target.name in accesses:
                old = accesses[target.name]
                accesses[target.name] = TableAccess(old.table, "write", old.joined)
        if not accesses:
            raise UnsupportedStatementError("no table references found")
        return list(accesses.values())

    @staticmethod
    def _extract_limit(expression: exp.Expression) -> int | None:
        limit_node = expression.find(exp.Limit)
        if limit_node is None:
            return None
        literal = limit_node.find(exp.Literal)
        if literal is None:
            return None
        try:
            return int(str(literal.this))
        except ValueError:
            return None

    @staticmethod
    def _complexity(expression: exp.Expression) -> int:
        score = 1
        score += len(list(expression.find_all(exp.Join))) * 3
        score += len(list(expression.find_all(exp.Subquery))) * 4
        score += len(list(expression.find_all(exp.CTE))) * 2
        score += 2 if expression.find(exp.Group) else 0
        score += 1 if expression.find(exp.Order) else 0
        score += len(list(expression.find_all(exp.Case))) * 2
        score += len(list(expression.find_all(exp.Window)))
        return score

    @staticmethod
    def _detect_risks(sql: str) -> tuple[str, ...]:
        return tuple(name for name, pattern in RISK_PATTERNS if pattern.search(sql))


@dataclass(frozen=True)
class IndexSuggestion:
    columns: tuple[str, ...]
    reason: str


class IndexAdvisor:
    def __init__(self, existing_indexes: dict[str, set[str]] | None = None) -> None:
        self._existing = {
            table: {c.lower() for c in cols}
            for table, cols in (existing_indexes or {}).items()
        }

    def suggest(self, analysis: QueryAnalysis) -> list[IndexSuggestion]:
        suggestions: list[IndexSuggestion] = []
        if not analysis.where_columns:
            return suggestions
        primary_table = analysis.tables[0].table if analysis.tables else "unknown"
        already = self._existing.get(primary_table.lower(), set())
        needed = [c for c in analysis.where_columns if c.lower() not in already]
        if needed:
            suggestions.append(IndexSuggestion(
                columns=tuple(needed),
                reason=f"WHERE filters on {needed} without covering index on {primary_table}",
            ))
        if analysis.complexity_score >= 10:
            suggestions.append(IndexSuggestion(
                columns=("__review__",),
                reason=f"complexity score {analysis.complexity_score} warrants manual plan review",
            ))
        return suggestions
