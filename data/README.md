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
it is read offline, with no web request during generation. Run from the personal repository root:

```sh
python3 data/generate_data.py
```

This generates all three CSVs in `data/`. To generate a single CSV:

```sh
python3 data/generate_data.py --scenario normal
python3 data/generate_data.py --scenario disruption
python3 data/generate_data.py --scenario edge_cases
```

Each invocation also writes the common `stations.json`, `settings.json` and
`generation_metadata.json`. Single-file runs and the all-files run produce
identical bytes for the same configuration, regardless of invocation order.
Metadata lists **expected** hashes for all scenarios, even if only one CSV has
been written. All outputs are UTF-8, with CSV columns in the order shown below.

Options:

| Option | Default | Meaning |
|---|---|---|
| `--scenario` | `all` | `all`, `normal`, `disruption` or `edge_cases` |
| `--seed` | `5300` | Integer seed controlling repeatable random transfers |
| `--start-date` | `2026-08-24` | First synthetic service date, a weekday in `YYYY-MM-DD` format |
| `--output-dir` | Script's directory | Destination for generated CSV/JSON files; independent of the working directory |

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
with 300 bikes and 600 dock positions. Coverage is 100% against the supplied plan.

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
returns, exact downtime or in-transit bikes are recorded or inferable from these
hourly snapshots alone.

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
The team geographic screenshot has not been provided. Label the future map
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
version, seed, provenance, assumptions, transfer parameters and generation-only
planned/successful transfer totals, expected row counts
and SHA-256 hashes, planted fixture locations and limitations. The application’s
detector must not read the planted scenarios or transfer parameters to decide
whether a point signals. `generate_data.py` is the reproducible generator;
`test_generate_data.py` contains its standalone acceptance checks.

## Model and edge fixtures

Only the **first service date** begins at 07:00 with 15 bikes per station. Inventory
then continues across all 40 dates: each station's next planned date at 07:00
equals its previous planned date at 21:00, including Friday-to-Monday. There is
**no nightly reset or operator redistribution**. The simulator assumes no activity
outside 07:00–21:00 or on unlisted weekend days; bikes remain where the previous
snapshot left them. This is an explicit time-window simplification, not a claim
that real bikes are never used at night or on weekends. Transfers move one bike
instantaneously between stations while
respecting 0–30 inventory bounds; they never create or remove a bike. All counts
below describe **synthetic transfer attempts**, not observed trips or customer
attempts. An attempted transfer is skipped if its source is empty or destination
is full; successful movements are reported separately in generation metadata.

| Hour ending at the snapshot | Normal model assumptions |
|---|---|
| 08:00–10:00 | 16–22 directed attempts per hour, residential to academic anchors, representing arrivals for class |
| 11:00–14:00 | 6–10 attempts per hour among academic/mixed/transport hubs, representing class changes, lunch and campus circulation |
| 15:00–17:00 | 6–10 attempts per hour, academic to residential, representing partial afternoon return |
| 18:00–21:00 | 9–13 attempts per hour, academic/mixed/transport to residential, including hypothetical evening library return |

Background circulation adds 10 symmetric pair attempts at hours 08, 09, 10, 17,
18 and 19, and 6 at other hours after 07. Pair weights are
`1 / (1 + straight-line distance in km)`, bounded by 1: closer anchors are more
likely to exchange bikes. This is not road distance, a routing model, elevation
adjustment or a travel-time estimate. Campus density and directional time windows
shape the daily pattern without claiming measured student travel behavior.

Only the disruption monitoring morning intensity is changed to 48–54 directed
attempts per hour at 08:00, 09:00 and 10:00. Later inventory follows from those
movements under the same afternoon/evening rules. There are no travel times or
in-transit inventories. Every parameter is a disclosed synthetic design choice,
not an estimate from Cornell schedules, sensor logs or Ithaca demand data.

Context sources accessed 2026-10-16: Cornell's [class meeting pattern](https://catalog.cornell.edu/enrollment-credit-requirements/class-meetings/)
supports using morning/afternoon class windows as a scenario design cue, and
[Ithaca neighborhoods](https://scl.cornell.edu/sub/residential-life/housing/campus-housing/housing-search-process/ithaca-neighborhoods)
describes student-housing areas and local terrain. Neither source measures bike
trip rates. Hills, road access, class attendance, travel time and actual demand
are not modeled; station types and transfer intensities remain assumptions.

Random streams are seeded separately by service-date index for reproducibility;
that does **not** make the inventory observations independent. Inventories carry
across dates, so serial dependence, drift and boundary concentration may arise.
Normal and disruption share the entire initial 25-day history exactly. The
baseline/monitoring labels describe data generation only. The dashboard uses all
hourly readings from a user-selected interval for exploratory Individuals limits,
without baseline approval or automatic alarms. This generator does not establish
I-chart assumptions or guarantee process stability. No rate has been retuned to
manufacture a suitable chart.
The dashboard can later inform human operators; this generator does not implement
or assume their rebalancing decisions.

Additional fixtures in `edge_cases.csv`:

| Planned time, default calendar | Values | Intended later software check |
|---|---|---|
| Every baseline date/hour, including 12:00 | `S20 = 15` | A constant selected interval retains CL = 15 but has no estimated UCL/LCL |
| Sep 28, 09:00 | All 20 stations have 15 bikes | Balanced inventory: full fleet still 300 |
| Sep 28, 10:00 | `S01`–`S10 = 0`; `S11`–`S20 = 30` | Polarized inventory: same 300 bikes and 50% network occupancy, but no station provides both pickup and return space |
| Sep 28, 11:00 | `S01 = 6`, `S02 = 24`; `S03 = 5`, `S04 = 25`; `S05 = 0`, `S06 = 30`; remaining stations = 15 | Exact 20%/80% thresholds do not trigger strict low/high-stock rules; 5/25 do; valid empty/full observations |

Fixtures use conserving transfers during daytime hours, but are deliberately
artificial software examples, not operator dispatch or claims about natural
commuting. They never change inventory between the last scheduled hour and the
next service-date opening. With a different start date, the planted
monitoring fixtures occur on its 26th planned service date; metadata records it.
Insufficient history, malformed rows, duplicate keys and missing external uploads
belong to later H-03 software tests, not to these simulated operating scenarios.

## Validation and real collection

```sh
python3 -m unittest discover -s data -p 'test_*.py' -v
```

Checks cover schema, date/hour completeness, unique keys, ordered timezone-aware
timestamps, capacity bounds, fleet conservation, common baseline, fixtures,
all 39 cross-date inventory transitions (including seven weekends), reproducibility,
separate/all equivalence, mixed-configuration protection, and a
calendar crossing the daylight-saving change. The generator checks its own core
inventory invariants before writing. No product SPC implementation is included.

For real collection, station controllers would timestamp and export available-
bike counts on the common hourly schedule. The operator would maintain IDs,
coordinates and usable capacity, declare the observation calendar, and validate
clock synchronization and data quality. Any future calibrated monitoring system
would also need a suitable stable reference period. Real networks may
have bikes in transit, equipment faults, closures and missing messages; the current
synthetic assumptions would require review before using the same model in service.
