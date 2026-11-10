"""The rules that keep the numbers honest, checked on the source."""

import ast
import hashlib
import json

from mdc.legacy import ROOT

PKG = ROOT / "mdc"


def imports(rel: str) -> set[str]:
    tree = ast.parse((PKG / rel).read_text())
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module:
            out.add(n.module)
        elif isinstance(n, ast.Import):
            out |= {a.name for a in n.names}
    return out


def test_forecasting_and_status_never_read_the_engagement_truth():
    for rel in ("forecast.py", "status.py", "intake.py"):
        assert "mdc.engagements" not in imports(rel), rel


def test_modern_side_never_touches_the_legacy_database():
    assert not {m for m in imports("modern.py") if m.startswith(("mdc.legacy", "sqlite3"))}


def test_planners_see_only_points_and_findings():
    from mdc.engagements import generate
    e = generate(1, 1, json.loads((ROOT / "config" / "delivery.json").read_text())["engagements"])[0]
    assert set(e["work_packages"][0]) == {"id", "points", "findings"}


def test_held_out_sets_match_their_lock():
    from mdc.cli import _digest, _engagement_set, _workloads
    lock = json.loads((ROOT / "config" / "heldout.json").read_text())
    assert _digest(_engagement_set("heldout")) == lock["engagements"]["sha256"]
    assert _digest(_workloads("heldout")) == lock["parity"]["sha256"]


def test_no_tuning_constants_in_forecasting_code():
    for rel in ("forecast.py", "status.py", "engagements.py"):
        tree = ast.parse((PKG / rel).read_text())
        nums = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)
                and isinstance(n.value, (int, float)) and not isinstance(n.value, bool)}
        assert nums <= {0, 1, 2, 3, 5, 9, 15, 50, 85, 95, 100, 200, 0.0, 1.0, 1e-9, 0x5EED, 30}, (rel, nums)
