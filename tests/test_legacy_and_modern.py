from decimal import Decimal

import pytest

from mdc.legacy import LegacyDatabase, parse_mapper, JPETSTORE
from mdc.modern import MongoRepository, connect, like_to_regex, migrate
from mdc.service import Failed, PetStoreService, java_split


@pytest.fixture
def both():
    legacy = LegacyDatabase()
    db = connect()
    migrate(legacy, db)
    return PetStoreService(legacy), PetStoreService(MongoRepository(db)), legacy, db


def test_every_mapper_statement_is_parsed_without_dynamic_sql():
    stmts = [s for p in sorted((JPETSTORE / "mapper").glob("*.xml")) for s in parse_mapper(p)]
    assert len(stmts) == 25
    upd = next(s for s in stmts if s.id == "updateProfile")
    assert ":listOptionValue" in upd.sql and upd.binds == {"listOptionValue": "listOption", "bannerOptionValue": "bannerOption"}


def test_legacy_keeps_hsqldb_semantics():
    db = LegacyDatabase()
    item = db.run("getItem", {"value": "EST-1"})[0]
    assert item["listprice"] == Decimal("16.50") and isinstance(item["listprice"], Decimal)
    assert db.run("searchProductList", {"value": "%Angel%"}) == []          # case-sensitive LIKE


def test_migration_moves_every_row():
    legacy = LegacyDatabase()
    db = connect()
    counts = migrate(legacy, db)
    assert counts["items"] == len(legacy.table_rows("item")) == 28
    assert counts["products"] == 16 and counts["accounts"] == 2
    acct = db.accounts.find_one({"_id": "j2ee"})
    assert acct["profile"]["favouriteCategoryId"] == "DOGS" and acct["signon"]["password"] == "j2ee"
    item = db.items.find_one({"_id": "EST-1"})
    assert item["quantity"] == 10000 and item["product"]["name"] == "Angelfish"


def test_like_translation():
    assert like_to_regex("%a_g%").fullmatch("tiger shark angelfish")
    assert like_to_regex("%a_g%").fullmatch("angelfish")
    assert not like_to_regex("%(%").fullmatch("angelfish")
    assert like_to_regex("%.%").fullmatch("a.b") and not like_to_regex("%.%").fullmatch("ab")


def test_java_split_keeps_leading_empty_and_drops_trailing():
    assert java_split("  dog") == ["", "dog"]
    assert java_split("fish dog  ") == ["fish", "dog"]


def test_order_round_trip_agrees(both):
    old, new, *_ = both
    order = {"username": "j2ee", "orderDate": "2026-03-05", "shipAddress1": "a", "shipAddress2": None,
             "shipCity": "c", "shipState": "s", "shipZip": "1", "shipCountry": "DE", "billAddress1": "b",
             "billAddress2": None, "billCity": "c", "billState": "s", "billZip": "1", "billCountry": "DE",
             "courier": "UPS", "totalPrice": "33.00", "billToFirstName": "A", "billToLastName": "B",
             "shipToFirstName": "A", "shipToLastName": "B", "creditCard": "1", "expiryDate": "12/03",
             "cardType": "Visa", "locale": "CA", "status": "P",
             "lineItems": [{"lineNumber": 1, "itemId": "EST-1", "quantity": 2, "unitPrice": "16.50"}]}
    assert old.place_order(order) == new.place_order(order) == 1000
    a, b = old.get_order(1000), new.get_order(1000)
    assert a["totalprice"] == b["totalprice"] == Decimal("33.00")
    assert a["lineitems"][0]["item"]["quantity"] == b["lineitems"][0]["item"]["quantity"] == 9998


def test_duplicate_signup_fails_on_both(both):
    old, new, *_ = both
    acct = {"username": "j2ee", "password": "x", "email": "e", "firstName": "f", "lastName": "l", "status": "OK",
            "address1": "a", "address2": None, "city": "c", "state": "s", "zip": "z", "country": "DE",
            "phone": "p", "languagePreference": "english", "favouriteCategoryId": "DOGS",
            "listOption": True, "bannerOption": False}
    for svc in (old, new):
        with pytest.raises(Failed):
            svc.insert_account(acct)
    # the failed sign-up must not change the existing account on either side
    assert old.get_account("j2ee")["email"] == new.get_account("j2ee")["email"] == "yourname@yourdomain.com"


def test_account_without_favourite_category_cannot_log_in_on_either_side(both):
    old, new, *_ = both
    acct = {"username": "nofav", "password": "pw", "email": "e", "firstName": "f", "lastName": "l", "status": "OK",
            "address1": "a", "address2": None, "city": "c", "state": "s", "zip": "z", "country": "DE",
            "phone": "p", "languagePreference": "english", "favouriteCategoryId": None,
            "listOption": False, "bannerOption": False}
    old.insert_account(acct)
    new.insert_account(acct)
    assert old.login("nofav", "pw") is None and new.login("nofav", "pw") is None


def test_missing_inventory_row_is_an_error_like_java(both):
    old, new, *_ = both
    for svc in (old, new):
        with pytest.raises(Failed):
            svc.in_stock("EST-999")
