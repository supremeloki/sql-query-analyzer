import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from sql_analyzer import (
    AnalyzerError,
    IndexAdvisor,
    SqlQueryAnalyzer,
)


@pytest.fixture
def analyzer():
    return SqlQueryAnalyzer(dialect="postgres")


def test_simple_select_analysis(analyzer):
    analysis = analyzer.analyze("SELECT id, name FROM users")
    assert analysis.statement_type == "SELECT"
    assert analysis.is_read_only
    assert analysis.tables[0].table == "users"
    assert not analysis.has_aggregate


def test_where_columns_extracted(analyzer):
    analysis = analyzer.analyze(
        "SELECT name FROM users WHERE age > 30 AND city = 'Tehran'"
    )
    assert set(analysis.where_columns) == {"age", "city"}


def test_join_detected(analyzer):
    analysis = analyzer.analyze(
        "SELECT u.name FROM users u JOIN orders o ON o.user_id = u.id"
    )
    joined_tables = {t.table for t in analysis.tables if t.joined}
    assert "orders" in joined_tables
    assert analysis.complexity_score >= 4


def test_aggregate_and_group_by(analyzer):
    analysis = analyzer.analyze(
        "SELECT region, COUNT(*) FROM sales GROUP BY region ORDER BY total DESC LIMIT 10"
    )
    assert analysis.has_aggregate
    assert analysis.has_group_by
    assert analysis.has_order_by
    assert analysis.limit == 10


def test_cte_counted(analyzer):
    analysis = analyzer.analyze(
        """
        WITH active AS (
            SELECT * FROM users WHERE status = 'active'
        )
        SELECT * FROM active
        """
    )
    assert analysis.cte_count == 1


def test_insert_marks_write_operation(analyzer):
    analysis = analyzer.analyze("INSERT INTO archive SELECT * FROM logs")
    write_rows = [t for t in analysis.tables if t.operation == "write"]
    assert any(t.table == "archive" for t in write_rows)
    assert not analysis.is_read_only


def test_select_star_risk_flagged(analyzer):
    analysis = analyzer.analyze("SELECT * FROM wide_table")
    assert "select_star" in analysis.risks


def test_parse_failure_raises(analyzer):
    with pytest.raises(AnalyzerError):
        analyzer.analyze("THIS IS NOT SQL AT ALL !!!")


def test_complexity_scores_ordered():
    simple = SqlQueryAnalyzer().analyze("SELECT a FROM t")
    complex_query = SqlQueryAnalyzer().analyze(
        """
        WITH c AS (SELECT * FROM base)
        SELECT c.a, x.b, SUM(x.c) OVER (PARTITION BY c.a) AS run
        FROM c JOIN extra x ON x.id = c.id
        WHERE c.flag = true
        GROUP BY c.a, x.b
        ORDER BY run DESC
        """
    )
    assert complex_query.complexity_score > simple.complexity_score


def test_index_advisor_suggests_where_columns():
    advisor = IndexAdvisor(existing_indexes={"users": {"id"}})
    analysis = SqlQueryAnalyzer().analyze(
        "SELECT name FROM users WHERE email = 'x' AND id = 5"
    )
