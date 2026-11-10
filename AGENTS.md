# AGENTS.md

## Fast feedback

```bash
python -m pytest                        # about 3 s; MONGO_URI=mongodb://... runs it on a real MongoDB
(cd web && npx tsc --noEmit && npx vitest run)
python -m mdc report                    # after any run
```

## Invariants

1. **The legacy app is not edited.** `legacy/jpetstore` is JPetStore 6, copied unchanged; the legacy side runs
   its own SQL.
2. **Parity compares behaviour, not code.** Both sides run the same journeys through the same ported service
   layer. Normalisation is limited to money precision and row order the SQL leaves undefined.
3. **A planted mistake that parity misses is reported, not hidden.**
4. **Planners never see the truth.** `forecast.py`, `status.py` and `intake.py` do not import `engagements.py`;
   engagements expose only points and findings to them.
5. **Numbers in a status report come from the facts.** `check_numbers` must pass before a report is written.
6. **Settings live in config.** Team, estimate weights, forecast and status rules are in `config/delivery.json`;
   decisions are in `config/decisions.json`.
7. **Reports are generated.** README numbers between the markers, `reports/REPORT.md` and `web/public/data.json`
   come from `python -m mdc report`.

## Held-out rule

`config/heldout.json` locks the held-out parity workloads and engagements by SHA-256. They run once, after the code
is frozen; the first run in `reports/heldout/` is the reported one. A rerun goes to `*_rerun.json`.
