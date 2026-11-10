import json
import random

import pytest

from mdc.engagements import commitments, first_warning, generate, play, reference_class, score
from mdc.forecast import monte_carlo_sprints, percentile, plan_sprints, rolling_sprints
from mdc.intake import analyse
from mdc.legacy import ROOT, LegacyDatabase
from mdc.mistakes import MISTAKES
from mdc.parity import catalog_ids, generate_workload, normalise, run_parity
from mdc.status import add_working_days, check_numbers, rag

CFG = json.loads((ROOT / "config" / "delivery.json").read_text())


@pytest.fixture(scope="module")
def workload():
    return generate_workload(5, 120, catalog_ids(LegacyDatabase()))


def test_workload_is_deterministic():
    ids = catalog_ids(LegacyDatabase())
    assert generate_workload(3, 40, ids) == generate_workload(3, 40, ids)


def test_parity_agrees_on_every_call(workload):
    r = run_parity(workload)
    assert r.agreed == r.operations and r.statements_validated >= 20, json.dumps(r.divergences[:3], default=str)[:3000]


@pytest.mark.parametrize("name", ["dropped-inner-join", "forgot-lower-name", "literal-underscore",
                                  "unsorted-history", "inventory-increment"])
def test_parity_catches_translation_mistakes(name):
    workload = generate_workload(1, 300, catalog_ids(LegacyDatabase()))
    assert run_parity(workload, MISTAKES[name]).divergences


def test_normalise_ignores_unordered_rows_only():
    a = [{"x": 1}, {"x": 2}]
    assert normalise("category_list", a) == normalise("category_list", a[::-1])
    assert normalise("orders_by_user", [{"orderdate": "2026-01-02"}, {"orderdate": "2026-01-01"}])[0]["orderdate"] == "2026-01-01"


def test_intake_finds_the_known_risks():
    a = analyse()
    titles = " ".join(f["title"] for f in a["findings"])
    assert "transaction" in titles and "sequence" in titles and "plain text" in titles
    assert a["inventory"]["statements"] == 25 and a["inventory"]["transactional_methods"] == 4
    wp3 = next(w for w in a["work_packages"] if w["id"] == "WP3")
    assert "insertOrder" in wp3["statements"] and any(f.startswith("F") for f in wp3["findings"])
    assert sum(len(w["statements"]) for w in a["work_packages"][:5]) == 25    # every statement has a home


def test_forecast_spread_and_plan():
    team, fc = CFG["team"], {**CFG["forecast"], "simulations": 500}
    wps = [{"points": 20, "findings": ["F1"]}, {"points": 10, "findings": []}]
    mc = monte_carlo_sprints(wps, team, fc, random.Random(1))
    assert percentile(mc, 15) < plan_sprints(30, team) * 1.5 < percentile(mc, 99) * 2
    assert percentile(mc, 85) > percentile(mc, 50)
    assert sum(rolling_sprints(10, [5, 5], fc, random.Random(1))) / 500 == pytest.approx(2.0)


def test_engagement_scoring_and_reference_class():
    cfg = {**CFG, "forecast": {**CFG["forecast"], "simulations": 200}}
    res = [play(e, cfg) for e in generate(11, 30, cfg["engagements"])]
    ref = reference_class(res)
    assert ref["p85"] > ref["p50"] > 0
    s = score(res, ref)
    assert s["methods"]["reference_class"]["on_time"] >= s["methods"]["plan"]["on_time"]
    r = res[0]
    assert first_warning(r, 0.0) == (r["rolling"][0]["sprint"] if r["rolling"] else None)
    assert commitments(r, ref)["reference_class"] == pytest.approx(r["plan"] * ref["p85"])


def test_rag_and_working_days():
    facts = {"commit_date": "2027-03-10", "target_date": "2027-02-26", "statements_validated": 24,
             "statements_total": 25, "divergences": 2, "open_high_findings": 0}
    s = rag(facts, CFG)
    assert s["schedule"]["colour"] == "red" and s["quality"]["colour"] == "amber" and s["overall"] == "red"
    from datetime import date
    assert add_working_days(date(2026, 12, 23), 2, ("2026-12-24", "2026-12-25")).isoformat() == "2026-12-29"


def test_number_guard_catches_invented_figures():
    facts = {"points": 108.5, "commit_date": "2027-01-13", "validated": 25}
    assert check_numbers("Scope is 108.5 points; 25 statements; finish 2027-01-13.", facts) == []
    assert check_numbers("Scope is 110 points; finish 2027-01-20.", facts) == ["2027-01-20", "110"]
    assert check_numbers("WP3 and F01 are on track.", facts) == []
