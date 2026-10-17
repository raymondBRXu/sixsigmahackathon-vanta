# DockWatch demo walkthrough

Start with `./app/testme` from the repository root. These checkpoints use the
bundled seed-5300 data and America/New_York time. The default is **Normal
operations**, September 28 at 09:00.

## 1. Normal operations: a complete hourly decision

The opening snapshot shows:

| Metric | Expected value |
|---|---:|
| Two-way availability | 90% (18/20 stations) |
| Empty stations | 2 (S15, S16) |
| Full stations | 0 |
| Coverage | 100% (20/20) |
| Selected S01 bikes / free docks | 17 / 13 |
| S01 adjacent-hour net change | -1 |

Hover a map marker to read its ID, name, count, capacity, free docks, observation
age and suggested action. Double-click a marker to select its station in the
sidebar and detail panel; the workspace stays on Operations. The station is
also selected when you open Analysis. S15/S16 suggest adding 15 bikes each.
The queue lists station IDs, readable names and target amounts; it does not
promise a feasible balanced route.

Press Play: one complete hourly snapshot advances every two seconds. Pan the map;
its view remains in place while colors, hover values, metrics and queue change.
Pause and step once. At September 28, 10:00, availability is 75%, empty count 2,
full count 3 and coverage 100%. The state is simulated, not live telemetry.

Return the clock to September 28, 09:00, select S01, and open Analysis. Playback
pauses. The analysis range initially spans the available history through the
displayed time. Use its two handles to select September 28, 07:00–09:00.

| Interval result | Expected value |
|---|---:|
| Hourly bikes | 21, 18, 17 |
| Valid / planned readings | 3 / 3 |
| Valid moving-range pairs | 2 |
| CL | 18.666667 |
| Estimated LCL | 13.347518 |
| Estimated UCL | 23.985816 |

The interval includes both endpoints and all hours between them. Changing either
endpoint recalculates the mean and estimated limits. Explain that intraday
patterns, bounded counts and serial dependence affect interpretation; these
limits do not establish a stable process or an automatic fault. There is no
review form, baseline diagnostic section, crossing count or SPC alarm. The
current-day inventory chart and network occupancy heatmap remain below it.

Scrub the shared clock to August 24, 07:00. The range is capped at that first
slot: S01 has one observed count of 15 and CL=15, but no adjacent variation from
which to estimate UCL/LCL. Future data are excluded. Return to September 28 to
continue.

## 2. Morning disruption: an operational contrast

Select Morning disruption. At September 28, 09:00 the expected snapshot has
3 empty stations, 5 full stations, 60% two-way availability and 100% coverage.
The source has the same first 25 service days as normal but stronger morning
transfers in the last 15. This split describes scenario construction; it does not
set an application baseline or analysis gate. The app receives inventory
observations, not planted labels.

Interpret this as a synthetic scenario contrast, not evidence that a real
intervention improved customer outcomes or an automatic proof of SPC validity.

## 3. Edge cases: service is not average occupancy

Select Edge cases and start at the default September 28, 09:00.

| Time | Empty | Full | Two-way | Network occupancy |
|---|---:|---:|---:|---:|
| 09:00 | 0 | 0 | 100% | 50% |
| 10:00 | 10 | 10 | 0% | 50% |
| 11:00 | 1 | 1 | 90% | 50% |

At 09:00 all stations have 15 bikes. At 10:00 half are empty and half full.
The same total occupancy can represent completely different service availability.
At 11:00 S01/S02 hold 6/24 bikes (exact 20%/80%: no threshold action), while
S03/S04 hold 5/25 (add/remove 10). S05/S06 are empty/full (add/remove 15).

Select S20 in Analysis and set the interval to August 24, 07:00–September 25,
21:00. Its 375 hourly readings are all 15, so the chart shows those counts and
CL=15. Its moving ranges are zero, so no UCL/LCL can be estimated. Operational
rules still work.
Missing/invalid records are tested in software fixtures; this CSV is complete.

## Verification and presentation

```sh
uv run --frozen --extra api pytest tests data/test_generate_data.py -q
npm test --prefix app/frontend
uv run --frozen --extra api python - <<'PY'
from dockwatch.data import load_bundle
from dockwatch.qc import snapshot_at, snapshot_metrics, individual_limits, station_history
obs, stations, settings = load_bundle('data')
print(snapshot_metrics(snapshot_at(obs, stations, '2026-09-28T09:00:00-04:00')))
print(individual_limits([10, 12, 11, 13, 14]))
history, summary = station_history(
    obs, settings, 'S01',
    '2026-09-28T07:00:00-04:00', '2026-09-28T09:00:00-04:00',
)
print(summary)
PY
```

The arithmetic fixture produces CL=12, LCL=8.010638298, UCL=15.989361702.
The interval call reproduces the S01 table above. The suite also checks inclusive
endpoints, recalculation, selected-window isolation, missing-hour and overnight
gaps, constant/single observations, unknown stations and invalid/duplicate
records. Missing observations remain missing, never zero.

A concise judge demonstration: normal snapshot and hover → double-click selection
→ playback → interval analysis → disruption → balanced/polarized edge case.
Explain the supervisor's decision, the three measured inputs, the denominator and
the method's limitations. The public deployment and logged-out browser check are
still pending; follow app/README.md when publishing is authorized.
