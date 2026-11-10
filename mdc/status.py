"""Status for a steering meeting: RAG from evidence, and a weekly report whose
numbers can be checked.

Schedule, quality and risk each get a colour from rules in config/delivery.json:

  schedule  the committed finish (reference-class 85th percentile) against the
            customer's target date
  quality   share of legacy statements validated by parity
  risk      high findings with no agreed decision (config/decisions.json)

The overall status is the worst of the three, and every colour carries its reason.
`check_numbers` guards a drafted narrative, for example one an LLM wrote: every
number in the text must appear in the facts it was drafted from.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

ORDER = {"green": 0, "amber": 1, "red": 2}


def add_working_days(start: date, days: float, holidays: tuple[str, ...] = ()) -> date:
    d, left = start, int(round(days))
    while left > 0:
        d += timedelta(days=1)
        if d.weekday() < 5 and d.isoformat() not in holidays:
            left -= 1
    return d


def rag(facts: dict, cfg: dict) -> dict:
    st = cfg["status"]
    out = {}
    slip = (date.fromisoformat(facts["commit_date"]) - date.fromisoformat(facts["target_date"])).days
    if slip <= st["schedule_amber_days"]:
        out["schedule"] = ("green", f"committed finish {facts['commit_date']} is on or before the target {facts['target_date']}")
    elif slip <= st["schedule_red_days"]:
        out["schedule"] = ("amber", f"committed finish {facts['commit_date']} is {slip} days after the target")
    else:
        out["schedule"] = ("red", f"committed finish {facts['commit_date']} is {slip} days after the target")
    share = facts["statements_validated"] / facts["statements_total"]
    colour = "green" if share >= st["parity_green"] else "amber" if share >= st["parity_amber"] else "red"
    out["quality"] = (colour, f"{facts['statements_validated']} of {facts['statements_total']} legacy statements "
                              f"validated by parity, {facts['divergences']} open divergences")
    open_high = facts["open_high_findings"]
    colour = "red" if open_high >= st["open_high_red"] else "amber" if open_high >= st["open_high_amber"] else "green"
    noun = "finding" if open_high == 1 else "findings"
    out["risk"] = (colour, f"{open_high} high {noun} without an agreed decision")
    overall = max((c for c, _ in out.values()), key=ORDER.get)
    return {"overall": overall, **{k: {"colour": c, "reason": r} for k, (c, r) in out.items()}}


def weekly_report(facts: dict, status: dict, findings: list[dict], decisions: list[dict]) -> str:
    decided = {d["finding"] for d in decisions if d["status"] == "agreed"}
    lines = [f"# Weekly status, week ending {facts['status_week']}", "",
             f"**Overall: {status['overall'].upper()}**", "",
             "| Area | Status | Why |", "|---|---|---|"]
    for area in ("schedule", "quality", "risk"):
        lines.append(f"| {area.title()} | {status[area]['colour']} | {status[area]['reason']} |")
    lines += ["", "## Forecast", "",
              f"- Scope: {facts['work_packages']} work packages, {facts['points']} points from the code analysis",
              f"- Finish, {facts['median_percentile']}% likely: {facts['p50_date']}; committed "
              f"({facts['commitment_percentile']}% likely, from past engagements): {facts['commit_date']}; "
              f"target: {facts['target_date']}",
              "", "## Decisions needed", ""]
    open_items = [f for f in findings if f["id"] not in decided]
    lines += [f"- {f['id']} ({f['severity']}): {f['title']}. Proposed: {f['action']}" for f in open_items] or ["- None"]
    lines += ["", "## Decided this week", ""]
    lines += [f"- {d['finding']}: {d['decision']} ({d['owner']}, {d['date']})" for d in decisions]
    return "\n".join(lines) + "\n"


NUMBER = re.compile(r"(?<![\w-])\d+(?:[.,]\d+)?%?")


def check_numbers(text: str, facts: dict) -> list[str]:
    """Numbers in `text` that do not come from `facts` (dates are checked whole)."""
    allowed: set[str] = set()

    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)
        elif isinstance(v, bool) or v is None:
            return
        elif isinstance(v, (int, float)):
            allowed.update({str(v), f"{v:g}", str(round(v)), f"{v:.1f}", f"{v:.2f}", f"{v:g}%"})
            if 0 <= v <= 1:
                allowed.add(f"{round(v * 100)}%")
        else:
            allowed.update(NUMBER.findall(str(v)))
            allowed.add(str(v))

    walk(facts)
    dates = set(re.findall(r"\d{4}-\d{2}-\d{2}", text))
    bad = [d for d in dates if d not in allowed]
    stripped = re.sub(r"\d{4}-\d{2}-\d{2}", " ", text)
    stripped = re.sub(r"\b[A-Z]{1,3}\d{1,3}\b", " ", stripped)     # ids such as F03, WP2
    bad += [n for n in NUMBER.findall(stripped) if n not in allowed]
    return bad
