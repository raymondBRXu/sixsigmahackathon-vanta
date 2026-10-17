# DockWatch v5 — two synthetic demonstration datasets

This is a **deliberately designed teaching and software-test fixture**, not real
Ithaca telemetry, a calibrated demand model, or evidence that a real bikeshare
process is stable. Real geographic landmarks anchor20 fictional stations.
All20 stations have30 usable dock positions; the closed fleet has300 usable bikes.
Sensors are accurate and complete. There are no faults, lost readings or manual
inspections. The first25 service dates supply a common reference; the next15
supply monitoring observations.

## Generate and run

From the repository root, with Python3.9+ and its IANA timezone database:

```sh
python3 data/generate_data.py
```

The script uses Python's standard library. Keep the entire `data/` folder,
including `station_anchors.json`, `README.v5.md` and `_qc_snapshot.py`; do not copy
only the generator. This data-only branch does not include the dashboard app.

For a complete app checkout, the loader prefers `app/qc.py`. When that file is
absent, it loads `data/_qc_snapshot.py`, an **unchanged, byte-for-byte copy** of the
app detector used to generate and validate this v5 release. No formulas have been
rewritten. Before importing the fallback, the loader verifies its SHA256:

```text
e5e1b4824b41450ed10963f91ab27061ee774afe1682abd29841bbcec47b6384
```

The `app/qc.py` detector label in the existing metadata, validation report and demo
guide identifies that source implementation; this publication supplies the same
bytes under the fallback filename. Those original reports and CSV/event-log hashes
are preserved. If integrated into an app with a modified detector, rerun validation
with that app; do not assume a different implementation has identical results.

| Option | Default | Meaning |
|---|---|---|
| `--seed` |5300| Repeatable variation; all acceptance checks still have to pass |
| `--start-date` |2026-08-24| First fictional service date, a weekday |
| `--output-dir` |The script's folder| Destination for the complete two-scenario set |

Both CSVs are generated together so their reference history and configuration
stay synchronized. The compatibility option`--scenario all`means the same matched
pair; there is no third-scenario or single-scenario option.
To try a separate output without changing the dashboard's active data:

```sh
python3 data/generate_data.py --output-dir /tmp/dockwatch-data-preview
```

New data are checked before replacement. Existing named generated outputs,
including legacy `edge_cases.csv` and its log, are archived in a timestamped
`.dockwatch-data-backups` folder beside the output folder. The script does not
change Git branches or upload anything. If these files are integrated into the
complete dashboard app, stop and restart that app after generating: its backend
caches CSVs and settings in memory. This branch alone does not provide a web server.
See [RUN_IN_CURSOR.md](RUN_IN_CURSOR.md).

## What the two CSVs demonstrate

| File | Designed behavior | Demonstration |
|---|---|---|
| `normal.csv` | Diurnal commute inventory with bounded seeded variation; every exported count6–24 | No operational warnings and zero actual point/8-side/6-trend monitoring candidates in all300 station/hour strata |
| `disruption.csv` | Identical pre-change history followed by varied, disclosed rider-event windows | Empty/full P1; low/high P2; exact6/24 boundaries; allthree statistical rules, including an event with6–24 stock and no inventory action |

Each has **12,000 data rows**, one header and600 complete snapshots:
20stations ×40fictional comparable weekdays ×15hours(07:00–21:00 inclusive).
Default reference dates are Aug24–Sep25,2026; monitoring is Sep28–Oct16,2026.
Weekdays include any real holidays: comparability is a simulation assumption,
not a claim about Cornell's real class or service calendar.

The normal acceptance condition is a finite demonstration constraint. Construction
and rejection of candidate schedules are disclosed in generation metadata; the
absence of rule violations does not prove independence, a normal distribution,
process capability, or a calibrated false-alarm rate. Baseline review stays manual.
The generator validates reference diagnostics instead of hiding candidates through
constant/unsupported histories or an unsuitable-review flag. It never changes
operational thresholds or the dashboard's statistical formulas.

## CSV codebook

| Column | Type and unit | Definition |
|---|---|---|
| `timestamp` |ISO8601 offset-aware datetime| Scheduled observation in America/New_York, e.g.2026-08-24T07:00:00-04:00 |
| `station_id` |String| S01–S20, matching the station configuration |
| `bikes` |Integer, bikes| Usable bikes docked at that station at that instant;0–30 |

Rows are ordered by time and station, exactly one per planned key. `-04:00` means
UTC minus4hours, not a duration or recording window. Dates crossing daylight-saving
changes use the appropriate local offset. Zero is a valid empty observation.
Free docks=`capacity-bikes`; occupancy=`bikes/capacity`.

The CSV records **docked inventory**, not trip counts, failed attempts, exact
downtime or demand. Only under the complete, simultaneous20-station and closed
fault-free fleet assumptions may the dashboard infer `in_transit=300-sum(bikes)`.
Partial uploads cannot support that inference. Adjacent-hour inventory changes
are net changes; they do not identify separate departures or arrivals.

## Continuous bike accounting and synthetic movement

Initialize15 bikes per station only once at the first07:00. A departure removes
one identified bike, positive elapsed riding time keeps it in transit, and an
arrival adds it only if a dock is available. Full arrivals require positive-time
rerouting. State persists across nights, weekends and the baseline boundary.
No bike is created, removed, teleported or reset. No operator moves, nightly
redistribution or dashboard recommendations are executed by the generator.

Movement schedules are designed synthetic commuter itineraries with morning
campus-bound travel, midday circulation, evening returns and lower night activity.
The network is simplified into ten independent two-station rider corridors,
each retaining30bikes across its two endpoints and in-transit state. Late rides
are deliberately timed to remain in transit at observation and arrive2–3minutes
later. Exact corridor/profile, timing and noise assumptions are recorded in
`generation_metadata.json`. These restrictions are teaching simplifications,
not empirically validated travel behavior. These patterns demonstrate the UI and rules; they are
not measured origin-destination demand or optimized dispatch. Deliberately designed
rider schedules must not be described as empirically realistic passenger behavior.
Off-hours schedules move forward from the prior evening inventory with sparse
rider movements; they do not target a preselected next-morning stock. Night
departures and later arrivals determine the next07:00 reading, including bikes
still in transit. At every event, docked plus in-transit equals300. Every exported
snapshot is checked against the independent event ledger.

The offline constructor can inspect the entire constructed fixture to check its
acceptance conditions. **The dashboard cannot:** it scores only data at/before
the simulated clock, estimates the first25 fully elapsed reference dates, freezes
those limits and evaluates monitoring windows only when their last point arrives.
Audit labels and planned event windows are not statistical detector inputs.

## Companion files and units

- `stations.json`: station_id/name/area/type; latitude/longitude in WGS84 decimal
  degrees; capacity in dock positions(30). IDs/coordinates do not change between
  the two scenarios. Area and function are descriptive, not SPC subgroups.
- `station_anchors.json`: offline generator source with the station fields,
  `source_url` and `coordinate_note`. Twelve anchors are in Cornell core and eight
  surrounding Ithaca; Cornell venue and TCAT stop coordinates identify real places,
  not actual bikeshare facilities, surveyed footprints or installation permission.
- `settings.json`: schema_version1, IANA timezone, ordered service_dates,
  baseline_dates, monitoring_dates in YYYY-MM-DD, integer local hours7–21,
  station_ids and automatic_complete_hourly_snapshots collection mode. The planned
  calendar is independent of observed CSV coverage.
- `generation_metadata.json`: synthetic provenance, version/seed/calendar,
  construction and travel assumptions, station sources, expected file hashes,
  per-snapshot docked/in-transit counts, and scenario construction details.
- `validation.json`: actual acceptance results from the generated pair, including
  normal rule checks, capacity/fleet checks and detected disruption examples.
- `demo_guide.md`: actual station/date/hour examples and explanations, regenerated
  with the pair. Use these verified locations rather than the oldv4 examples.
- `normal_events.jsonl`, `disruption_events.jsonl`: audit-only chronological
  simulated events. They are not extra scenarioCSVs or required chart inputs.
- `generate_data.py`, `test_generate_data.py`: generator and reproducible acceptance
  tests; `README.v5.md` is the template copied to README.md on successful generation.
- `_qc_snapshot.py`: the verified, unchanged source detector snapshot described above;
  used only when the complete app detector is absent.

Event log fields:

| Field | Definition |
|---|---|
| `event` |departure, arrival or reroute|
| `timestamp` |Offset-aware physical event time|
| `bike_id`, `trip_id` |Synthetic identities connecting each departure and later arrival|
| `station_id` |Origin, arrival station, or full destination being rerouted|
| `destination_id`, `arrival_due` |Planned next destination and future arrival time, for departures/reroutes|
| `flow` |Disclosed hypothetical rider-schedule category on a departure|

B001–B015 initially belong toS01, B016–B030 toS02, continuing toB286–B300 atS20.
Pending rides at the final21:00 remain in transit, with due times in the log.
They are not forced to finish to make docked inventory equal300.

## Rules and verification

Operational policy:0/30=P1;1–5/25–29=P2;6–24inclusive=no warning.
Advice targets15:3bikes→add12;27bikes→remove12. Quantities are suggestions for
human review, not a dispatched vehicle or optimized route.

Same-station/same-hour Individuals limits use the locked reference:
MR=absolute adjacent-date change; sigma=MRbar/1.128; CL=mean; limits=CL±3sigma.
Rules: strict point outside limits;8strictly on one side;6strictly increasing or
decreasing. Equality toCL breaks a side run; ties break trends. These are separate
from6/24 operational thresholds. Sources:
[course PythonSPC chapter](https://timothyfraser.com/sigma/chapters/statistical-process-control-in-python.html),
[NIST Individuals charts](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc322.htm).

```sh
python3 -m unittest discover -s data -p 'test_generate_data.py' -v
```

This command runs from this data-only branch without an `app/` folder. For a
separate, complete dashboard checkout, its additional app tests may be run with
`.venv/bin/python -m pytest tests -q` after installing that app's dependencies.
The app test suite and web launcher are not included in this branch.

Read the current command output and validation report for actual results. Tests
cover independent event replay, correct rule examples, shared history, time
cutoffs and no autoapproval. Degenerate/invalid uploads remain software tests;
they are not sensor failures hidden inside the two demonstration scenarios.

## Collecting real observations

Station controllers would synchronize clocks and export usable-bike counts hourly.
Operators would maintain station IDs, usable capacity and coordinates, establish
comparable dates, investigate missingness/faults, and review a suitable reference.
Real use would require revisiting these simplifying assumptions. Neither accurate
simulation readings nor a clean finite example establish real-world reliability
or a causal effect of rebalancing.
