"""Classic relational-to-document translation mistakes, each as a variant of the
modern repository. The parity harness earns trust only if it catches them: a
workload that lets one through is a hole in the validation, and the report says so.
"""

from __future__ import annotations

from mdc.modern import MongoRepository, like_to_regex


class DroppedInnerJoin(MongoRepository):
    """Returns the account even when its favourite category has no banner row."""

    def _account_row(self, doc, password=None):
        rows = super()._account_row(doc, password)
        if rows or not doc or "profile" not in doc or "signon" not in doc or doc.get("accountRow") is False:
            return rows
        if password is not None and doc["signon"]["password"] != password:
            return []
        prof = doc["profile"]
        return [{"username": doc["_id"], "email": doc["email"], "firstname": doc["firstName"],
                 "lastname": doc["lastName"], "status": doc["status"], "address1": doc["address1"],
                 "address2": doc["address2"], "city": doc["city"], "state": doc["state"], "zip": doc["zip"],
                 "country": doc["country"], "phone": doc["phone"], "languagepreference": prof["languagePreference"],
                 "favouritecategoryid": prof["favouriteCategoryId"], "listoption": prof["listOption"],
                 "banneroption": prof["bannerOption"], "bannername": None}]


class CaseSensitiveName(MongoRepository):
    """Matches the search pattern against the stored name, forgetting lower(name)."""

    def searchProductList(self, p):
        regex = "^" + like_to_regex(p["value"]).pattern + "$"
        return [self._product(d) for d in self.db.products.find({"name": {"$regex": regex, "$options": "s"}})]


class LiteralUnderscore(MongoRepository):
    """Treats LIKE's `_` as a literal character rather than "any one character"."""

    def searchProductList(self, p):
        import re
        regex = "^" + "".join(".*" if ch == "%" else re.escape(ch) for ch in p["value"]) + "$"
        return [self._product(d) for d in self.db.products.find({"nameLower": {"$regex": regex, "$options": "s"}})]


class UnsortedHistory(MongoRepository):
    """Drops ORDER BY ORDERDATE: order history comes back in insertion order."""

    def getOrdersByUsername(self, p):
        return [self._order(d) for d in self.db.orders.find({"username": p["value"], "status": {"$exists": True}})]


class InventoryIncrement(MongoRepository):
    """Adds the ordered quantity to stock instead of subtracting it."""

    def updateInventoryQuantity(self, p):
        r = self.db.items.update_one({"_id": p["itemId"], "quantity": {"$exists": True}},
                                     {"$inc": {"quantity": int(p["increment"])}})
        return r.matched_count


class StatuslessOrders(MongoRepository):
    """Returns orders that have no status, which the legacy inner join hides."""

    def getOrder(self, p):
        d = self.db.orders.find_one({"_id": int(p["value"])})
        if d and "status" not in d:
            d = {**d, "status": {"code": None}}
        return [self._order(d)] if d else []


MISTAKES = {
    "dropped-inner-join": DroppedInnerJoin,
    "forgot-lower-name": CaseSensitiveName,
    "literal-underscore": LiteralUnderscore,
    "unsorted-history": UnsortedHistory,
    "inventory-increment": InventoryIncrement,
    "statusless-orders": StatuslessOrders,
}
