"""Analysis: read the legacy application and turn it into scope, findings and work.

From the MyBatis mappers, the DDL and the Java services it derives:

  - per statement: tables read and written, joins, ORDER BY, LIKE, and the
    inner joins that can hide rows;
  - per service method: the statements it runs and whether it is @Transactional;
  - findings: risks and issues the delivery has to decide on, each with the
    evidence that raised it (rules below, no hand-written list);
  - work packages: statements grouped by the business capability they serve,
    with the size drivers the estimate uses.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from mdc.legacy import JPETSTORE, ROOT, Statement, load_statements

CONFIG = ROOT / "config"
TABLE = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE)\s+([\w,\s]+?)(?:\bWHERE\b|\bSET\b|\(|\bVALUES\b|\bORDER\b|$)", re.I)
# Where each legacy table lives in the document model (see mdc.modern).
TARGET = {"account": "accounts", "profile": "accounts", "signon": "accounts", "bannerdata": "banners",
          "category": "categories", "product": "products", "item": "items", "inventory": "items",
          "orders": "orders", "orderstatus": "orders", "lineitem": "orders", "sequence": "sequences",
          "supplier": "suppliers"}


@dataclass
class StatementFacts:
    id: str
    mapper: str
    kind: str
    tables: list[str]
    joins: int
    order_by: bool
    like: bool
    writes: bool


@dataclass
class ServiceMethod:
    service: str
    method: str
    transactional: bool
    statements: list[str]


@dataclass
class Finding:
    id: str
    kind: str            # risk | issue
    severity: str        # high | medium | low
    title: str
    evidence: str
    action: str
    statements: list[str] = field(default_factory=list)
    data: bool = False          # about the data itself (belongs to the migration work package)


@dataclass
class WorkPackage:
    id: str
    name: str
    statements: list[str]
    drivers: dict
    findings: list[str] = field(default_factory=list)
    points: float = 0.0


def statement_facts(s: Statement) -> StatementFacts:
    tables: list[str] = []
    for m in TABLE.finditer(s.sql):
        for t in m.group(1).split(","):
            name = t.strip().split()[0].lower() if t.strip() else ""
            if name and name not in tables:
                tables.append(name)
    from_part = re.search(r"\bFROM\b(.*?)(\bWHERE\b|$)", s.sql, re.I)
    joins = (from_part.group(1).count(",") if from_part else 0) + len(re.findall(r"\bJOIN\b", s.sql, re.I))
    return StatementFacts(s.id, s.mapper, s.kind, tables, joins, bool(re.search(r"\bORDER BY\b", s.sql, re.I)),
                          bool(re.search(r"\bLIKE\b", s.sql, re.I)), s.kind != "select")


def service_methods(java_dir: Path = JPETSTORE / "java" / "org" / "mybatis" / "jpetstore" / "service") -> list[ServiceMethod]:
    out = []
    for path in sorted(java_dir.glob("*Service.java")):
        text = path.read_text()
        for m in re.finditer(r"((?:@\w+\s*)*)public\s+[\w<>, ]+\s+(\w+)\s*\([^)]*\)\s*\{", text):
            start = m.end()
            depth, i = 1, start
            while depth and i < len(text):
                depth += {"{": 1, "}": -1}.get(text[i], 0)
                i += 1
            body = text[start:i]
            calls = list(dict.fromkeys(re.findall(r"\w+Mapper\.(\w+)\(", body)))
            # Calls to sibling methods of the same service (getNextId) count too.
            for sibling in re.findall(r"\b(getNextId)\(", body):
                calls += [c for c in ("getSequence", "updateSequence") if c not in calls]
            out.append(ServiceMethod(path.stem, m.group(2), "@Transactional" in m.group(1), calls))
    return [s for s in out if s.statements]


def findings(facts: dict[str, StatementFacts], methods: list[ServiceMethod], schema_text: str) -> list[Finding]:
    out: list[Finding] = []
    n = 0

    def add(kind, sev, title, evidence, action, statements=(), data=False):
        nonlocal n
        if any(f.title == title for f in out):
            return
        n += 1
        out.append(Finding(f"F{n:02d}", kind, sev, title, evidence, action, list(statements), data))

    for m in methods:
        written = {TARGET[t] for s in m.statements if facts[s].writes for t in facts[s].tables if t in TARGET}
        if m.transactional and len(written) > 1:
            add("risk", "high", f"{m.service}.{m.method} writes {len(written)} collections in one transaction",
                f"@Transactional; writes {', '.join(sorted(written))} via {', '.join(m.statements)}",
                "Needs a multi-document transaction (replica set, as on Atlas) or a redesign so the "
                "write lands in one document; agree which with the customer architect",
                [x for x in m.statements if facts[x].writes])
    for m in methods:
        reads = [s for s in m.statements if facts[s].kind == "select" and "sequence" in facts[s].tables]
        writes = [s for s in m.statements if facts[s].writes and "sequence" in facts[s].tables]
        if reads and writes:
            add("risk", "high", "Order ids come from a read-then-write sequence",
                f"{m.service} reads {reads[0]} then writes {writes[0]} with no lock: two concurrent orders can get the same id",
                "Replace with an atomic findOneAndUpdate($inc); confirm the id format stays the same for the customer's reports",
                reads + writes)
    if re.search(r"create table signon[^;]*password", schema_text, re.I):
        add("issue", "high", "Passwords are stored in plain text", "SIGNON.PASSWORD is varchar(25), compared directly in SQL",
            "Out of scope for a like-for-like migration: raise with the customer's security lead and agree a "
            "hashing change as a separate, tested step",
            [f.id for f in facts.values() if "signon" in f.tables])
    hidden = [f for f in facts.values() if f.kind == "select" and f.joins > 0]
    if hidden:
        add("risk", "medium", f"{len(hidden)} reads use inner joins that hide rows",
            "e.g. " + ", ".join(sorted(f.id for f in hidden)[:4]) + ": a missing profile, banner, status or inventory row drops the result",
            "Keep the legacy behaviour unless the customer decides otherwise; parity tests pin it",
            [f.id for f in hidden])
    likes = [f.id for f in facts.values() if f.like]
    if likes:
        add("risk", "medium", "Search passes user input into SQL LIKE", f"{', '.join(likes)}: % and _ typed by a user are wildcards",
            "Translate LIKE exactly (anchored regex on a lower-cased copy of the name, indexed); flag the wildcard behaviour to the product owner",
            likes)
    if re.search(r"decimal\s*\(", schema_text, re.I):
        add("risk", "medium", "Money columns are DECIMAL", "listprice, unitcost, unitprice, totalprice are decimal(10,2)",
            "Store as Decimal128, never as double; reconcile totals after the data migration", data=True)
    orphan_tables = [t for t in ("lineitem", "orderstatus", "inventory") if not re.search(
        rf"create table {t}\b[^;]*foreign key", schema_text, re.I | re.S)]
    if orphan_tables:
        add("risk", "low", "Child tables have no foreign keys", f"{', '.join(orphan_tables)} can hold orphan rows",
            "Count orphans in the customer's production copy before migration; agree whether to drop or quarantine them",
            data=True)
    return out


CAPABILITIES = [
    ("WP1", "Catalogue browsing and search", ["CategoryMapper", "ProductMapper"], ["getItemListByProduct", "getItem"]),
    ("WP2", "Accounts and sign-in", ["AccountMapper"], []),
    ("WP3", "Order placement", [], ["insertOrder", "insertOrderStatus", "insertLineItem", "updateInventoryQuantity"]),
    ("WP4", "Order history", [], ["getOrder", "getOrdersByUsername", "getLineItemsByOrderId"]),
    ("WP5", "Stock and id generation", ["SequenceMapper"], ["getInventoryQuantity"]),
]


def work_packages(facts: dict[str, StatementFacts], found: list[Finding], weights: dict) -> list[WorkPackage]:
    wps = []
    for wid, name, mappers, extra in CAPABILITIES:
        ids = [f.id for f in facts.values() if f.mapper in mappers] + extra
        ids = list(dict.fromkeys(i for i in ids if i in facts))
        tables = {t for i in ids for t in facts[i].tables}
        drivers = {"statements": len(ids), "writes": sum(facts[i].writes for i in ids),
                   "joins": sum(facts[i].joins for i in ids), "tables": len(tables)}
        linked = [f.id for f in found if set(f.statements) & set(ids)]
        wps.append(WorkPackage(wid, name, ids, drivers, linked))
    tables_total = len(TARGET)
    wps.append(WorkPackage("WP6", "Data migration and reconciliation", [],
                           {"statements": 0, "writes": 0, "joins": 0, "tables": tables_total},
                           [f.id for f in found if f.data]))
    wps.append(WorkPackage("WP7", "Cut-over rehearsal and hypercare", [],
                           {"statements": 0, "writes": 0, "joins": 0, "tables": 0}, []))
    for wp in wps:
        d = wp.drivers
        wp.points = round(weights["base"] + weights["statement"] * d["statements"] + weights["write"] * d["writes"]
                          + weights["join"] * d["joins"] + weights["table"] * d["tables"]
                          + weights["finding"] * len(wp.findings), 1)
    return wps


def analyse(root: Path = JPETSTORE) -> dict:
    stmts = load_statements(root / "mapper")
    facts = {s.id: statement_facts(s) for s in stmts.values()}
    methods = service_methods(root / "java" / "org" / "mybatis" / "jpetstore" / "service")
    schema = (root / "database" / "jpetstore-hsqldb-schema.sql").read_text()
    found = findings(facts, methods, schema)
    weights = json.loads((CONFIG / "delivery.json").read_text())["estimate_weights"]
    wps = work_packages(facts, found, weights)
    tables = sorted({t.lower() for t in re.findall(r"create table (\w+)", schema, re.I)})
    java_files = list((root / "java").rglob("*.java"))
    return {
        "inventory": {"java_files": len(java_files), "java_lines": sum(len(p.read_text().splitlines()) for p in java_files),
                      "tables": len(tables), "statements": len(facts),
                      "writes": sum(f.writes for f in facts.values()),
                      "joins": sum(f.joins for f in facts.values()),
                      "transactional_methods": sum(m.transactional for m in methods)},
        "statements": {k: asdict(v) for k, v in facts.items()},
        "service_methods": [asdict(m) for m in methods],
        "findings": [asdict(f) for f in found],
        "work_packages": [asdict(w) for w in wps],
    }
