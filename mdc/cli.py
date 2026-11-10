"""python -m mdc <command>

  intake       analyse the legacy app: scope, findings, work packages
  parity       run a workload against legacy and MongoDB      (--set dev|heldout)
  mistakes     check the parity harness catches classic translation mistakes
  engagements  score forecasting on simulated engagements     (--set dev|heldout)
  cockpit      forecast, RAG status and weekly report for the JPetStore engagement
  lock         write config/heldout.json (refuses to overwrite)
  report       regenerate reports/REPORT.md, the README dashboard and web data

Held-out sets run once: the first run is written to reports/heldout/ and a second
run is refused unless --rerun, which writes a separate file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from datetime import date
from pathlib import Path

from mdc.legacy import ROOT, LegacyDatabase

CONFIG = ROOT / "config"
REPORTS = ROOT / "reports"
SETS = {
    "parity": {"dev": {"seeds": [1, 2, 3], "journeys": 300}, "heldout": {"seeds": [2027], "journeys": 600}},
    "engagements": {"dev": {"seed": 1, "count": 120}, "heldout": {"seed": 2027, "count": 120}},
}


def _cfg() -> dict:
    return json.loads((CONFIG / "delivery.json").read_text())


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, default=str) + "\n")


def _digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def _workloads(name: str):
    from mdc.parity import catalog_ids, generate_workload
    spec = SETS["parity"][name]
    ids = catalog_ids(LegacyDatabase())
    return [generate_workload(s, spec["journeys"], ids) for s in spec["seeds"]]


def _engagement_set(name: str):
    from mdc.engagements import generate
    spec = SETS["engagements"][name]
    return generate(spec["seed"], spec["count"], _cfg()["engagements"])


def _check_lock(kind: str, data) -> None:
    lock = json.loads((CONFIG / "heldout.json").read_text())
    if _digest(data) != lock[kind]["sha256"]:
        raise SystemExit(f"held-out {kind} no longer match config/heldout.json")


def _out(kind: str, name: str, rerun: bool) -> Path:
    if name == "dev":
        return REPORTS / f"{kind}_dev.json"
    first = REPORTS / "heldout" / f"{kind}_first_run.json"
    if first.exists() and not rerun:
        raise SystemExit(f"{first.relative_to(ROOT)} exists: held-out sets run once (use --rerun for a separate file)")
    return first if not first.exists() else REPORTS / "heldout" / f"{kind}_rerun.json"


def cmd_lock(args) -> int:
    path = CONFIG / "heldout.json"
    if path.exists() and not args.force:
        raise SystemExit("config/heldout.json exists; held-out sets are not regenerated")
    _write(path, {"_comment": "SHA-256 of the held-out parity workloads and engagements, written before either ran.",
                  "parity": {**SETS["parity"]["heldout"], "sha256": _digest(_workloads("heldout"))},
                  "engagements": {**SETS["engagements"]["heldout"], "sha256": _digest(_engagement_set("heldout"))}})
    print("wrote config/heldout.json")
    return 0


def cmd_intake(args) -> int:
    from mdc.intake import analyse
    a = analyse()
    _write(REPORTS / "intake.json", a)
    print(json.dumps(a["inventory"]))
    return 0


def cmd_parity(args) -> int:
    from mdc.parity import run_parity
    workloads = _workloads(args.set)
    if args.set == "heldout":
        _check_lock("parity", workloads)
    out = _out("parity", args.set, args.rerun)
    t0 = time.perf_counter()
    runs = [run_parity(w).to_dict() for w in workloads]
    merged = {"set": args.set, "workloads": len(runs), "operations": sum(r["operations"] for r in runs),
              "agreed": sum(r["agreed"] for r in runs), "divergence_count": sum(r["divergence_count"] for r in runs),
              "statements_total": runs[0]["statements_total"],
              "statements_validated": min(r["statements_validated"] for r in runs),
              "statement_calls": {s: sum(r["statements"][s]["calls"] for r in runs) for s in runs[0]["statements"]},
              "migrated": runs[0]["migrated"], "backend": "mongodb" if __import__("os").environ.get("MONGO_URI") else "mongomock",
              "seconds": round(time.perf_counter() - t0, 2), "runs": runs}
    _write(out, merged)
    print(f"{merged['agreed']}/{merged['operations']} calls agree, {merged['statements_validated']}/"
          f"{merged['statements_total']} statements validated -> {out.relative_to(ROOT)}")
    return 0


def cmd_mistakes(args) -> int:
    from mdc.mistakes import MISTAKES
    from mdc.parity import run_parity
    workload = _workloads("dev")[0]
    out = {}
    for name, cls in MISTAKES.items():
        r = run_parity(workload, cls)
        out[name] = {"caught": bool(r.divergences), "divergent_calls": len(r.divergences),
                     "first_caught_at_call": r.divergences[0]["index"] if r.divergences else None,
                     "doc": (cls.__doc__ or "").strip()}
        print(name, "caught" if r.divergences else "MISSED")
    _write(REPORTS / "mistakes.json", out)
    return 0


def cmd_engagements(args) -> int:
    from mdc.engagements import play, reference_class, score
    cfg = _cfg()
    t0 = time.perf_counter()
    if args.set == "dev":
        results = [play(e, cfg) for e in _engagement_set("dev")]
        ref = reference_class(results)
        _write(REPORTS / "engagements_dev.json", {"set": "dev", "reference_class": ref, "score": score(results, ref, cfg["forecast"]["checkpoint_sprint"]),
                                                  "seconds": round(time.perf_counter() - t0, 1)})
        print(json.dumps(ref))
        return 0
    ref = json.loads((REPORTS / "engagements_dev.json").read_text())["reference_class"]
    data = _engagement_set("heldout")
    _check_lock("engagements", data)
    out = _out("engagements", "heldout", args.rerun)
    results = [play(e, cfg) for e in data]
    scored = score(results, ref, cfg["forecast"]["checkpoint_sprint"])
    _write(out, {"set": "heldout", "reference_class_from_dev": ref, "score": scored,
                 "seconds": round(time.perf_counter() - t0, 1)})
    print(json.dumps(scored["methods"], indent=1))
    return 0


def cmd_cockpit(args) -> int:
    from mdc.forecast import monte_carlo_sprints, percentile, plan_sprints
    from mdc.status import add_working_days, check_numbers, rag, weekly_report
    cfg = _cfg()
    intake = json.loads((REPORTS / "intake.json").read_text())
    parity = json.loads((REPORTS / "parity_dev.json").read_text())
    ref = json.loads((REPORTS / "engagements_dev.json").read_text())["reference_class"]
    decisions = json.loads((CONFIG / "decisions.json").read_text())["decisions"]
    wps = intake["work_packages"]
    points = round(sum(w["points"] for w in wps), 1)
    team = cfg["team"]
    plan = plan_sprints(points, team)
    mc = monte_carlo_sprints(wps, team, cfg["forecast"], random.Random(7))
    commit = plan * ref["p85"]
    start = date.fromisoformat(team["engagement_start"])
    day = team["sprint_days"]
    off = tuple(team.get("non_working_days", []))
    decided = {d["finding"] for d in decisions if d["status"] == "agreed"}
    facts = {
        "status_week": cfg["customer"]["status_week"], "target_date": cfg["customer"]["target_end"],
        "work_packages": len(wps), "points": points,
        "plan_sprints": round(plan, 2), "mc_p50_sprints": round(percentile(mc, 50), 2),
        "mc_p85_sprints": round(percentile(mc, 85), 2), "commit_sprints": round(commit, 2),
        "p50_date": add_working_days(start, percentile(mc, 50) * day, off).isoformat(),
        "commit_date": add_working_days(start, commit * day, off).isoformat(),
        "plan_date": add_working_days(start, plan * day, off).isoformat(),
        "statements_total": parity["statements_total"], "statements_validated": parity["statements_validated"],
        "divergences": parity["divergence_count"], "parity_calls": parity["operations"],
        "findings": len(intake["findings"]),
        "open_high_findings": sum(1 for f in intake["findings"] if f["severity"] == "high" and f["id"] not in decided),
        "decisions": len(decisions), "reference_class_p85": ref["p85"],
        "median_percentile": 50, "commitment_percentile": cfg["forecast"]["commitment_percentile"],
    }
    facts["target_sprints"] = round(_working_days(start, date.fromisoformat(facts["target_date"]), off) / day, 2)
    status = rag(facts, cfg)
    step = 0.25
    hist: dict[float, int] = {}
    for x in mc:
        b = round(int(x / step) * step, 2)
        hist[b] = hist.get(b, 0) + 1
    report = weekly_report(facts, status, intake["findings"], decisions)
    unexplained = check_numbers(report, {**facts, "findings_list": intake["findings"], "decisions": decisions})
    _write(REPORTS / "cockpit.json", {"facts": facts, "status": status, "report_numbers_unexplained": unexplained,
                                      "histogram": {"step": step, "bins": sorted(hist.items())},
                                      "work_packages": wps, "findings": intake["findings"], "decisions": decisions})
    (REPORTS / "weekly_status.md").write_text(report)
    print(json.dumps(status, indent=1))
    if unexplained:
        raise SystemExit(f"weekly report has numbers not in the facts: {unexplained}")
    return 0


def _working_days(start: date, end: date, off: tuple) -> int:
    from datetime import timedelta
    n, d = 0, start
    while d < end:
        d += timedelta(days=1)
        if d.weekday() < 5 and d.isoformat() not in off:
            n += 1
    return n


def cmd_report(args) -> int:
    from mdc.report import build
    build()
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="mdc")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("intake")
    for name in ("parity", "engagements"):
        s = sub.add_parser(name)
        s.add_argument("--set", choices=("dev", "heldout"), default="dev")
        s.add_argument("--rerun", action="store_true")
    sub.add_parser("mistakes")
    sub.add_parser("cockpit")
    s = sub.add_parser("lock")
    s.add_argument("--force", action="store_true")
    sub.add_parser("report")
    a = p.parse_args(argv)
    return {"intake": cmd_intake, "parity": cmd_parity, "mistakes": cmd_mistakes, "engagements": cmd_engagements,
            "cockpit": cmd_cockpit, "lock": cmd_lock, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
