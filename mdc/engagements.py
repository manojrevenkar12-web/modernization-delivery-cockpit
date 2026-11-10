"""A synthetic world of modernization engagements, to check forecasts against truth.

Each engagement has work packages with points and findings (what a planner sees)
and a hidden truth: how much GenAI actually speeds the team up, how wrong each
estimate is, whether more scope turns up mid-way, and whether capacity dips (an
SME on leave, a test environment that is late). The engagement is played sprint
by sprint. Planners see only points, findings and the throughput each sprint.

Three ways to commit to a date at kickoff are scored:

  plan             the single-number plan
  monte_carlo      the 85th percentile of a Monte Carlo forecast from the
                   team's assumptions (config/delivery.json)
  reference_class  the plan times the 85th percentile of actual/plan in past
                   engagements (the dev set), the reference-class method

Whatever the commitment, a rolling forecast re-run every sprint from observed
throughput warns as soon as its 85th percentile passes it. A warning counts if it
comes before the committed date.
"""

from __future__ import annotations

import math
import random
import statistics

from mdc.forecast import monte_carlo_sprints, percentile, plan_sprints, rolling_sprints


def generate(seed: int, count: int, world: dict) -> list[dict]:
    rng = random.Random(seed)
    out = []
    for n in range(count):
        wps = []
        for i in range(rng.randint(*world["work_packages"])):
            wps.append({"id": f"WP{i + 1}", "points": rng.randint(*world["points"]),
                        "findings": [f"F{k}" for k in range(rng.randint(*world["findings"]))]})
        out.append({"id": f"E{seed}-{n + 1:03d}", "seed": rng.randrange(1 << 30), "work_packages": wps})
    return out


def play(engagement: dict, cfg: dict) -> dict:
    """Run one engagement to the end. Returns what each method committed and warned, and the truth."""
    team, fc, world = cfg["team"], cfg["forecast"], cfg["engagements"]
    rng = random.Random(engagement["seed"])
    plan_rng = random.Random(engagement["seed"] ^ 0x5EED)
    wps = engagement["work_packages"]
    total_points = sum(w["points"] for w in wps)

    # The truth, hidden from the planners.
    ts = world["true_speedup"]
    speed = rng.triangular(ts["low"], ts["high"], ts["mode"])
    effort = []
    for w in wps:
        sigma = world["true_sigma"]["base"] + world["true_sigma"]["per_finding"] * len(w["findings"])
        effort.append(w["points"] * team["engineer_days_per_point"] * rng.lognormvariate(0, sigma) / speed)
    sd = world["scope_discovery"]
    discovery = None
    if rng.random() < sd["probability"]:
        extra = total_points * rng.uniform(*sd["extra_share"])
        discovery = {"sprint": rng.randint(*sd["sprint"]), "points": extra,
                     "effort": extra * team["engineer_days_per_point"] * rng.lognormvariate(0, world["true_sigma"]["base"]) / speed}
    cd = world["capacity_dip"]
    dip = None
    if rng.random() < cd["probability"]:
        dip = {"start": rng.randint(*cd["start"]), "length": rng.randint(*cd["sprints"]), "drop": rng.uniform(*cd["drop"])}

    # Kickoff commitments.
    plan = plan_sprints(total_points, team)
    mc = monte_carlo_sprints(wps, team, fc, plan_rng)
    commit_mc = percentile(mc, fc["commitment_percentile"])
    commit_plan = plan

    # Play sprints.
    cap = team["engineers"] * team["sprint_days"] * team["focus_factor"]
    queue = [[e, w["points"]] for e, w in zip(effort, wps)]   # remaining effort, points
    observed: list[float] = []
    rolling: list[dict] = []
    sprint = 0
    while queue and sprint < world["max_sprints"]:
        if discovery and sprint == discovery["sprint"]:
            queue.append([discovery["effort"], discovery["points"]])
        budget = cap * (1 - dip["drop"]) if dip and dip["start"] <= sprint < dip["start"] + dip["length"] else cap
        done_points = 0.0
        while budget > 1e-9 and queue:
            e, p = queue[0]
            work = min(budget, e)
            share = work / e if e > 0 else 1
            done_points += p * share
            queue[0] = [e - work, p * (1 - share)]
            budget -= work
            if queue[0][0] <= 1e-9:
                queue.pop(0)
        sprint += 1
        observed.append(done_points)
        if queue and sprint >= fc["rolling_min_sprints"]:
            remaining = sum(p for _, p in queue)   # undiscovered scope is not in the queue yet
            samples = rolling_sprints(remaining, observed, fc, plan_rng)
            if samples:
                p85 = sprint + percentile(samples, fc["commitment_percentile"])
                p50 = sprint + percentile(samples, 50)
                rolling.append({"sprint": sprint, "p50": p50, "p85": p85})
    # Fractional finish: the last sprint counts only the share it was used.
    actual = sprint - 1 + min(1.0, observed[-1] / max(1e-9, max(observed))) if observed else 0.0
    if queue:
        actual = float(world["max_sprints"])
    return {"id": engagement["id"], "points": total_points, "actual": actual, "plan": commit_plan,
            "monte_carlo": {"p50": percentile(mc, 50), "p85": commit_mc}, "rolling": rolling,
            "discovery": discovery is not None, "dip": dip is not None}


def reference_class(results: list[dict], q: float = 85) -> dict:
    """Actual/plan ratios of finished engagements: the correction a planner applies."""
    ratios = [r["actual"] / r["plan"] for r in results if r["plan"] > 0]
    return {"engagements": len(ratios), "p50": round(percentile(ratios, 50), 3),
            "p85": round(percentile(ratios, q), 3), "p95": round(percentile(ratios, 95), 3)}


def commitments(r: dict, ref: dict | None) -> dict[str, float]:
    out = {"plan": r["plan"], "monte_carlo": r["monte_carlo"]["p85"]}
    if ref:
        out["reference_class"] = r["plan"] * ref["p85"]
    return out


def first_warning(r: dict, commitment: float) -> int | None:
    for x in r["rolling"]:
        if x["p85"] > commitment + 1e-9:
            return x["sprint"]
    return None


def score(results: list[dict], ref: dict | None = None, checkpoint: int = 3) -> dict:
    n = len(results)
    methods: dict[str, dict] = {}
    for name in commitments(results[0], ref):
        on_time, late, warned, lead, false_alarm, buffer = 0, 0, 0, [], 0, []
        for r in results:
            c = commitments(r, ref)[name]
            buffer.append(c - r["plan"])
            w = first_warning(r, c)
            if r["actual"] <= c:
                on_time += 1
                false_alarm += w is not None
            else:
                late += 1
                if w is not None and w < c:
                    warned += 1
                    lead.append(c - w)
        methods[name] = {"on_time": round(on_time / n, 3), "late": late, "late_warned_before_due": warned,
                         "median_warning_lead_sprints": round(statistics.median(lead), 2) if lead else None,
                         "false_alarms": false_alarm, "median_buffer_sprints": round(statistics.median(buffer), 2)}

    def at(r):
        rows = [x for x in r["rolling"] if x["sprint"] == checkpoint]
        return rows[0] if rows else None

    cp = [(r, at(r)) for r in results if at(r)]
    return {
        "engagements": n,
        "methods": methods,
        "mae_sprints": {"plan": round(statistics.fmean(abs(r["plan"] - r["actual"]) for r in results), 2),
                        "monte_carlo_p50": round(statistics.fmean(abs(r["monte_carlo"]["p50"] - r["actual"]) for r in results), 2),
                        f"rolling_p50_at_sprint_{checkpoint}": round(statistics.fmean(abs(x["p50"] - r["actual"]) for r, x in cp), 2) if cp else None},
        "rolling_p85_coverage_at_checkpoint": round(sum(r["actual"] <= x["p85"] for r, x in cp) / len(cp), 3) if cp else None,
        "checkpoint_sprint": checkpoint,
        "median_actual_sprints": round(statistics.median(r["actual"] for r in results), 2),
    }
