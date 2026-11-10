"""The modernized side: JPetStore's data access rewritten for MongoDB.

Document model (the reasons are in `mdc.design`):

  accounts   _id = username; the ACCOUNT row, with PROFILE embedded as `profile`
             and SIGNON embedded as `signon` (one-to-one, same lifecycle)
  banners    _id = category id; BANNERDATA stays a small shared lookup
  categories _id = category id
  products   _id = product id
  items      _id = item id; INVENTORY embedded as `quantity` (one-to-one, updated
             together), and an extended reference to its product
             (`product.name`, `product.description`, `product.categoryId`)
             because every item read in JPetStore also reads those fields
  orders     _id = order id; ORDERSTATUS embedded as `status`, LINEITEM rows
             embedded as `lineItems` (bounded, always read with the order)
  sequences  _id = sequence name

`MongoRepository.run(statement_id, params)` answers every mapper statement with
the same shape the legacy SQL returns, so the two sides can be compared call by
call. Legacy behaviour is kept where the comparison found a difference that a
customer would notice; each such choice is a decision in config/decisions.json.

Connect to a real MongoDB with MONGO_URI (CI runs against a mongo:8 service);
without it the repository uses mongomock in process.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from decimal import Decimal

from bson.decimal128 import Decimal128

MONEY = ("listprice", "unitcost", "unitprice", "totalprice")


def connect(name: str = "jpetstore"):
    uri = os.environ.get("MONGO_URI")
    if uri:
        import pymongo
        client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.drop_database(name)
        return client[name]
    import mongomock
    return mongomock.MongoClient()[name]


def _d128(v):
    return None if v is None else Decimal128(Decimal(str(v)))


def _dec(v):
    if v is None:
        return None
    return v.to_decimal() if isinstance(v, Decimal128) else Decimal(str(v))


def _date(v):
    if v is None or isinstance(v, datetime):
        return v
    return datetime.fromisoformat(str(v)[:19] if "T" in str(v) or len(str(v)) > 10 else str(v))


def _datestr(v):
    return None if v is None else v.strftime("%Y-%m-%d")


# ----------------------------------------------------------------- data migration
def migrate(legacy, db) -> dict[str, int]:
    """Copy JPetStore's tables into the document model. Returns documents per collection."""
    rows = {t: legacy.table_rows(t) for t in ("account", "profile", "signon", "bannerdata", "category",
                                               "product", "item", "inventory", "orders", "orderstatus",
                                               "lineitem", "sequence", "supplier")}
    profiles = {r["userid"]: r for r in rows["profile"]}
    signons = {r["username"]: r for r in rows["signon"]}
    accounts = []
    for a in rows["account"]:
        doc = _account_doc(a)
        if a["userid"] in profiles:
            doc["profile"] = _profile_doc(profiles[a["userid"]])
        if a["userid"] in signons:
            doc["signon"] = {"password": signons[a["userid"]]["password"]}
        accounts.append(doc)
    # Sign-ons without an account row exist in principle; keep them so nothing is lost.
    for name, s in signons.items():
        if not any(d["_id"] == name for d in accounts):
            accounts.append({"_id": name, "signon": {"password": s["password"]}, "accountRow": False})
    products = {p["productid"]: p for p in rows["product"]}
    inventory = {r["itemid"]: r["qty"] for r in rows["inventory"]}
    items = []
    for i in rows["item"]:
        p = products[i["productid"]]
        doc = {"_id": i["itemid"], "productId": i["productid"], "listPrice": _d128(i["listprice"]),
               "unitCost": _d128(i["unitcost"]), "supplierId": i["supplier"], "status": i["status"],
               "attributes": [i[f"attr{n}"] for n in range(1, 6)],
               "product": {"name": p["name"], "description": p["descn"], "categoryId": p["category"]}}
        if i["itemid"] in inventory:
            doc["quantity"] = inventory[i["itemid"]]
        items.append(doc)
    statuses = {r["orderid"]: r for r in rows["orderstatus"]}
    lines: dict[int, list] = {}
    for li in rows["lineitem"]:
        lines.setdefault(li["orderid"], []).append(_line_doc(li))
    orders = []
    for o in rows["orders"]:
        doc = _order_doc(o)
        if o["orderid"] in statuses:
            st = statuses[o["orderid"]]
            doc["status"] = {"lineNumber": st["linenum"], "timestamp": _date(st["timestamp"]), "code": st["status"]}
        doc["lineItems"] = sorted(lines.get(o["orderid"], []), key=lambda d: d["lineNumber"])
        orders.append(doc)
    batches = {
        "accounts": accounts,
        "banners": [{"_id": b["favcategory"], "bannerName": b["bannername"]} for b in rows["bannerdata"]],
        "categories": [{"_id": c["catid"], "name": c["name"], "description": c["descn"]} for c in rows["category"]],
        "products": [{"_id": p["productid"], "categoryId": p["category"], "name": p["name"],
                      "nameLower": p["name"].lower() if p["name"] is not None else None,
                      "description": p["descn"]} for p in rows["product"]],
        "items": items,
        "orders": orders,
        "sequences": [{"_id": s["name"], "nextId": s["nextid"]} for s in rows["sequence"]],
        "suppliers": [{"_id": s["suppid"], **{k: v for k, v in s.items() if k != "suppid"}} for s in rows["supplier"]],
    }
    counts = {}
    for name, docs in batches.items():
        db[name].delete_many({})
        if docs:
            db[name].insert_many(docs)
        counts[name] = len(docs)
    db["products"].create_index("categoryId")
    db["products"].create_index("nameLower")
    db["items"].create_index("productId")
    db["orders"].create_index([("username", 1), ("orderDate", 1)])
    return counts


def _account_doc(a: dict) -> dict:
    return {"_id": a["userid"], "email": a["email"], "firstName": a["firstname"], "lastName": a["lastname"],
            "status": a["status"], "address1": a["addr1"], "address2": a["addr2"], "city": a["city"],
            "state": a["state"], "zip": a["zip"], "country": a["country"], "phone": a["phone"]}


def _profile_doc(p: dict) -> dict:
    return {"languagePreference": p["langpref"], "favouriteCategoryId": p["favcategory"],
            "listOption": p["mylistopt"], "bannerOption": p["banneropt"]}


def _line_doc(li: dict) -> dict:
    return {"lineNumber": li["linenum"], "itemId": li["itemid"], "quantity": li["quantity"],
            "unitPrice": _d128(li["unitprice"])}


ORDER_FIELDS = {  # legacy column -> document field
    "userid": "username", "orderdate": "orderDate", "shipaddr1": "shipAddress1", "shipaddr2": "shipAddress2",
    "shipcity": "shipCity", "shipstate": "shipState", "shipzip": "shipZip", "shipcountry": "shipCountry",
    "billaddr1": "billAddress1", "billaddr2": "billAddress2", "billcity": "billCity", "billstate": "billState",
    "billzip": "billZip", "billcountry": "billCountry", "courier": "courier", "totalprice": "totalPrice",
    "billtofirstname": "billToFirstName", "billtolastname": "billToLastName",
    "shiptofirstname": "shipToFirstName", "shiptolastname": "shipToLastName", "creditcard": "creditCard",
    "exprdate": "expiryDate", "cardtype": "cardType", "locale": "locale",
}


def _order_doc(o: dict) -> dict:
    doc = {"_id": o["orderid"]}
    for col, f in ORDER_FIELDS.items():
        doc[f] = o[col]
    doc["orderDate"] = _date(doc["orderDate"])
    doc["totalPrice"] = _d128(doc["totalPrice"])
    return doc


# ------------------------------------------------------------------ repository
class DuplicateKey(Exception):
    pass


class MongoRepository:
    """Every JPetStore mapper statement, answered from the document model."""

    def __init__(self, db):
        self.db = db
        self.calls: dict[str, int] = {}

    def run(self, statement_id: str, params: dict | None = None):
        self.calls[statement_id] = self.calls.get(statement_id, 0) + 1
        return getattr(self, statement_id)(dict(params or {}))

    # Accounts ---------------------------------------------------------------
    def _account_row(self, doc: dict | None, password: str | None = None) -> list[dict]:
        # Legacy joins ACCOUNT, PROFILE, SIGNON and BANNERDATA with inner joins: an account
        # missing any of them, or whose favourite category has no banner, is not returned.
        if not doc or doc.get("accountRow") is False or "profile" not in doc or "signon" not in doc:
            return []
        if password is not None and doc["signon"]["password"] != password:
            return []
        prof = doc["profile"]
        banner = self.db.banners.find_one({"_id": prof.get("favouriteCategoryId")})
        if banner is None:
            return []
        return [{"username": doc["_id"], "email": doc["email"], "firstname": doc["firstName"],
                 "lastname": doc["lastName"], "status": doc["status"], "address1": doc["address1"],
                 "address2": doc["address2"], "city": doc["city"], "state": doc["state"], "zip": doc["zip"],
                 "country": doc["country"], "phone": doc["phone"],
                 "languagepreference": prof["languagePreference"],
                 "favouritecategoryid": prof["favouriteCategoryId"], "listoption": prof["listOption"],
                 "banneroption": prof["bannerOption"], "bannername": banner["bannerName"]}]

    def getAccountByUsername(self, p):
        return self._account_row(self.db.accounts.find_one({"_id": p["username"]}))

    def getAccountByUsernameAndPassword(self, p):
        return self._account_row(self.db.accounts.find_one({"_id": p["param1"]}), password=p["param2"])

    def insertAccount(self, p):
        fields = {"email": p["email"], "firstName": p["firstName"], "lastName": p["lastName"],
                  "status": p["status"], "address1": p["address1"], "address2": p.get("address2"),
                  "city": p["city"], "state": p["state"], "zip": p["zip"], "country": p["country"],
                  "phone": p["phone"]}
        existing = self.db.accounts.find_one({"_id": p["username"]})
        if existing and existing.get("accountRow") is not False:
            raise DuplicateKey(f"account {p['username']} exists")
        self.db.accounts.update_one({"_id": p["username"]}, {"$set": fields, "$unset": {"accountRow": ""}},
                                    upsert=True)
        return 1

    def updateAccount(self, p):
        fields = {"email": p["email"], "firstName": p["firstName"], "lastName": p["lastName"],
                  "status": p["status"], "address1": p["address1"], "address2": p.get("address2"),
                  "city": p["city"], "state": p["state"], "zip": p["zip"], "country": p["country"],
                  "phone": p["phone"]}
        r = self.db.accounts.update_one({"_id": p["username"], "accountRow": {"$ne": False}, "email": {"$exists": True}},
                                        {"$set": fields})
        return r.matched_count

    def _profile_fields(self, p):
        return {"languagePreference": p["languagePreference"], "favouriteCategoryId": p.get("favouriteCategoryId"),
                "listOption": 1 if p.get("listOption") else 0, "bannerOption": 1 if p.get("bannerOption") else 0}

    def insertProfile(self, p):
        doc = self.db.accounts.find_one({"_id": p["username"]})
        if doc and "profile" in doc:
            raise DuplicateKey(f"profile {p['username']} exists")
        self.db.accounts.update_one({"_id": p["username"]}, {"$set": {"profile": self._profile_fields(p)}},
                                    upsert=True)
        if not doc:
            self.db.accounts.update_one({"_id": p["username"]}, {"$set": {"accountRow": False}})
        return 1

    def updateProfile(self, p):
        r = self.db.accounts.update_one({"_id": p["username"], "profile": {"$exists": True}},
                                        {"$set": {"profile": self._profile_fields(p)}})
        return r.matched_count

    def insertSignon(self, p):
        doc = self.db.accounts.find_one({"_id": p["username"]})
        if doc and "signon" in doc:
            raise DuplicateKey(f"signon {p['username']} exists")
        self.db.accounts.update_one({"_id": p["username"]}, {"$set": {"signon": {"password": p["password"]}}},
                                    upsert=True)
        if not doc:
            self.db.accounts.update_one({"_id": p["username"]}, {"$set": {"accountRow": False}})
        return 1

    def updateSignon(self, p):
        r = self.db.accounts.update_one({"_id": p["username"], "signon": {"$exists": True}},
                                        {"$set": {"signon.password": p["password"]}})
        return r.matched_count

    # Catalog ----------------------------------------------------------------
    @staticmethod
    def _category(c):
        return {"categoryid": c["_id"], "name": c["name"], "description": c["description"]}

    def getCategory(self, p):
        c = self.db.categories.find_one({"_id": p["categoryId"]})
        return [self._category(c)] if c else []

    def getCategoryList(self, p):
        return [self._category(c) for c in self.db.categories.find()]

    @staticmethod
    def _product(d):
        return {"productid": d["_id"], "name": d["name"], "description": d["description"], "categoryid": d["categoryId"]}

    def getProduct(self, p):
        d = self.db.products.find_one({"_id": p["productId"]})
        return [self._product(d)] if d else []

    def getProductListByCategory(self, p):
        return [self._product(d) for d in self.db.products.find({"categoryId": p["value"]})]

    def searchProductList(self, p):
        # Legacy: lower(name) LIKE #{value}, case sensitive, % and _ as wildcards.
        # `nameLower` is written at migration so the match can run in the database.
        regex = "^" + like_to_regex(p["value"]).pattern + "$"
        return [self._product(d) for d in self.db.products.find({"nameLower": {"$regex": regex, "$options": "s"}})]

    @staticmethod
    def _item(d, with_quantity: bool):
        row = {"itemid": d["_id"], "listprice": _dec(d["listPrice"]), "unitcost": _dec(d["unitCost"]),
               "supplierid": d["supplierId"], "product.productid": d["productId"],
               "product.name": d["product"]["name"], "product.description": d["product"]["description"],
               "product.categoryid": d["product"]["categoryId"], "status": d["status"],
               **{f"attribute{n + 1}": d["attributes"][n] for n in range(5)}}
        if with_quantity:
            row["quantity"] = d["quantity"]
        return row

    def getItemListByProduct(self, p):
        return [self._item(d, False) for d in self.db.items.find({"productId": p["value"]})]

    def getItem(self, p):
        d = self.db.items.find_one({"_id": p["value"], "quantity": {"$exists": True}})
        return [self._item(d, True)] if d else []

    def getInventoryQuantity(self, p):
        d = self.db.items.find_one({"_id": p["itemId"], "quantity": {"$exists": True}})
        return [{"value": d["quantity"]}] if d else []

    def updateInventoryQuantity(self, p):
        r = self.db.items.update_one({"_id": p["itemId"], "quantity": {"$exists": True}},
                                     {"$inc": {"quantity": -int(p["increment"])}})
        return r.matched_count

    # Orders -----------------------------------------------------------------
    @staticmethod
    def _order(d):
        return {"billaddress1": d["billAddress1"], "billaddress2": d["billAddress2"], "billcity": d["billCity"],
               "billcountry": d["billCountry"], "billstate": d["billState"], "billtofirstname": d["billToFirstName"],
               "billtolastname": d["billToLastName"], "billzip": d["billZip"], "shipaddress1": d["shipAddress1"],
               "shipaddress2": d["shipAddress2"], "shipcity": d["shipCity"], "shipcountry": d["shipCountry"],
               "shipstate": d["shipState"], "shiptofirstname": d["shipToFirstName"],
               "shiptolastname": d["shipToLastName"], "shipzip": d["shipZip"], "cardtype": d["cardType"],
               "courier": d["courier"], "creditcard": d["creditCard"], "expirydate": d["expiryDate"],
               "locale": d["locale"], "orderdate": _datestr(d["orderDate"]), "orderid": d["_id"],
               "totalprice": _dec(d["totalPrice"]), "username": d["username"], "status": d["status"]["code"]}

    def getOrder(self, p):
        d = self.db.orders.find_one({"_id": int(p["value"]), "status": {"$exists": True}})
        return [self._order(d)] if d else []

    def getOrdersByUsername(self, p):
        cur = self.db.orders.find({"username": p["value"], "status": {"$exists": True}}).sort("orderDate", 1)
        return [self._order(d) for d in cur]

    def insertOrder(self, p):
        if self.db.orders.find_one({"_id": int(p["orderId"])}):
            raise DuplicateKey(f"order {p['orderId']} exists")
        doc = {"_id": int(p["orderId"]), "username": p["username"], "orderDate": _date(p["orderDate"])}
        for f in ("shipAddress1", "shipAddress2", "shipCity", "shipState", "shipZip", "shipCountry", "billAddress1",
                  "billAddress2", "billCity", "billState", "billZip", "billCountry", "courier", "billToFirstName",
                  "billToLastName", "shipToFirstName", "shipToLastName", "creditCard", "expiryDate", "cardType",
                  "locale"):
            doc[f] = p.get(f)
        doc["totalPrice"] = _d128(p["totalPrice"])
        doc["lineItems"] = []
        self.db.orders.insert_one(doc)
        return 1

    def insertOrderStatus(self, p):
        status = {"lineNumber": int(p["orderId"]), "timestamp": _date(p["orderDate"]), "code": p["status"]}
        r = self.db.orders.update_one({"_id": int(p["orderId"]), "status": {"$exists": False}},
                                      {"$set": {"status": status}})
        if r.matched_count == 0:
            raise DuplicateKey(f"status for order {p['orderId']} exists or order missing")
        return 1

    def getLineItemsByOrderId(self, p):
        d = self.db.orders.find_one({"_id": int(p["orderId"])}, {"lineItems": 1})
        if not d:
            return []
        return [{"orderid": d["_id"], "linenumber": li["lineNumber"], "itemid": li["itemId"],
                 "quantity": li["quantity"], "unitprice": _dec(li["unitPrice"])} for li in d["lineItems"]]

    def insertLineItem(self, p):
        line = {"lineNumber": int(p["lineNumber"]), "itemId": p["itemId"], "quantity": int(p["quantity"]),
                "unitPrice": _d128(p["unitPrice"])}
        r = self.db.orders.update_one({"_id": int(p["orderId"]), "lineItems.lineNumber": {"$ne": line["lineNumber"]}},
                                      {"$push": {"lineItems": line}})
        if r.matched_count == 0:
            raise DuplicateKey(f"line {line['lineNumber']} of order {p['orderId']} exists or order missing")
        return 1

    # Sequences --------------------------------------------------------------
    def getSequence(self, p):
        d = self.db.sequences.find_one({"_id": p["name"]})
        return [{"name": d["_id"], "nextid": d["nextId"]}] if d else []

    def updateSequence(self, p):
        return self.db.sequences.update_one({"_id": p["name"]}, {"$set": {"nextId": int(p["nextId"])}}).matched_count


def like_to_regex(pattern: str) -> re.Pattern:
    """SQL LIKE (no escape clause) to an anchored regular expression."""
    out = []
    for ch in pattern:
        out.append(".*" if ch == "%" else "." if ch == "_" else re.escape(ch))
    return re.compile("".join(out), re.S)
