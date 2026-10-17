# DockWatch data: v5 scenarios in the current dashboard

These are deliberately designed teaching and software-test fixtures for a fictional
Ithaca-area bikeshare network. The two sources are `normal.csv` and `disruption.csv`.
Neither is real telemetry, a calibrated demand model, or evidence of process stability.
The former `edge_cases.csv` is no longer a source; disruption includes inventory
boundary examples, and software tests cover missing, invalid and degenerate inputs.

Each CSV has **12,000 observations**: 20 stations × 40 scheduled weekdays × 15 hours,
07:00–21:00 America/New_York. Default dates are **August 24–October 16, 2026**.
Every station has 30 usable docks. All fixture readings are accurate and complete.
Listed weekdays, including holidays, are assumed comparable within this simulation;
this is not a real Cornell operating calendar.

## Current dashboard and preserved generation checks

The incoming data release includes a preserved statistical implementation and its
original reports. They describe a different workflow from the current dashboard:

| | Published v5 generation checks | Current React History |
|---|---|---|
| Limits | First 25 reference dates, frozen for the final 15 dates | Estimated from the selected station/hour and date range |
| Rules | Point beyond limits, eight on one side, six-point trend | All eight course-image tests when Diagnosis is enabled |
| Clock | Historical detector evaluates elapsed monitoring windows | History reads all collection dates independently of playback |
| Review | Historical reference-review states | No reference approval or frozen monitoring workflow |
| Diagnosis range | Reference and monitoring periods | All 40 dates selected and locked until Diagnosis is disabled |

`README.v5.md`, `demo_guide.md`, `validation.json` and detector labels in
`generation_metadata.json` are preserved publication artifacts. References there
to `app/qc.py`, Analysis, baseline collection, manual review and three-rule
zero-candidate results describe the historical detector. They are not instructions
for the current UI or claims about its eight-rule results. The generator prefers
`app/qc.py` if present; this checkout instead uses `data/_qc_snapshot.py`, since
current statistics live in `app/dockwatch/`. Its SHA256 is verified before loading:

```text
e5e1b4824b41450ed10963f91ab27061ee774afe1682abd29841bbcec47b6384
```

For example, current History on **normal, S01, 07:00, all dates** detects T3:
four contributing points in one matching window. That does not contradict the
published zero-candidate result under different rules and limit periods. Use
[the current walkthrough](../demo/README.md) for verified UI checkpoints.
The dashboard detector never reads intended disruptions, event logs or generator
parameters as evidence that an observation matches a rule.

## Scenarios and CSV codebook

| File | Construction | Current operational interpretation |
|---|---|---|
| `normal.csv` | Designed diurnal inventory with bounded seeded variation; every count is 6–24 inclusive | No strict inventory warning; exploratory History patterns remain possible |
| `disruption.csv` | Same first 25 dates, then disclosed rider-event windows | Empty/full, low/high, exact 6/24 boundaries and cross-date patterns |

August 24–September 25 observations are identical between sources; September
28–October 16 supplies the contrast. These construction labels do not configure
current History limits. Candidate profiles were deliberately selected using the
frozen generator checks. Finite acceptance does not establish independence,
normality, process capability or a calibrated false-alarm rate.

| Column | Type / unit | Meaning |
|---|---|---|
| `timestamp` | ISO 8601 datetime with UTC offset | Exact planned local observation, e.g. `2026-09-28T09:00:00-04:00` |
| `station_id` | String | `S01`–`S20`, matching `stations.json` |
| `bikes` | Integer, bikes | Usable bikes docked at that station at the instant; 0–30 inclusive |

Rows are time/station ordered, with one per planned key. Zero is a valid empty
reading; a missing upload reading is an absent row, not an inferred zero. Free
docks are `capacity - bikes`; occupancy is `bikes / capacity`. Inventory changes
do not identify separate departures and arrivals. CSVs do not measure customer
attempts, trip demand, exact outage duration or intervention effects.

## Positive-duration rides and continuous accounting

The closed fleet has **300 bikes across docked and in-transit states** and 600
dock positions. Each bike starts docked at the first 07:00 only: 15 per station.
Departure removes an identified bike; strictly positive riding time keeps it in
transit; arrival adds it only when a dock is available. Full destinations require
positive-time rerouting. Docked plus in-transit equals 300 throughout the event
model. The CSV's docked total alone usually does not equal 300.

State persists through nights and weekends. Sparse overnight riders evolve from
the prior inventory; there is no daily reset, operator redistribution or execution
of dashboard recommendations. Final pending rides remain in transit. Ten two-station
rider corridors, seeded variation and deliberately timed late rides simplify the
model. These are disclosed teaching assumptions, not measured passenger behavior,
road routing or optimized dispatch.

Only for a complete simultaneous snapshot of this closed, fault-free fleet does
`300 - sum(bikes)` equal in-transit inventory. Normal on September 28 at 09:00 has
291 docked and 9 in transit; disruption has 296 docked and 4 in transit. Partial
uploads cannot support this inference. The dashboard reports docked observations
and does not display an inferred trip count. Optional fleet validation only
checks that observed docked totals do not exceed 300; independent event replay
verifies conservation.

## Companion files and event codebook

- `stations.json`: `station_id`, `name`, `area`, `type`, WGS84 `latitude`/`longitude`
  in decimal degrees and `capacity` in docks. IDs, coordinates and capacities match
  across scenarios. Area/type are descriptive, not statistical subgroups.
- `station_anchors.json`: offline landmark sources with `source_url` and
  `coordinate_note`. Twelve anchors are in Cornell core and eight in surrounding
  Ithaca. These are real places, not existing or approved bikeshare facilities.
- `settings.json`: schema version, IANA timezone, ordered `service_dates`,
  construction-only `baseline_dates`/`monitoring_dates`, local integer `hours`
  7–21, `station_ids` and collection mode. Coverage uses this independent plan.
- `generation_metadata.json`: seed/version, construction assumptions, station
  provenance, expected hashes, per-snapshot docked/in-transit counts and audits.
- `normal_events.jsonl`, `disruption_events.jsonl`: chronological synthetic event
  ledgers for audit, not extra scenario CSVs or required chart inputs.
- `validation.json`, `demo_guide.md`, `README.v5.md`, `_qc_snapshot.py`: preserved
  generation-time checks, examples, template and detector, scoped above.
- `generate_data.py`, `test_generate_data.py`: generator and independent checks,
  including physical replay, historical detector checks and reproducibility.

| Event field | Meaning |
|---|---|
| `event` | `departure`, `arrival` or `reroute` |
| `timestamp` | Offset-aware physical event time |
| `bike_id`, `trip_id` | Synthetic identities linking departure and later arrival |
| `station_id` | Origin, arrival station or full destination being rerouted |
| `destination_id`, `arrival_due` | Next destination and future arrival time |
| `flow` | Disclosed synthetic rider-schedule category on a departure |

B001–B015 begin at S01, continuing in groups of 15 through B286–B300 at S20.
Snapshots follow due arrivals and departures. Published CSVs and ledgers remain
unchanged in this integration.

## Regeneration and verification

The generator uses Python 3.9+ and the system IANA timezone database. Keep the
complete data folder, including anchors, the README template and detector snapshot.
Use a separate preview directory when checking reproducibility:

```sh
python3 data/generate_data.py --output-dir /tmp/dockwatch-data-preview
python3 -m unittest discover -s data -p 'test_generate_data.py' -v
uv run --frozen --extra api pytest tests data/test_generate_data.py -q
```

Both scenarios are generated together. Options are `--seed` (5300), `--start-date`
(`2026-08-24`, a weekday), `--output-dir` (this data directory) and the compatibility
option `--scenario all`. There is no single-source or third-scenario mode.
Existing generated outputs are archived in a timestamped `.dockwatch-data-backups`
folder before replacement. Default regeneration also replaces this integrated
README with the historical `README.v5.md` template; review documentation when
adopting regenerated files. Restart the dashboard after replacing data because
its backend caches observations and configuration.

Application tests separately check current eight-rule decisions, same-hour limits,
missing/constant/single readings, validation and API behavior. The generation
report alone does not validate current dashboard results. Operational thresholds
are strictly below 6 or above 24; exactly 6/24 does not trigger. Popup quantities
target 15 for human review and are not an arranged dispatch.

For real collection, station controllers would export synchronized usable-bike
counts; operators would maintain the plan and investigate faults, closures,
missingness and capacity changes. Bounded counts, temporal dependence and deliberate
fixture construction limit interpretation. Calibrated monitoring would require
separate suitability validation.
