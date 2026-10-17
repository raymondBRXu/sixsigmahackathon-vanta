# DockWatch synthetic data and generator

These files describe a **fictional** Ithaca-area bikeshare system. Every station
automatically records an accurate inventory at every scheduled hour. All stations
are open; every bike and dock is usable. There are **no missing readings, sensor
failures, manual counts, real customer records or measured local demand** in these
three datasets. Station locations are anchored to real Ithaca/Cornell landmarks,
but the bikeshare stations and every inventory record are simulated.

## Run the generator

Requires Python 3.9 or newer and the system's IANA timezone database; no third-party
Python packages are used. Keep the bundled `station_anchors.json` beside the script:
it is read offline, with no web request during generation. Run from the repository root:

```sh
python3 data/generate_data.py
```

This generates all three CSVs plus their simulation audit logs in `data/`. To generate one scenario:

```sh
python3 data/generate_data.py --scenario normal
python3 data/generate_data.py --scenario disruption
python3 data/generate_data.py --scenario edge_cases
```

Each selected scenario also writes `<scenario>_events.jsonl`. Each invocation writes
the common `stations.json`, `settings.json` and `generation_metadata.json`. Single-file runs and the all-files run produce
identical bytes for the same configuration, regardless of invocation order.
Metadata lists **expected** hashes for all scenarios, even if only one CSV has
been written. All outputs are UTF-8, with CSV columns in the order shown below.

Options:

| Option | Default | Meaning |
|---|---|---|
| `--scenario` | `all` | `all`, `normal`, `disruption` or `edge_cases` |
| `--seed` | `5300` | Integer seed controlling repeatable synthetic rides |
| `--start-date` | `2026-08-24` | First synthetic service date, a weekday in `YYYY-MM-DD` format |
| `--output-dir` | Script's directory | Destination for generated CSV/JSON/JSONL files; independent of the working directory |

For a separate experiment:

```sh
python3 data/generate_data.py --seed 123 --output-dir data/experiment_123
```

The command overwrites the named generated outputs in its destination. A single-
scenario run refuses to mix a new seed/calendar or changed generator output with
incompatible sibling CSVs. Use a new output directory or regenerate `--scenario all`
to replace the complete set. It also rejects sibling files whose bytes no longer
match their recorded hashes. It does not modify the application or Git remotes.

## Three scenarios

| File | Content | Purpose |
|---|---|---|
| `normal.csv` | A repeatable student-oriented day: morning class arrivals, midday campus/hub exchange, partial afternoon return and stronger evening return, plus modest random movements | Regular-operation demonstration; not a promise of zero inventory warnings or zero statistical signals |
| `disruption.csv` | Exactly the same first 25 days as `normal.csv`; stronger residential-to-academic morning transfers during the next 15 days | Operationally abnormal redistribution, potentially empty residential and crowded academic stations; no sensor/equipment fault |
| `edge_cases.csv` | Complete valid readings with controlled empty/full counts, exact/near inventory thresholds, a constant later-hour baseline, and balanced versus polarized networks | Verify boundary behavior without invalid or missing data |

Each file has **12,000 data rows**, plus one header: 20 stations × 15 hours × 40
service dates. The first 25 dates contribute 7,500 baseline rows; the last 15
contribute 4,500 monitoring rows. There are 600 complete snapshots per file, each
with all 20 stations observed. The **fleet** is 300 bikes and there are 600 dock
positions, but some bikes can be in transit. At every simulated instant:
`sum(docked bikes) + in_transit bikes = 300`. The CSV contains docked bikes only,
so its simultaneous station totals can be less than 300. Coverage is 100% against
the observation plan even while bikes are being ridden.

Default dates are the 40 weekdays from **2026-08-24 through 2026-10-16**. Baseline:
Aug 24–Sep 25; monitoring: Sep 28–Oct 16. All listed weekdays, including holidays,
are assumed comparable **within this fictional simulation**. This is not an
assertion about real Cornell schedules or holiday travel. `--start-date` generates
a new explicit 40-weekday plan and preserves local-time daylight-saving offsets.

## CSV codebook

| Column | Type / unit | Meaning |
|---|---|---|
| `timestamp` | ISO 8601 datetime with UTC offset | Exact scheduled local observation time in `America/New_York`, e.g. `2026-08-24T07:00:00-04:00` |
| `station_id` | String identifier | `S01`–`S20`, matching `stations.json` |
| `bikes` | Integer, bikes | Available usable bikes at that station; 0–30 inclusive |

Rows are ordered by timestamp then station identifier, with one row per station
and hour. Hours are 07:00–21:00 inclusive. Free docks can be derived as
`capacity - bikes`; occupancy is `bikes / capacity`. Zero bikes is a valid measured
empty station, not a missing reading. No customer attempts, separate pickups and
returns, trip destinations, journey times or exact downtime are recorded in
these snapshots. Under the explicitly known closed 300-bike fleet assumption,
**a complete simultaneous 20-station snapshot** permits the aggregate inference
`in_transit = 300 - sum(bikes)`. Missing stations, unusable bikes, repairs or bikes
outside the assumed fleet would invalidate that inference. Do not apply it to a
partial upload or infer individual trips from hourly net changes.

## Companion files

`stations.json` is an array of 20 station records, identical across scenarios:

| Field | Type / unit | Meaning |
|---|---|---|
| `station_id` | String | Unique key used in every CSV |
| `name` | String | Simulated station label referring to a real nearby landmark |
| `area` | String | Geographic grouping, with a higher station density around Cornell |
| `type` | String | `residential`, `academic`, `mixed`, `transport` or `recreation`; hypothetical trip context, not measured demand |
| `latitude` | Decimal degrees, WGS84 | Landmark anchor's north/south location; not a surveyed docking footprint |
| `longitude` | Decimal degrees, WGS84 | Landmark anchor's east/west location; not a surveyed docking footprint |
| `capacity` | Integer, positions | Fixed at 30 for every station |

Twenty simulated stations use real geographic anchors, with at least 12 around
Cornell housing, teaching buildings and libraries. Source URLs and coordinate
provenance are separate from `stations.json` to preserve the product schema.
Label the map
**“Ithaca — simulated bikeshare network.”** Coordinates identify landmark areas,
not approved or existing bikeshare docking locations.

`station_anchors.json` is the bundled generator input. It contains the seven station
fields above plus `source_url` (official Cornell venue or TCAT GTFS source) and
`coordinate_note` (how the location was obtained and its limits). The coordinates
were retrieved on 2026-10-16; the TCAT feed version is 20260922. Sources are also
copied into `generation_metadata.json` under `station_sources` for audit. Twelve
anchors are in Cornell core: five housing/community sites, six academic/library
sites and one student-union hub. Eight cover Collegetown, Downtown Ithaca,
East Ithaca, Cayuga Heights, South Hill and Stewart Park. Area/type labels are
simulation classifications. The Baker Tower anchor was checked against the official
Cornell Facilities building footprint; a valid landmark anchor still does not
establish the feasibility or permission for a physical docking site.

`settings.json` supplies product inputs independently of observed rows:

- `schema_version`: integer schema version (1).
- `timezone`: IANA timezone name, `America/New_York`.
- `service_dates`: ordered planned local dates (`YYYY-MM-DD`).
- `baseline_dates`, `monitoring_dates`: locked disjoint date lists, 25 and 15 dates.
- `hours`: scheduled local clock hours, integers 7–21.
- `station_ids`: complete planned station list.
- `collection_mode`: `automatic_complete_hourly_snapshots`.

Do not infer the planned calendar or baseline from whatever rows happen to be
uploaded. `generation_metadata.json` is **generation/audit information only**:
version, seed, provenance, parameters, scheduled/departed ride totals, expected
row counts and hashes, edge fixture locations, and limitations. Its
`snapshot_audit[scenario]` records `timestamp`, `docked` and `in_transit` at each
of the 600 exported instants. `expected_event_logs` records audit-log hashes.
Expected hashes for all scenarios do not mean all files were written in a
single-scenario invocation.

`normal_events.jsonl`, `disruption_events.jsonl` and `edge_cases_events.jsonl`
are chronological **simulator audit logs**, not real customer trip records and
not required dashboard inputs. Every line is a JSON object. The initial allocation
is `B001`–`B015` at S01, the next 15 at S02, continuing through `B300` at S20.

| Event / field | Meaning |
|---|---|
| `event` | `departure`, `arrival` or `reroute` |
| `timestamp` | Actual simulated event instant, timezone-aware ISO datetime |
| `bike_id`, `trip_id` | Audit identities tying a bike's departure to its later arrival; one bike cannot occupy two states |
| `station_id` | Departure origin, successful arrival station, or full station reached before rerouting |
| `destination_id`, `arrival_due` | Planned destination and next arrival time, for departures and reroutes |
| `flow` | Departure's hypothetical movement category; controlled edge rides are explicitly labeled |

The detector must not read audit labels, planned abnormal timing, generator
parameters or future trips to decide whether an observation signals. Keep the
application inputs to CSV, station configuration and the observation calendar.
Use the audit logs to explain and independently reproduce the simulation.
`generate_data.py` is the runnable generator; `test_generate_data.py` checks it.

## Continuous riding model

Only the **first service date** starts at 07:00 with 15 bikes per station.
The simulation then advances continuously through nights and weekends. Export
hours remain 07:00–21:00 on the 40 planned weekdays; an unexported hour is outside
the sampling plan, not a sensor failure. There is **no overnight reset or operator
rebalancing**. Tomorrow's 07:00 inventory reflects all intervening departures and
arrivals rather than copying yesterday's 21:00 inventory.

For example, a hypothetical 23:00 departure with a 23:25 arrival reduces the origin
and increases the destination before the next morning. A 06:50 departure arriving
at 07:15 remains in transit at 07:00. Other riders can also return bikes to either
station, so morning counts reflect **net** activity, not only overnight departures.

Each actual departure removes one available bike from the origin. It has a
strictly positive riding duration; there is no instantaneous station-to-station
transfer. On reaching the destination, the simulator checks capacity again. If
it is full, the bike stays in transit, takes additional time to a nearby station
with an available dock, and checks again there. Docks are not reserved by a
future arrival. An empty origin cannot release a bike. A bike still riding at
the final exported time stays in transit with a planned future arrival; it is
not artificially returned to make the final total 300.

Events use absolute UTC time, with local America/New_York time for hourly activity
and the output calendar. At equal event times, arrivals precede departures;
snapshots reflect all events due at the observation instant. The initial 07:00
snapshot precedes the first departure schedule. A date-indexed local calendar
and absolute duration arithmetic preserve meaning across daylight-saving changes.

The following are **hypothetical scheduled departure attempts**, not observed
customer demand or estimates from Cornell data. A scheduled departure may fail
because no bike is available, and only actual departures create trips.

| Local interval on weekdays | Scheduled directed activity, plus background circulation |
|---|---|
| 00:00–06:00 | Very low random nighttime activity, 0–2 attempts per hour |
| 06:00–07:00 | 4–8 pre-class residential-to-academic attempts, plus 2 background |
| 07:00–10:00 | 16–22 residential-to-academic attempts per hour, plus 10 background |
| 10:00–14:00 | 6–10 campus/hub attempts per hour, plus 6 background |
| 14:00–17:00 | 6–10 academic-to-residential attempts per hour, plus 6 background |
| 17:00–21:00 | 9–13 campus/hub-to-residential attempts per hour, plus 10 background |
| 21:00–24:00 | 2–5 late-return attempts per hour, plus 2 background |

Weekend movement uses lower-intensity recreational/hub circulation and nighttime
activity, without weekday class surges. Metadata records the exact schedule.
Departures are spread within each hour. Distance-weighted candidate pairs use
`1 / (1 + straight-line km)`; an illustrative detour factor, assumed cycling speed
and small handling/jitter allowance create positive ride durations. These are
synthetic design parameters, not measured routes, slope corrections or calibrated
travel-time estimates. See the generated metadata for the exact constants.

Only disruption's monitoring weekday morning intensity is increased to 48–54
directed attempts per hour. It starts at 07:00 on the first monitoring date.
Before then, normal and disruption share the same events and latent in-transit
state, including nights and weekends. Every baseline observation therefore matches.
Subsequent differences are consequences of the changed departure schedule and
capacity constraints, not a reset or injected stock. No station is replenished
by an operator in this generator.

Context sources accessed 2026-10-16: Cornell's [class meeting pattern](https://catalog.cornell.edu/enrollment-credit-requirements/class-meetings/)
supports using morning/afternoon class windows as a scenario design cue, and
[Ithaca neighborhoods](https://scl.cornell.edu/sub/residential-life/housing/campus-housing/housing-search-process/ithaca-neighborhoods)
describes student-housing areas and local terrain. Neither source measures bike
trip rates or journey times. Hills, road access, class attendance and actual
demand are not modeled; station types, departure intensities and riding durations
remain disclosed assumptions.

Random streams are seeded by absolute hourly interval for reproducibility;
that does **not** make the inventory observations independent. Inventories carry
across dates, so serial dependence, drift and boundary concentration may arise.
Normal and disruption share the entire baseline history exactly. H-03 must
compare the **same station and clock hour across dates**, then review baseline
suitability. This generator does not approve I-chart assumptions, calculate limits,
or guarantee detection. No rate has been retuned to manufacture a suitable chart.
The dashboard can later inform human operators; this generator does not implement
or assume their rebalancing decisions.

Additional fixtures in `edge_cases.csv`:

| Planned time, default calendar | Values | Intended later software check |
|---|---|---|
| Every baseline date/hour, including 12:00 | `S20 = 15` | Constant later-hour baseline must remain unsupported for calibrated statistical alarms |
| Sep 28, 09:00 | All 20 stations have 15 bikes | Balanced inventory: full fleet still 300 |
| Sep 28, 10:00 | `S01`–`S10 = 0`; `S11`–`S20 = 30` | Polarized inventory: same 300 bikes and 50% network occupancy, but no station provides both pickup and return space |
| Sep 28, 11:00 | `S01 = 6`, `S02 = 24`; `S03 = 5`, `S04 = 25`; `S05 = 0`, `S06 = 30`; remaining stations = 15 | Exact 20%/80% thresholds do not trigger strict low/high-stock rules; 5/25 do; valid empty/full observations |

For edge baseline history, S20 is excluded from departures, arrivals and reroutes,
so it stays at 15 without any hidden adjustment. On the first monitoring date,
random departures pause from midnight through noon and pre-existing trips must
finish before the controlled schedule. Positive-duration rides from 07:00 toward
the 09:00 target, 09:00 toward 10:00, and 10:00 toward 11:00 create the vectors
above. All rides must actually complete before their fixture snapshot: those
three targets sum to 300, so they intentionally have zero in-transit bikes at
those exact instants. Inventory is never overwritten and a pending trip is never
silently deleted. Other edge times can have bikes in transit.

These are explicitly **artificial rider schedules for software testing**, not
operator redistribution, measured demand or plausible typical weekday patterns.
With a different start date they occur on the 26th planned service date.
Insufficient history, malformed rows, duplicate keys and missing external uploads
belong to later H-03 software tests, not to these simulated operating scenarios.

## Validation and real collection

```sh
python3 -m unittest discover -s data -p 'test_*.py' -v
```

Checks cover schema, date/hour completeness, unique keys, ordered timezone-aware
timestamps, capacity bounds, fleet conservation, common baseline, fixtures,
independent bike-by-bike event replay matching all hourly CSV rows, actual
nighttime/weekend rides, positive-duration trips, arrival-time capacity checks,
reproducibility, separate/all equivalence, mixed-configuration and audit-log
protection, and a calendar crossing the daylight-saving change. The generator checks its own core
inventory invariants before writing. No product SPC implementation is included.

For real collection under the assumed sensor setup, station controllers would
timestamp and export available-bike counts on the common hourly schedule. The operator would maintain IDs,
coordinates and usable capacity, establish comparable service dates and baseline
approval, and validate clock synchronization and data quality. Real networks may
have equipment faults, closures, unavailable bikes and missing messages; the
current synthetic assumptions would require review before use in service. Where
telemetry is not yet available, the same proxy variables can be collected through
a timestamped station inventory count and a maintained capacity list; this is a
real-collection alternative, not a change to the accurate-automatic-sensor demo.

## Compatibility with the earlier demo

The CSV schema, station identifiers, geographic anchors, date/hour plan and three
scenario names are unchanged. Counts and all derived results **do change**. Remove
any application assertion that station counts must sum to 300, that network
occupancy is always 50%, or that next07:00 must equal previous21:00. Recompute
metrics, baseline diagnostics and frozen limits from v4; do not reuse v3 baseline
approvals or hard-coded demo numbers. An hourly net change remains a net change.
Only show inferred aggregate in-transit bikes when the complete snapshot and
closed-fleet assumptions hold. The generator does not change the running app or
publish files to GitHub.

## Verified v4 default output

Generated locally on 2026-10-16 with seed 5300. Each CSV still has 12,000 rows
and 600 complete snapshots; the 19 independent acceptance tests passed.

| Scenario | Docked bikes across the network | In-transit bikes |
|---|---:|---:|
| normal | 288–300 | 0–12 |
| disruption | 282–300 | 0–18 |
| edge_cases | 288–300 | 0–12 |

These are observed ranges for this seed, not bounds imposed on future generations.
For example, normal's bike B138 leaves S10 at Aug24 23:55:36 and arrives at S17
on Aug25 00:07:37. Bike B011 leaves S14 on Aug26 06:48:34 and arrives at S07 at
07:00:43, so it is in transit in that day's 07:00 snapshot. All times are local
EDT (UTC−04:00). These examples are generated events, not real trips.
