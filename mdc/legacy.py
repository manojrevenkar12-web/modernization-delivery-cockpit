"""The legacy side: JPetStore's own SQL, unchanged, on an in-process database.

The MyBatis mapper XML files are parsed as they ship. Each statement keeps its SQL
text; `#{name}` and `#{name,jdbcType=X}` placeholders become named parameters and
`<bind>` elements are evaluated the way JPetStore defines them. The schema and seed
data are JPetStore's HSQLDB scripts, loaded into SQLite with two adjustments that
keep HSQLDB's semantics (both are recorded in `ADJUSTMENTS`):

  - DECIMAL columns are stored as text and read back as `Decimal`, because SQLite
    would otherwise store them as binary floating point;
  - LIKE is made case sensitive, as it is in HSQLDB.
"""

from __future__ import annotations

import re
import sqlite3
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JPETSTORE = ROOT / "legacy" / "jpetstore"
ADJUSTMENTS = [
    "DECIMAL(p,s) columns stored as TEXT and returned as Decimal (SQLite has no exact decimal type)",
    "PRAGMA case_sensitive_like = ON (HSQLDB's LIKE is case sensitive, SQLite's is not by default)",
]
PLACEHOLDER = re.compile(r"#\{\s*([\w.]+)\s*(?:,[^}]*)?\}")
DECIMAL_COLUMN = re.compile(r"\bdecimal\s*\(\s*\d+\s*,\s*\d+\s*\)", re.I)


@dataclass(frozen=True)
class Statement:
    mapper: str
    id: str
    kind: str                     # select | insert | update | delete
    sql: str                      # with :named parameters
    params: tuple[str, ...]
    binds: dict = field(default_factory=dict)   # name -> source property (boolean to 1/0)
    result_type: str = ""

    @property
    def key(self) -> str:
        return f"{self.mapper}.{self.id}"


def _strip_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_mapper(path: Path) -> list[Statement]:
    root = ET.parse(path).getroot()
    mapper = root.get("namespace", path.stem).rsplit(".", 1)[-1]
    out = []
    for el in root:
        if el.tag not in ("select", "insert", "update", "delete"):
            continue
        binds = {}
        text = el.text or ""
        for child in el:
            if child.tag == "bind":
                # JPetStore binds booleans: value="_parameter.isListOption() ? 1 : 0"
                m = re.search(r"is(\w+)\(\)", child.get("value", ""))
                prop = (m.group(1)[0].lower() + m.group(1)[1:]) if m else child.get("name")
                binds[child.get("name")] = prop
            else:
                raise ValueError(f"{path.name}:{el.get('id')}: dynamic SQL <{child.tag}> is not supported")
            text += child.tail or ""
        params = tuple(dict.fromkeys(PLACEHOLDER.findall(text)))
        sql = PLACEHOLDER.sub(lambda m: ":" + m.group(1).replace(".", "_"), text)
        out.append(Statement(mapper, el.get("id"), el.tag, _strip_ws(sql), params, binds,
                             el.get("resultType", "")))
    return out


def load_statements(mapper_dir: Path = JPETSTORE / "mapper") -> dict[str, Statement]:
    stmts = {}
    for path in sorted(mapper_dir.glob("*.xml")):
        for s in parse_mapper(path):
            stmts[s.id] = s
    return stmts


def _schema_sql(path: Path) -> str:
    text = path.read_text()
    text = re.sub(r"--[^\n]*", "", text)
    return DECIMAL_COLUMN.sub("TEXT", text)


def _decimal_columns(path: Path) -> set[tuple[str, str]]:
    cols, table = set(), None
    for line in path.read_text().splitlines():
        m = re.match(r"\s*create table (\w+)", line, re.I)
        if m:
            table = m.group(1).lower()
        m = re.match(r"\s*(\w+)\s+decimal", line, re.I)
        if m and table:
            cols.add((table, m.group(1).lower()))
    return cols


class LegacyDatabase:
    """JPetStore's schema and seed data in SQLite, and its mapper statements."""

    def __init__(self, root: Path = JPETSTORE):
        self.statements = load_statements(root / "mapper")
        schema = root / "database" / "jpetstore-hsqldb-schema.sql"
        self.decimal_columns = _decimal_columns(schema)
        # Autocommit; the service opens a savepoint where Java has @Transactional.
        self.conn = sqlite3.connect(":memory:", isolation_level=None)
        self.in_transaction = False
        self.conn.execute("PRAGMA case_sensitive_like = ON")
        self.conn.executescript(_schema_sql(schema))
        data = re.sub(r"--[^\n]*", "", (root / "database" / "jpetstore-hsqldb-dataload.sql").read_text())
        self.conn.executescript(data)
        self.calls: dict[str, int] = {}

    def table_rows(self, table: str) -> list[dict]:
        cur = self.conn.execute(f"SELECT * FROM {table}")
        names = [d[0].lower() for d in cur.description]
        return [self._typed(table, dict(zip(names, row))) for row in cur.fetchall()]

    def _typed(self, table: str, row: dict) -> dict:
        for col in list(row):
            if (table, col) in self.decimal_columns and row[col] is not None:
                row[col] = Decimal(str(row[col]))
        return row

    def run(self, statement_id: str, params: dict | None = None):
        """Execute one mapper statement the way MyBatis would. Selects return rows as
        {property: value} with MyBatis' case-insensitive property names lower-cased."""
        s = self.statements[statement_id]
        self.calls[statement_id] = self.calls.get(statement_id, 0) + 1
        args = dict(params or {})
        for name, prop in s.binds.items():
            args[name] = 1 if args.get(prop) else 0
        bound = {p.replace(".", "_"): _to_sql(args.get(p)) for p in s.params}
        if s.kind == "select":
            cur = self.conn.execute(s.sql, bound)
            names = [d[0].lower() for d in cur.description]
            rows = [dict(zip(names, r)) for r in cur.fetchall()]
            return [self._decimals(r) for r in rows]
        return self.conn.execute(s.sql, bound).rowcount

    def _decimals(self, row: dict) -> dict:
        money = {"listprice", "unitcost", "unitprice", "totalprice"}
        return {k: (Decimal(str(v)) if k in money and v is not None else v) for k, v in row.items()}


def _to_sql(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bool):
        return int(value)
    return value
