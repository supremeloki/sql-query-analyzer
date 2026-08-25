# sql-analyzer

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

AST-level SQL analysis: table access mapping (read/write, joined), WHERE column extraction, complexity scoring, risk pattern detection, and index suggestions — the analysis brain for NL→SQL systems.

## 🚀 Overview

Before executing generated SQL — or tuning hand-written SQL — you need to *understand* it. `sql-analyzer` parses with sqlglot into an AST and answers the practical questions: which tables are touched and whether writes or joins are involved, which columns filter in WHERE clauses, how complex the query is on a weighted scale (joins ×3, subqueries ×4, windows, CTEs…), and which risky patterns appear (`SELECT *`, cartesian joins, implicit casts). An `IndexAdvisor` then cross-references WHERE columns against existing indexes to suggest what's missing.

## ✨ Features

- **Statement typing:** SELECT vs INSERT/UPDATE/DELETE with `is_read_only` flag
- **Table access map:** read/write operation per table + joined detection
- **Column intelligence:** WHERE-filter columns separated from projection columns
- **Complexity score:** weighted AST walk — a single number to gate expensive queries
- **Risk detection:** `select_star`, `cartesian_join`, `implicit_cast` patterns flagged
- **Index advisor:** suggests indexes on filtered columns not already covered; flags high-complexity queries for manual review
- **Zero dependencies** beyond sqlglot

## 🚧 Structure

```
sql-query-analyzer/
├── src/sql_analyzer/
│   ├── __init__.py
│   └── core.py
├── tests/
│   └── test_core.py
├── README.md
└── pyproject.toml
```

## 📦 Installation

```bash
git clone https://github.com/supremeloki/sql-query-analyzer.git
cd sql-query-analyzer
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

## 📋 Requirements

- Python 3.11+
- Runtime: `sqlglot >= 20`

## 🏃 Quick Start

```python
from sql_analyzer import IndexAdvisor, SqlQueryAnalyzer

analyzer = SqlQueryAnalyzer(dialect="postgres")
analysis = analyzer.analyze(
    "SELECT u.name FROM users u JOIN orders o ON o.user_id = u.id "
    "WHERE u.age > 30"
)
print(analysis.tables)
print(analysis.where_columns, analysis.complexity_score)

advisor = IndexAdvisor(existing_indexes={"users": {"id"}})
for suggestion in advisor.suggest(analysis):
    print(suggestion.reason)
```

## 🔧 Error Handling

```text
AnalyzerError
└── UnsupportedStatementError   # no table references found
```

Parse failures raise `AnalyzerError` with the underlying detail attached.

## 🧪 Testing

```bash
pytest tests/ -v
```

## 📝 Code Quality

- Full type hints (`X | None` style), frozen analyses/suggestions
- Zero comments — names carry the meaning
- Complexity ordering asserted between simple and heavy queries

## 📄 License

MIT — see [LICENSE](LICENSE).

## 👤 Author

**Kooroush Masoumi** - [kooroushmasoumi@gmail.com](mailto:kooroushmasoumi@gmail.com)

---

⭐ Star this repo if you find it useful!
