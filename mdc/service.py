"""JPetStore's service layer (AccountService, CatalogService, OrderService), ported
call for call so the same user journeys can run against either data layer.

The service decides which mapper statements run and in what order, exactly as the
Java code does; the repository it is given answers them, from the legacy SQL or
from MongoDB.
"""

from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from decimal import Decimal

from mdc.modern import DuplicateKey


class Failed(Exception):
    """A call the application would surface as an error (e.g. a duplicate key)."""


def java_split(text: str) -> list[str]:
    """String.split("\\\\s+"): leading empty strings kept, trailing ones dropped."""
    parts = re.split(r"\s+", text)
    while parts and parts[-1] == "":
        parts.pop()
    return parts


class PetStoreService:
    def __init__(self, repo):
        self.repo = repo

    def _run(self, statement: str, params: dict | None = None):
        try:
            return self.repo.run(statement, params)
        except (sqlite3.IntegrityError, DuplicateKey) as e:
            raise Failed("duplicate key") from e

    @contextmanager
    def _transaction(self):
        conn = getattr(self.repo, "conn", None)
        if conn is None:
            yield
            return
        conn.execute("SAVEPOINT tx")
        self.repo.in_transaction = True
        try:
            yield
        except Exception:
            conn.execute("ROLLBACK TO tx")
            conn.execute("RELEASE tx")
            raise
        else:
            conn.execute("RELEASE tx")
        finally:
            self.repo.in_transaction = False

    # AccountService -------------------------------------------------------
    def get_account(self, username: str):
        rows = self._run("getAccountByUsername", {"username": username})
        return rows[0] if rows else None

    def login(self, username: str, password: str):
        rows = self._run("getAccountByUsernameAndPassword", {"param1": username, "param2": password})
        return rows[0] if rows else None

    def insert_account(self, account: dict) -> None:
        with self._transaction():
            self._run("insertAccount", account)
            self._run("insertProfile", account)
            self._run("insertSignon", account)

    def update_account(self, account: dict) -> None:
        with self._transaction():
            self._run("updateAccount", account)
            self._run("updateProfile", account)
            if account.get("password"):
                self._run("updateSignon", account)

    # CatalogService -------------------------------------------------------
    def category_list(self):
        return self._run("getCategoryList")

    def category(self, category_id: str):
        rows = self._run("getCategory", {"categoryId": category_id})
        return rows[0] if rows else None

    def product(self, product_id: str):
        rows = self._run("getProduct", {"productId": product_id})
        return rows[0] if rows else None

    def products_by_category(self, category_id: str):
        return self._run("getProductListByCategory", {"value": category_id})

    def search(self, keywords: str):
        out = []
        for keyword in java_split(keywords):
            out += self._run("searchProductList", {"value": "%" + keyword.lower() + "%"})
        return out

    def items_by_product(self, product_id: str):
        return self._run("getItemListByProduct", {"value": product_id})

    def item(self, item_id: str):
        rows = self._run("getItem", {"value": item_id})
        return rows[0] if rows else None

    def in_stock(self, item_id: str) -> bool:
        rows = self._run("getInventoryQuantity", {"itemId": item_id})
        if not rows:
            raise Failed("no inventory row")       # Java unboxes null: NullPointerException
        return rows[0]["value"] > 0

    # OrderService ---------------------------------------------------------
    def next_id(self, name: str) -> int:
        rows = self._run("getSequence", {"name": name})
        if not rows:
            raise Failed(f"no sequence {name}")
        nxt = rows[0]["nextid"]
        self._run("updateSequence", {"name": name, "nextId": nxt + 1})
        return nxt

    def place_order(self, order: dict) -> int:
        with self._transaction():
            order = dict(order)
            order["orderId"] = self.next_id("ordernum")
            for line in order["lineItems"]:
                self._run("updateInventoryQuantity", {"itemId": line["itemId"], "increment": line["quantity"]})
            self._run("insertOrder", order)
            self._run("insertOrderStatus", order)
            for line in order["lineItems"]:
                self._run("insertLineItem", {**line, "orderId": order["orderId"]})
            return order["orderId"]

    def get_order(self, order_id: int):
        rows = self._run("getOrder", {"value": order_id})
        if not rows:
            return None
        order = dict(rows[0])
        lines = []
        for line in self._run("getLineItemsByOrderId", {"orderId": order_id}):
            line = dict(line)
            item = self.item(line["itemid"])
            if item is not None:
                qty = self._run("getInventoryQuantity", {"itemId": line["itemid"]})
                item = {**item, "quantity": qty[0]["value"] if qty else None}
            line["item"] = item
            lines.append(line)
        order["lineitems"] = sorted(lines, key=lambda li: li["linenumber"])
        return order

    def orders_by_user(self, username: str):
        return self._run("getOrdersByUsername", {"value": username})


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))
