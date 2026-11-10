"""Forecasting delivery: a single-number plan, Monte Carlo at kickoff, and a rolling
forecast from the throughput the team actually achieves.

Effort per work package is its points times a log-normal factor whose spread grows
with the findings attached to it, divided by a GenAI speed-up drawn from a
triangular range (config/delivery.json). Capacity per sprint is engineers x
sprint days x focus factor. The rolling forecast replaces the assumed speed-up
and spread with the points per sprint observed so far, resampled.
"""

from __future__ import annotations

import math
import random
import statistics


def percentile(values: list[float], p: float) -> float:
    s = sorted(values)
    if not s:
        return math.nan
    k = (len(s) - 1) * p / 100
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def capacity_days(team: dict) -> float:
    """Engineer-days of focused work per sprint."""
    return team["engineers"] * team["sprint_days"] * team["focus_factor"]


def plan_sprints(points: float, team: dict) -> float:
    """The classic plan: points at the expected speed-up, no spread, no surprises."""
    effort = points * team["engineer_days_per_point"] / team["genai_speedup"]["mode"]
    return effort / capacity_days(team)


def monte_carlo_sprints(wps: list[dict], team: dict, fc: dict, rng: random.Random) -> list[float]:
    out = []
    sp = team["genai_speedup"]
    cap = capacity_days(team)
    for _ in range(fc["simulations"]):
        speed = rng.triangular(sp["low"], sp["high"], sp["mode"])
        effort = 0.0
        for wp in wps:
            sigma = fc["effort_sigma"]["base"] + fc["effort_sigma"]["per_finding"] * len(wp.get("findings", []))
            effort += wp["points"] * team["engineer_days_per_point"] * rng.lognormvariate(-sigma * sigma / 2, sigma)
        out.append(effort / speed / cap)
    return out


def rolling_sprints(remaining_points: float, observed: list[float], fc: dict, rng: random.Random) -> list[float]:
    """Sprints still needed, from resampled observed points-per-sprint."""
    if not observed or max(observed) <= 0:
        return []
    out = []
    for _ in range(fc["simulations"]):
        left, sprints = remaining_points, 0.0
        while left > 1e-9 and sprints < 200:
            done = rng.choice(observed)
            if done >= left:
                sprints += left / done if done > 0 else 1
                left = 0
            else:
                left -= done
                sprints += 1
        out.append(sprints)
    return out


def summary(samples: list[float]) -> dict:
    return {"p50": round(percentile(samples, 50), 2), "p85": round(percentile(samples, 85), 2),
            "p95": round(percentile(samples, 95), 2), "mean": round(statistics.fmean(samples), 2)}
