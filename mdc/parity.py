"""Behavioural parity: the legacy application against the modernized one.

A workload is a seeded sequence of user journeys through JPetStore's services:
browsing, searching, signing up, logging in, editing a profile, placing orders and
reading them back. The same workload runs against the legacy SQL and against
MongoDB, each starting from the same migrated data. Every service call's result
(or error) is normalised and compared. A mapper statement counts as validated
when it ran in the workload and every call that used it agreed.

Normalisation is limited to what a user cannot see: money to two decimals, and
row order only where neither the SQL nor the service defines one.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from decimal import Decimal

from mdc.legacy import LegacyDatabase
from mdc.modern import MongoRepository, connect, migrate
from mdc.service import Failed, PetStoreService

ORDERED_OPS = {"orders_by_user"}       # SQL has ORDER BY ORDERDATE
WORDS = ["fish", "Dog", "CAT", "bird", "snake", "poodle", "angel", "shark", "koi", "gold", "finch",
         "%", "_", "a_g", "%%", ".", "(", "ä", "  dog", "fish dog", "rattle", "manx", "iguana", "lab"]


def _canon(value):
    if isinstance(value, Decimal):
        return str(value.quantize(Decimal("0.01")))
    if isinstance(value, dict):
        return {k: _canon(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [_canon(v) for v in value]
    if isinstance(value, float):
        return str(Decimal(str(value)).quantize(Decimal("0.01")))
    return value


def normalise(op: str, result):
    result = _canon(result)
    if isinstance(result, list) and op not in ORDERED_OPS:
        return sorted(result, key=lambda r: json.dumps(r, sort_keys=True, default=str))
    if op in ORDERED_OPS and isinstance(result, list):
        # ORDER BY ORDERDATE leaves ties unordered: compare within equal dates as sets.
        return sorted(result, key=lambda r: (r.get("orderdate"), json.dumps(r, sort_keys=True, default=str)))
    return result


# --------------------------------------------------------------------- workload
def generate_workload(seed: int, journeys: int, catalog: dict) -> list[dict]:
    """Seeded journeys. `catalog` lists the ids that exist (from the legacy data)."""
    rng = random.Random(seed)
    ops: list[dict] = []
    users = ["j2ee", "ACID"]
    passwords = {"j2ee": "j2ee", "ACID": "ACID"}
    cats = catalog["categories"] + ["MAMMALS"]
    products = catalog["products"] + ["XX-NONE-1"]
    items = catalog["items"] + ["EST-999"]
    day = 0
    for j in range(journeys):
        kind = rng.choices(["browse", "search", "signup", "account", "order", "history"],
                           [3, 2, 1, 1, 2, 1])[0]
        if kind == "browse":
            c = rng.choice(cats)
            ops += [{"op": "category_list"}, {"op": "category", "args": [c]}, {"op": "products_by_category", "args": [c]}]
            p = rng.choice(products)
            ops += [{"op": "product", "args": [p]}, {"op": "items_by_product", "args": [p]}]
            i = rng.choice(items)
            ops += [{"op": "item", "args": [i]}, {"op": "in_stock", "args": [i]}]
        elif kind == "search":
            words = rng.sample(WORDS, rng.randint(1, 2))
            ops.append({"op": "search", "args": [" ".join(words)]})
        elif kind == "signup":
            name = rng.choice([f"user{j}", f"user{j}", rng.choice(users)])   # sometimes a name that exists
            pw = f"pw{rng.randint(100, 999)}"
            fav = rng.choice(catalog["categories"] + [None])
            acct = _account(rng, name, pw, fav)
            ops.append({"op": "insert_account", "args": [acct]})
            if name not in users:
                users.append(name)
                passwords[name] = pw
            ops += [{"op": "get_account", "args": [name]}, {"op": "login", "args": [name, pw]}]
        elif kind == "account":
            u = rng.choice(users)
            pw = rng.choice([passwords.get(u, "x"), "wrong", ""])
            ops.append({"op": "login", "args": [u, pw]})
            new_pw = rng.choice(["", f"pw{rng.randint(100, 999)}"])
            acct = _account(rng, u, new_pw, rng.choice(catalog["categories"] + [None]))
            ops.append({"op": "update_account", "args": [acct]})
            if new_pw:
                passwords[u] = new_pw
            ops += [{"op": "get_account", "args": [u]}, {"op": "login", "args": [u, passwords.get(u, "x")]}]
        elif kind == "order":
            u = rng.choice(users)
            day += rng.randint(0, 2)
            lines = []
            for n in range(1, rng.randint(1, 4) + 1):
                item = rng.choice(catalog["items"])
                lines.append({"lineNumber": n, "itemId": item, "quantity": rng.choice([1, 1, 2, 3, 5000]),
                              "unitPrice": catalog["prices"][item]})
            total = sum(Decimal(str(li["unitPrice"])) * li["quantity"] for li in lines)
            # Orders are dated within a month, not in placement order, so ORDER BY matters.
            date = f"2026-03-{1 + rng.randint(0, 27):02d}"
            ops.append({"op": "place_order", "args": [_order(rng, u, date, total, lines)]})
            ops.append({"op": "orders_by_user", "args": [u]})
        else:
            u = rng.choice(users)
            ops.append({"op": "orders_by_user", "args": [u]})
            ops.append({"op": "get_order", "args": [rng.randint(1000, 1000 + max(1, j // 3))]})
    return ops


def _account(rng, name, password, fav):
    return {"username": name, "password": password, "email": f"{name}@example.org", "firstName": "Ada",
            "lastName": rng.choice(["Lovelace", "Hopper", "Müller"]), "status": "OK",
            "address1": f"{rng.randint(1, 99)} Main St", "address2": rng.choice([None, "Apt 2"]),
            "city": "Berlin", "state": "BE", "zip": f"{rng.randint(10000, 14999)}", "country": "DE",
            "phone": "030-555", "languagePreference": rng.choice(["english", "german"]),
            "favouriteCategoryId": fav, "listOption": rng.random() < 0.5, "bannerOption": rng.random() < 0.5}


def _order(rng, user, date, total, lines):
    addr = {"shipAddress1": "1 Ship Rd", "shipAddress2": None, "shipCity": "Berlin", "shipState": "BE",
            "shipZip": "10115", "shipCountry": "DE", "billAddress1": "2 Bill Rd", "billAddress2": "c/o",
            "billCity": "Berlin", "billState": "BE", "billZip": "10117", "billCountry": "DE"}
    return {"username": user, "orderDate": date, **addr, "courier": rng.choice(["UPS", "DHL"]),
            "totalPrice": str(total), "billToFirstName": "Ada", "billToLastName": "L", "shipToFirstName": "Ada",
            "shipToLastName": "L", "creditCard": "999 9999 9999 9999", "expiryDate": "12/03", "cardType": "Visa",
            "locale": "CA", "status": "P", "lineItems": lines}


def catalog_ids(legacy: LegacyDatabase) -> dict:
    items = legacy.table_rows("item")
    return {"categories": sorted(r["catid"] for r in legacy.table_rows("category")),
            "products": sorted(r["productid"] for r in legacy.table_rows("product")),
            "items": sorted(r["itemid"] for r in items),
            "prices": {r["itemid"]: str(r["listprice"]) for r in items}}


# ------------------------------------------------------------------------ runner
@dataclass
class ParityReport:
    operations: int = 0
    agreed: int = 0
    divergences: list[dict] = field(default_factory=list)
    statements: dict[str, dict] = field(default_factory=dict)
    migrated: dict[str, int] = field(default_factory=dict)

    @property
    def statements_validated(self) -> int:
        return sum(1 for s in self.statements.values() if s["calls"] and not s["divergent_calls"])

    def to_dict(self) -> dict:
        return {"operations": self.operations, "agreed": self.agreed,
                "divergences": self.divergences[:50], "divergence_count": len(self.divergences),
                "statements": self.statements, "statements_total": len(self.statements),
                "statements_validated": self.statements_validated, "migrated": self.migrated}


def _call(service, op: dict):
    try:
        return {"ok": getattr(service, op["op"])(*op.get("args", []))}
    except Failed as e:
        return {"error": str(e)}


def run_parity(workload: list[dict], repo_factory=MongoRepository, db=None) -> ParityReport:
    legacy = LegacyDatabase()
    db = db if db is not None else connect()
    report = ParityReport(migrated=migrate(legacy, db))
    modern = repo_factory(db)
    old, new = PetStoreService(legacy), PetStoreService(modern)
    report.statements = {s: {"calls": 0, "divergent_calls": 0} for s in legacy.statements}
    for n, op in enumerate(workload):
        before_old, before_new = dict(legacy.calls), dict(modern.calls)
        a, b = _call(old, op), _call(new, op)
        used = {k for k in legacy.calls if legacy.calls[k] != before_old.get(k, 0)}
        used |= {k for k in modern.calls if modern.calls[k] != before_new.get(k, 0)}
        same = normalise(op["op"], a) == normalise(op["op"], b)
        report.operations += 1
        for s in used:
            if s in report.statements:
                report.statements[s]["calls"] += 1
                report.statements[s]["divergent_calls"] += 0 if same else 1
        if same:
            report.agreed += 1
        else:
            report.divergences.append({"index": n, "op": op["op"], "args": json.loads(json.dumps(op.get("args", []), default=str)),
                                       "legacy": json.loads(json.dumps(normalise(op["op"], a), default=str)),
                                       "modern": json.loads(json.dumps(normalise(op["op"], b), default=str)),
                                       "statements": sorted(used)})
    return report
