# DockWatch Documentation
*Project README, user guide, methods and data codebook*

**Team Vanta · Cornell Six Sigma Hackathon · Bikeshare Fleets**

**[Open the public dashboard — no sign-in required](https://connect.systems-apps.com/content/ca01a272-5237-45e0-ac0c-4f3453f50c4c/)** ·
[Public API documentation](https://connect.systems-apps.com/content/ca01a272-5237-45e0-ac0c-4f3453f50c4c/api/docs).
Use these hosted links to try the tool without installing it. Local setup follows below.

DockWatch helps a bikeshare operations supervisor answer: **which station needs
attention, what inventory action should I review, and what patterns deserve
investigation?** It combines a React dashboard, FastAPI service and reusable
Python statistical library.

This document contains the complete project README and dataset codebook, followed
by function/parameter references and a reproducible demonstration. It describes
main revision `253ecc7d3e5e9bf8bdbfb2ef88b25e705e81aa97`, reviewed October 17, 2026.
The original source, datasets and separate READMEs remain in the repository.

**Read this distinction first:** current inventory actions follow the simulation
clock. History examines the loaded collection period independently of that clock.
The 6/15/24 inventory references are operating policy values; History estimates
statistical limits from observed data. Historical pattern matches do not create
inventory move orders.

### Contents

1. [Project README and setup](#project-readme-and-setup)
2. [Using each dashboard function](#using-each-dashboard-function)
3. [Inventory measures and action rules](#inventory-measures-and-action-rules)
4. [History calculations and diagnosis](#history-calculations-and-diagnosis)
5. [Data README and complete codebook](#data-readme-and-complete-codebook)
6. [API and Python function reference](#api-and-python-function-reference)
7. [Demonstration and known-answer results](#demonstration-and-known-answer-results)
8. [Reproduction, checks and handoff](#reproduction-checks-and-handoff)
9. [Requirements and sources](#requirements-and-sources)

## Project README and setup

### Purpose, user and scope

The intended user reviews inventory hourly, checks urgent stations on a map,
confirms the latest count, and arranges manual rebalancing. They can separately
investigate a station at the same operating hour across dates.

The demonstration covers **20 fictional Ithaca-area stations, 30 docks per
station, and 300 bikes docked or in transit**. Two synthetic CSVs provide normal
inventory and disruption examples. There is no live telemetry, automatic dispatch,
route optimization, forecast, customer-failure estimate or persistent user database.

The interface uses React/Vite and MapLibre; FastAPI serves the built page and API
from one process. Python implements all statistical decisions. Interactive charts
use React SVG; Plotnine supplies additional static API charts.

### Install and start

Prerequisites: **Python 3.12**, **uv**, **Node.js 22+**, **npm**, and Git.
The first installation needs internet. Street-map tiles also use internet;
the map supports a tile-free station view.

```bash
git clone https://github.com/raymondBRXu/sixsigmahackathon-vanta.git
cd sixsigmahackathon-vanta
./app/testme
```

Open **http://127.0.0.1:8000/**. The API explorer is
**http://127.0.0.1:8000/api/docs**. Stop the local server with Ctrl+C.
If port 8000 is occupied, use `PORT=8001 ./app/testme`.

`app/testme` installs locked Python and JavaScript dependencies, builds React,
then starts FastAPI. Run it from the repository root. The helper names
`testme`, `manifestme` and `deployme` have **no `.sh` suffix**.

For development, use separate terminals:

```bash
# Terminal 1: Python API
uv sync --frozen --extra api
uv run --frozen --extra api uvicorn app.api:app --host 127.0.0.1 --port 8000
```

```bash
# Terminal 2: React development server
npm ci --prefix app/frontend
npm run dev --prefix app/frontend
```

Use the local URL printed by Vite. Its development proxy sends API requests to
port 8000; the production page uses relative URLs within the deployed content.

### Project files

| Location | Purpose |
|---|---|
| `app/frontend/` | Dashboard controls, map, charts and interaction tests |
| `app/api.py` | HTTP endpoints and built-page hosting |
| `app/dockwatch/` | Data validation, QC functions, pattern detection and plotting |
| `data/` | Two observation CSVs, configuration, generator and audit artifacts |
| `tests/` | Known-answer, boundary, validation, API and packaging tests |
| `scripts/` | Deployment bundle preparation and verification |
| `uv.lock`, `app/frontend/package-lock.json` | Reproducible dependency versions |
| `SPEC.md`, `CONTRACT.yaml` | Current product specification and task ledger |
| `demo/README.md` | Extended demonstration with numeric checkpoints |

The project is MIT-licensed. Team members are **Chi Zhang, Raymond Xu,
Ruoxi Wang, Siyu Yao and Huiyu Zhu**.

## Using each dashboard function

Start with **Normal operations**, **S01**, **September 28, 2026, 09:00 EDT**.
The interface initially pauses at this snapshot. All displayed local times use
**America/New_York**.

### Controls, inputs and effects

| Control | Input / default | Function and result |
|---|---|---|
| Demo scenario | Normal operations; or Disruption/uploaded source | Changes the observations; resets the clock, pauses playback and closes History |
| Station | S01–S20; default S01 | Selects the station details and pauses playback; does not determine a separately opened History station |
| Play / Pause | Paused initially | Advances one scheduled hourly snapshot every two seconds |
| Step / simulation slider | Ordered hourly slots, indices 0–599 | Chooses the viewing time and pauses playback; after 21:00 comes 07:00 on the next scheduled date |
| Street basemap | On initially | Toggles street tiles; markers retain their coordinates when tiles are off |
| Upload inventory CSV | A CSV containing timestamp, station_id, bikes | Validates readings against the fixed stations and calendar; accepted uploads become the selected temporary source |
| Overview / View by Station | Overview initially | Switches presentation while keeping the same clock and data source |
| History | Opened for a station; 07:00, all dates, Diagnosis off | Pauses playback and opens same-hour analysis for that station |
| Operating hour | Integer hour 07:00–21:00 | Selects one reading per service date and recalculates estimates |
| Analysis date range | Inclusive service dates | Selects dates for estimating CL and limits; unavailable while Diagnosis is on |
| Diagnosis | Off on every opening | Selects and locks all dates; evaluates eight rules and shows matched-rule tabs |
| Download current snapshot | Current scenario and clock | Downloads an enriched station table; this is not the original input CSV |

### Overview: decide what to inspect next

1. Check **Observation coverage**. Interpret availability and empty/full values
   using the number of observed stations, not an assumed complete network.
2. Review the **Action queue**: empty/full first, low/high next, then missing/stale
   records needing reinspection. Within a priority, station ID determines order.
3. Hover or keyboard-focus a row, red alert or map marker to highlight the matching
   station across views. A marker popup shows count, free docks, reading time/age
   and suggested action. Double-click a marker, or use Enter/Space on it, to select it.
4. Check the selected station's **Current bikes**, **Free docks** and **Hourly net
   change**. Confirm the inventory and transport capacity before arranging a move.
5. Use **Download current snapshot** if staff need a review table.

The queue displays **Station**, **Bikes** and **State**; quantities appear in map
popups and exports. Its order is a transparent review priority, not a route plan.

Red alerts represent **current empty/full stations only**. Clicking one opens its
enlarged rolling chart without stopping playback. The × dismisses that station's
continuous condition; it does not change readings, remove its queue row or record
a completed action. A valid recovered reading clears dismissal; a later critical
condition can alert again. Source changes, rewinds and nonconsecutive seeks reset
dismissals. Missing data do not prove recovery. Therefore, no active red alerts
does not necessarily mean no inventory warnings.

### View by Station: inspect recent movement

Twenty charts display each station's latest **eight scheduled slots**, using
the same 0–30 bike scale. Fewer elapsed slots produce fewer points; missing
readings stay gaps and lines do not bridge overnight gaps. Hover points/hours
to inspect dates.

Click a chart body or press Enter/Space to enlarge it. **Back to all stations**
or Escape returns to the grid. These actions preserve playback. Fixed lines at
**Lower 6**, **CL 15** and **Upper 24** are inventory references; the CL label here
does not mean a historically estimated center line.

### History: investigate a pattern

Choose **History** on a station chart. The dialog pauses playback and always
starts at 07:00, all service dates and Diagnosis off. Select another hour or date
range to recalculate the chart and its observed/planned counts, CL, LCL and UCL.
Hover, keyboard-focus or tap a point for its date and count; tap again to unpin.

**History can show dates later than the sidebar clock.** It uses the complete
loaded timeline and is a retrospective review, not an alarm simulation using
only information available at playback time.

Turn **Diagnosis** on to restore and lock all dates. Each detected rule gets a
tab: selected-rule contributing points are red, other matches have amber outlines.
The explanation distinguishes unique highlighted points from overlapping windows.
Unevaluable rules have reasons and are not passes. Turn Diagnosis off to unlock
the date range. Closing with **Close** or Escape restores the underlying view and
focus; playback stays paused. Reopening resets History's settings.

### Common problems and next steps

| What happens | What to do |
|---|---|
| CSV cannot load | Read its validation message; fix unknown IDs, duplicate keys, blank counts, timezone or off-calendar timestamps, then upload again |
| Uploaded source disappears | Upload again; sources expire on restart or eviction and page reload starts the default demo |
| Streets do not load | Turn Street basemap off; use markers and station names |
| Current count is missing/stale | Obtain a new valid reading; do not treat the station as empty or assign a move quantity |
| No estimated limits | Read the reason; one reading, no adjacent pair or zero moving-range variation cannot estimate limits |
| Normal has a History match | Check the rule and period; normal inventory does not imply zero matches under the current eight-rule analysis |
| Documentation and an old generator report differ | Use this current implementation description; the preserved generator reports use different rules and estimation periods |

## Inventory measures and action rules

A current count must be recorded **exactly at simulation time**. Earlier readings
are shown separately as latest-known context; future readings never enter current
snapshots. Age is measured against simulation time, not the computer's date.
Missing counts are not replaced by zero or carried forward into current rates.

Let `N` be observed stations and `P` planned stations (20 in this demo).

| Measure | Calculation / unit | Interpretation |
|---|---|---|
| Station occupancy | bikes / capacity; fraction | Share of docks occupied |
| Free docks | capacity − bikes; dock positions | Return spaces, assuming all positions work |
| Empty / full proportion | Count at 0 / at capacity, each divided by N | Current observed stations lacking one service |
| Two-way availability | Count with 0 < bikes < capacity, divided by N | Stations offering both a bike and return space |
| Observation coverage | N / P | Completeness at the selected instant |
| Mean occupancy | Mean of observed occupancy fractions | Average station occupancy |
| Hourly net change | Current minus previous count at the same station, exactly one hour apart on the same local date | Net change, not separate arrivals/departures |

The API returns fractions; the interface displays percentages. With `N=0`, rates
and mean occupancy are unavailable; coverage is zero. Availability is not a
customer success probability or the percentage of time service was available.

### Manual action policy

| Current bikes, capacity 30 | State / priority | Recommendation |
|---|---|---|
| 0 | Empty / 1 | Add 15 |
| 30 | Full / 1 | Remove 15 |
| 1–5 | Low stock / 2 | Add 15 − bikes |
| 25–29 | High stock / 2 | Remove bikes − 15 |
| 6–24 inclusive | Available / 4 | No threshold action |
| No current count | Missing or stale / 3 | Reinspect; no move quantity |

Stale means the latest reading is at least **60 minutes** old. Without any prior
reading, or with a prior reading younger than 60 minutes but no exact-current
reading, the state is missing. On this hourly calendar, an earlier scheduled
reading is already stale. The queue contains priorities 1–3 only.

The code generalizes the thresholds to strictly below 20% or above 80% occupancy,
with a target of `floor(capacity/2)`. Exactly **6 and 24** are not warnings.
The signed `suggested_change` is positive to add, negative to remove, zero for
normal counts and null for missing/stale counts. Suggestions do not identify a
source/destination pair, allocate a vehicle or execute a move. Historical
statistical matches neither create queue rows nor assign quantities.

## History calculations and diagnosis

### Individuals chart

The analysis unit is **one station's count at one chosen hour on one service
date**. Neighborhood labels do not define statistical subgroups. Matching hours
avoids mixing morning and evening behavior in one series.

Build the planned-date grid first; retain absent readings as gaps. For valid
readings `x` and adjacent scheduled dates with both counts present:

```text
CL        = mean(valid x)
MR_i      = abs(x_i - x_(i-1))
MR_mean   = mean(valid adjacent moving ranges)
sigma_hat = MR_mean / 1.128
LCL       = CL - 3 × sigma_hat
UCL       = CL + 3 × sigma_hat
```

The constant 1.128 is the expected range factor for two observations, following
[NIST Individuals charts](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc322.htm).
Missing scheduled readings break pairs. Non-service weekends do not break
consecutive scheduled dates. Limits are not clipped to 0–30. No observations,
no eligible pair or zero MR variation yields unavailable limits and an
explanation; a mean remains available when there are observed readings.
The app displays an Individuals chart, not a separate Moving Range chart.

**The selected series supplies both the estimates and the evaluated observations.**
Changing dates/hour refits them. Diagnosis uses the full station/hour series.
There is no approved stable baseline or frozen prospective monitoring period in
this implementation.

### Eight diagnosis rules

Let `d = x − CL` and `s = sigma_hat`. Rule numbers follow the project's
course-image convention implemented in `app/dockwatch/patterns.py`.

| Rule | Window | Exact condition |
|---|---:|---|
| T1 | 1 | abs(d) > 3s |
| T2 | 3 | At least two d > 2s, or at least two d < −2s |
| T3 | 5 | At least four d > s, or at least four d < −s |
| T4 | 8 | All d > 0, or all d < 0 |
| T5 | 6 | All five consecutive differences strictly positive or all strictly negative |
| T6 | 15 | Every abs(d) ≤ s, including boundaries |
| T7 | 8 | Every abs(d) > s, with at least one point on each side of CL |
| T8 | 14 | All thirteen differences nonzero, with alternating signs |

Missing readings break windows. Equality with CL breaks T4; ties break T5/T8.
T1/T2/T3/T6/T7 need finite CL and positive finite sigma; T4 needs a finite CL;
T5/T8 can evaluate order without estimated limits if a complete window exists.

Statuses distinguish **detected**, **not detected after evaluation**, and
**unavailable**. Each event records its window, final confirmation index and
contributing points. T2/T3 highlight qualifying points only. Overlapping windows
remain separate events, while highlighted points are deduplicated per rule.
Consequently, an event count is not a count of independent incidents.

Bounded integer inventory, serial dependence, shared bike movements, deliberate
fixture selection and multiple rules limit interpretation. A match suggests
investigation; it does not identify a physical cause, establish capability or
stability, or quantify a real-world false-alarm probability.

## Data README and complete codebook

### Purpose and the two scenarios

The bundled data are **designed synthetic teaching and software-test fixtures**, not real Ithaca telemetry or measured travel demand. Each CSV contains 12,000 observations: 20 stations × 40 scheduled weekdays × 15 hourly observations, 07:00–21:00 in `America/New_York`. The default calendar runs August 24–October 16, 2026. Weekdays, including holidays, are assumed comparable for this fictional example; this is not Cornell's actual operating calendar.

| Scenario | Construction | What it demonstrates |
|---|---|---|
| `normal.csv` | Designed daily inventory pattern with seeded variation; all counts are 6–24 inclusive | Changing inventory without operational warnings; current History may still detect statistical patterns |
| `disruption.csv` | Identical first 25 dates, followed by disclosed changes to rider schedules | Empty/full, low/high, exact 6/24 boundaries and cross-date patterns |

The shared portion is August 24–September 25 (7,500 rows); the contrast is September 28–October 16 (4,500 rows). These construction periods do not determine the current History chart's limits. There are exactly two scenario CSVs. The retired `edge_cases.csv` is not required: disruption includes boundary examples, while software tests exercise invalid, missing and degenerate inputs.

### File inventory

| File in `data/` | Purpose |
|---|---|
| `normal.csv`, `disruption.csv` | Dashboard observation inputs; same three-column schema |
| `stations.json` | Shared station identities, coordinates and usable capacities |
| `settings.json` | Independent collection plan used to determine expected readings and coverage |
| `station_anchors.json` | Offline landmark provenance and generator input |
| `normal_events.jsonl`, `disruption_events.jsonl` | Individual-bike movement ledgers for conservation audits; not extra datasets or dashboard inputs |
| `generation_metadata.json` | Construction assumptions, seed, hashes and inventory audits |
| `validation.json` | Preserved generation-time physical and historical detector results |
| `generate_data.py` | Standard-library simulator that produces the matched pair and reports |
| `test_generate_data.py` | Reproducibility, independent event replay and historical detector checks |
| `_qc_snapshot.py` | Preserved historical three-rule detector used by this generator |
| `README.md` | Current integration explanation and data codebook |
| `README.v5.md` | Historical publication README and generator's output template |
| `demo_guide.md` | Historical three-rule demonstration coordinates |
| `RUN_IN_CURSOR.md` | Historical data-branch running instructions; its old UI and launch references do not describe current main |

The following codebook is embedded here so readers can understand the inputs without following these links. Original files remain available in [the data folder](../data/).

### Observation CSV schema

```csv
timestamp,station_id,bikes
2026-08-24T07:00:00-04:00,S01,15
```

| Column | Type and units | Definition and validation |
|---|---|---|
| `timestamp` | Timezone-aware datetime; ISO 8601 in bundled files | Instant of the scheduled reading. Must resolve to an exact planned local date/hour. `-04:00` means UTC minus four hours, not a recording duration. Valid timestamps with another offset are converted to the configured timezone. |
| `station_id` | String | Foreign key to `stations.json`; bundled IDs are `S01`–`S20`. Unknown or blank IDs are rejected. |
| `bikes` | Finite integer, bikes | Usable bikes docked at that instant, from 0 to the station's capacity (30), inclusive. Blank, fractional, negative or over-capacity counts are rejected. Zero means a valid empty reading. |

The primary key is `(timestamp, station_id)`; duplicates are rejected. The loader sorts rows by time and station and ignores extra columns. Missing observations must be absent rows, never invented zeroes. Bundled files contain every planned key; incomplete uploads retain gaps and reduce coverage. No primary field is nullable in an observed row. The loader adds `service_date` (local `YYYY-MM-DD`) and `hour` (local integer hour); these are derived fields, not required upload columns.

Derived free docks equal `capacity − bikes`; occupancy equals `bikes / capacity`. Changes between inventory readings are net changes, not separate departures, arrivals, customer attempts, demand or exact outage duration.

### Stations and geographic provenance

`stations.json` is an array with one object per station. `station_anchors.json` repeats the station fields and adds the two provenance fields below. No listed field is null in the supplied files.

| Field | Type / units | Meaning |
|---|---|---|
| `station_id` | Unique nonempty string | Join key shared by observations and collection plan |
| `name` | Nonempty string | Display name, explicitly suffixed “simulated station” |
| `area` | Nonempty string | Descriptive neighborhood/campus area; not an SPC subgroup |
| `type` | Nonempty string | Functional description: residential, academic, mixed, transport or recreation in these fixtures |
| `latitude` | Number, WGS84 decimal degrees | North–south coordinate; valid range −90 to 90 |
| `longitude` | Number, WGS84 decimal degrees | East–west coordinate; valid range −180 to 180 |
| `capacity` | Positive integer, docks | Usable dock positions; 30 for every bundled station |
| `source_url` | URL string; anchors only | Recorded Cornell venue or transit-location provenance |
| `coordinate_note` | String; anchors only | How the landmark coordinate was obtained and its limitations |

Twelve anchors lie in Cornell core and eight in surrounding Ithaca. They identify real landmarks, **not existing bikeshare installations, surveyed station footprints or approved locations**. IDs and coordinates are shared across scenarios. The abbreviated names below omit the common simulated-station suffix:

| ID | Landmark | ID | Landmark |
|---|---|---|---|
| S01 | Robert Purcell Community Center | S11 | Willard Straight Hall |
| S02 | Appel Commons | S12 | Stocking Hall / Dairy Bar |
| S03 | Toni Morrison Hall | S13 | Schwartz Center / Collegetown North |
| S04 | Baker Tower | S14 | College Avenue at Mitchell Street |
| S05 | William Keeton House | S15 | Ithaca Commons / Seneca Street |
| S06 | Olin Library / Arts Quad | S16 | Ithaca Commons / Green Street |
| S07 | Upson Hall / Engineering Quad | S17 | Maplewood Apartments |
| S08 | Mann Library | S18 | Pleasant Grove at Hanshaw / Community Corners |
| S09 | Rockefeller Hall | S19 | Hudson Street at Columbia Street |
| S10 | Kennedy Hall / Ag Quad | S20 | Stewart Park Entrance |

### Collection-plan codebook

| `settings.json` field | Type | Meaning / supplied value |
|---|---|---|
| `schema_version` | Integer | Format version, 1 |
| `timezone` | IANA timezone string | `America/New_York`; must name an available timezone |
| `service_dates` | Ordered unique date-string array | Forty `YYYY-MM-DD` dates; supplies the expected calendar independently of CSV contents |
| `hours` | Ordered unique integer array | Local hours 7 through 21 inclusive; loader permits integers 0–23 |
| `station_ids` | Unique string array | S01–S20; must match station configuration |
| `baseline_dates` | Date-string array | First 25 construction/reference dates for the historical generator |
| `monitoring_dates` | Date-string array | Final 15 construction dates for the historical generator |
| `collection_mode` | String | `automatic_complete_hourly_snapshots` |

The application requires timezone, service dates, hours and station IDs. The other fields provide fixture metadata; `baseline_dates` and `monitoring_dates` do not freeze current History limits.

### Fleet accounting and event-ledger codebook

The closed fleet has 300 bikes across docked and in-transit states, with 600 dock positions. Initialization places 15 bikes at each station **once**, at the first 07:00. Each departure removes an identified bike; positive riding time keeps it in transit; a successful arrival adds it to the destination. A full destination requires additional riding before another arrival attempt. State persists overnight and across weekends. There is no daily reset, operator redistribution or execution of dashboard recommendations. Pending final rides remain in transit.

The model simplifies travel into ten two-station corridors with designed morning, daytime, evening and sparse overnight/weekend movement. Some trips deliberately span snapshot times. This is a reproducible demonstration design, not calibrated road travel or citywide demand. For a complete simultaneous snapshot under these assumptions only, `300 − sum(bikes)` gives in-transit inventory. Partial uploads cannot support that inference. The app's optional fleet check only rejects docked totals above 300; event replay is what establishes conservation.

Each JSONL line is one event, in chronological order:

| Field | Type | Present on / interpretation |
|---|---|---|
| `event` | String enum | `departure`, `arrival`, `reroute` |
| `timestamp` | Offset-aware datetime string | All; physical event time |
| `bike_id` | String | All; B001–B300 identifies the same bicycle across trips |
| `trip_id` | String | All; T-prefixed trip identifier links departure, possible reroutes and arrival within a scenario |
| `station_id` | Station ID string | All; departure origin, arrival destination or full station being rerouted from |
| `destination_id` | Station ID string | Departure/reroute only; next destination |
| `arrival_due` | Offset-aware datetime string | Departure/reroute only; scheduled future arrival attempt |
| `flow` | String | Departure only; synthetic morning/daytime/evening/overnight/weekend schedule category, optionally suffixed `_still_riding` |

Fields absent from a variant are omitted, not missing measurements. B001–B015 initially belong to S01, continuing in blocks of 15 through B286–B300 at S20. The published ledgers contain departure and arrival records; reroute is a supported generator variant, not an event claimed to occur in these files. Unfulfilled synthetic departure plans are not recorded customer failures.

### Audit JSON structure and interpretation

`generation_metadata.json` contains `synthetic`, `provenance`, `not_detector_input`, `calendar_assumption` and `limitations`; `configuration` records generator version, seed, start date, timezone, hours and station hash. `model` records fleet/capacity, corridors, initial allocation, duration/profile construction, off-hours behavior and sensor assumptions. `fixture_selection_attempts_by_corridor` discloses deliberate candidate selection. `station_sources` carries ID, URL and coordinate note. `expected_csvs` records rows, reference/monitoring row counts, snapshots, coverage and SHA256; `expected_event_logs` records event counts and SHA256. `snapshot_audit[scenario]` lists timestamp, docked and in-transit counts. `transfer_audit[scenario][phase][flow]` counts planned transfers, successful departures, arrivals and reroutes. `final_in_transit` records pending bikes at the last snapshot.

`validation.json` records generator/detector identity, scope, status, shared-history checks and manual-review status. Per-scenario `event_replay` summarizes conservation, positive durations, bikes/events/snapshots checked and pending rides. `scenarios` contains coverage, inventory range, operational-warning counts, historical rule counts/examples and 300 station/hour `strata`. Each stratum records reference sample size, adjacent pairs, center/limits, correlation, eligibility and warnings. Statistical examples identify station, date/hour, value, rule, direction, contributing dates and exploratory status. These are saved generation results, not fresh execution or current dashboard outputs.

### Historical detector versus current History

Generation used the preserved three-rule detector: limit crossing, eight on one side and six-point trend, with first-25-date limits frozen for the final 15. Current History fits the selected date range; enabling Diagnosis selects all dates and evaluates eight rules. History is retrospective and independent of playback. Therefore the generator's “zero normal candidates” claim does **not** promise zero current History matches. Neither construction labels nor event logs are detector inputs. Normal's deliberately accepted profile is not proof of independence, capability, a normal distribution or a calibrated false-alarm rate.

The generator prefers legacy `app/qc.py` if present; this checkout instead uses the hash-checked `data/_qc_snapshot.py`. Historical statements in `README.v5.md`, `RUN_IN_CURSOR.md`, `demo_guide.md` and metadata about an Analysis tab, manual baseline review or causal frozen monitoring describe that earlier workflow. Use this documentation and [the current demonstration guide](../demo/README.md) for the current app.

### Reproduce safely and collect real data

From the repository root, using Python 3.9+ with an IANA timezone database:

```sh
python3 data/generate_data.py --output-dir /tmp/dockwatch-data-preview
python3 -m unittest discover -s data -p 'test_generate_data.py' -v
```

Keep the entire `data/` folder. Options are `--seed` (5300), `--start-date` (`2026-08-24`, must be a weekday), `--output-dir` (defaults to the script's folder) and `--scenario all` (only choice). Both CSVs are produced together. Existing named outputs are backed up before replacement. Default regeneration also overwrites `data/README.md` with historical `README.v5.md`; review regenerated files before integrating them. Restart the backend after replacing active data because it caches observations/configuration. Changing seed/date requires rechecking demo coordinates and current-app results.

Real collection would use synchronized station controllers to export usable-bike counts and operators to maintain IDs, capacities and the collection plan. Faults, closures, missingness, holiday effects and capacity changes would need explicit handling. Trip logs or additional sensors would be needed to distinguish departures/arrivals and validate in-transit bikes. Sampling every hour cannot measure every short empty/full episode. Real monitoring requires a separately justified comparable-history design and validation beyond these fixtures.

## API and Python function reference

The React interface calls the same Python calculations available to other clients. Start the application as described above, then open `/api/docs` for interactive requests or `/api/openapi.json` for its machine-readable contract. The implementation is [`app/api.py`](../app/api.py); missing JSON measurements are `null`. Inventory counts, Individuals limits and inventory changes use **bikes**, ages use **minutes**, and coverage, availability and occupancy are **fractions from 0 to 1**.

### Request parameters and defaults

| Parameter | Default | Meaning and valid inputs |
|---|---|---|
| `source` | `normal` | `normal`, `disruption`, or an accepted upload's source ID. |
| `cursor` | `377` | Zero-based index in `/api/config`'s 600 timestamps: 0–599. Default: September 28, 2026, 09:00 EDT. |
| `station_id` | `S01` | Configured ID, S01–S20. |
| `hour` | Omitted | One configured local operating hour, integer 7–21; selects same-hour daily history. |
| `start_date` | First service date | Inclusive `YYYY-MM-DD`, used with `hour`. |
| `end_date` | Cursor's local date | Inclusive date, no later than cursor's date; used with `hour`. |
| `start`, `end` | `0`, cursor | Legacy hourly-history indices when `hour` is omitted; require `0 <= start <= end <= cursor`. |
| `diagnosis` | `false` | Eight-rule diagnosis on `/api/analysis`; restrictions below. |

Date bounds without `hour` are invalid. With `hour`, date bounds replace `start`/`end`. Only configured service dates are included; on the final selected date, a selected hour later than the cursor is excluded. `/api/config` supplies the actual calendar rather than asking clients to reconstruct it.

### Routes and returned information

| Method and route | Inputs | Returns |
|---|---|---|
| `GET /api/health`, `GET /health` | None | `{"status":"ok"}`: service liveness. |
| `GET /api/config` | `source` | Scenarios, stations, ordered timestamps, timezone, hours, service dates, default cursor, source ID/label/row count. |
| `GET /api/snapshot` | `source`, `cursor` | Selected timestamp, network metrics, all station rows and ordered operational queue. |
| `GET /api/realtime` | `source`, `cursor` | All stations' last eight elapsed scheduled slots, timestamps, capacity and fixed references: lower 6, center 15, upper 24. |
| `GET /api/analysis` | All parameters above | Station/capacity, resolved selection, history and statistical summary. |
| `GET /api/charts/{chart}.svg` | `chart`, selection parameters except `diagnosis` | Static SVG; `chart` is `history`, `inventory` or `heatmap`. |
| `GET /api/snapshot.csv` | `source`, `cursor` | Downloadable current station table described below. |
| `POST /api/uploads` | Multipart field `file` | HTTP 201 configuration containing a temporary source ID. |

The eight-slot window is fixed, can cross service days, and retains missing slots. SVG history uses the selected interval or same-hour dates; inventory and heatmap render elapsed hours on the cursor's date. All SVG variants validate `station_id`; inventory/heatmap also validate legacy interval bounds but do not use that interval for plotting. SVGs omit diagnosis highlighting. The interactive interface uses JSON instead.

Snapshot rows contain station metadata and current/last-reading information. The queue includes priorities 1–3, sorted by priority then station ID; it contains no statistical findings. Metrics are `n`, `planned`, `coverage`, `empty_count`, `full_count`, `available_count`, `empty_rate`, `full_rate`, `availability` and `mean_occupancy`. Coverage uses planned stations; availability and empty/full rates use valid current observations. Missing measurements are never counted as available.

Analysis history rows are `timestamp`, `station_id`, `bikes`. Summary fields are `cl`, `n`, `planned`, `pairs`, `limits`, `reason` and, in same-hour mode, `hour`. `limits` is null or `{cl,lcl,ucl,mr_mean,sigma,n,pairs}`. Insufficient or zero moving-range variation returns null limits with an explanation.

Diagnosis requires `hour`, **exactly the complete configured date range**, and a cursor through the final date's selected hour; otherwise the API returns 422. The dashboard requests this full retrospective series independently of playback. An ordinary API history request can use an earlier cutoff.

`summary.special_causes` contains `status` (`disabled`/`enabled`), `ruleset`, `rule_status`, `events` and `issues`. Per-rule status is `detected`, `not_detected` or `unavailable`, with a reason and evaluated-window count. Events identify rule, start/end/trigger indices, contributing indices and direction. Issues summarize each detected rule, deduplicated highlighted indices and event count. All indices are zero-based history positions, including missing slots; overlapping windows remain separate events. Enabled diagnosis does not guarantee every rule can be evaluated.

```bash
curl 'http://127.0.0.1:8000/api/analysis?source=disruption&cursor=599&station_id=S01&hour=9&start_date=2026-08-24&end_date=2026-10-16&diagnosis=true'
```

### Upload, export and error contract

Upload the raw three-column observation schema: `timestamp,station_id,bikes`. The server validates timezone-aware scheduled instants, known stations, integer counts within capacity and unique station/timestamp keys. Extra columns are ignored. Missing observations must be omitted rows; blank counts are invalid. A header-only file is accepted as all observations missing. Uploads cannot redefine stations/calendar and are **not** checked against the synthetic 300-bike fleet bound.

```bash
curl -F 'file=@data/normal.csv' http://127.0.0.1:8000/api/uploads
```

Use the returned `source.id` in subsequent requests. Maximum size is **5 MiB**. Up to **eight uploads** live in one server process; the ninth evicts the oldest inserted upload. Restart loses all uploads; there is no time-based expiry or per-user private storage. Use one worker for this demo.

The snapshot export contains these columns, with missing values blank:

| Columns | Meaning |
|---|---|
| `station_id,name,area,type,latitude,longitude,capacity` | Station metadata from the codebook. |
| `bikes,as_of_time,occupancy,free_docks` | Exact-current count, selected instant, count/capacity, capacity-count. |
| `latest_timestamp,latest_bikes,age_minutes` | Separately labeled latest observation at/before the selected instant and its age. |
| `status,priority,action` | Operational category, ordering priority and staff-facing instruction. |
| `target_bikes,suggested_change` | Half-capacity target and signed suggestion: positive add, negative remove; null when current count is missing. |

The JSON snapshot additionally has `display_name` and `net_change`, absent from the CSV. Export is a **derived snapshot**, not the raw time series: its time column is `as_of_time`, so it cannot be uploaded unchanged. Explicitly map valid current rows to the raw schema if needed; never substitute an older reading for a missing current count.

Successful reads return 200; uploads return 201. Errors return JSON `detail`: **404** unknown/evicted/restarted source; **413** oversized upload; **422** invalid selection, diagnosis range or CSV. Row validation reports up to the first 20 errors with CSV row numbers. Framework validation may return structured details.

### Python function reference

Use Python 3.12. `python -m pip install .` installs the core library; `python -m pip install '.[api]'` adds HTTP/plotting dependencies. Data files remain explicit inputs and are not bundled in the wheel. Core functions below are exported by `dockwatch`; `observations` means a validated DataFrame, `stations` its validated metadata DataFrame, and `settings` its validated calendar dictionary.

| Function and exact parameters | Result and purpose |
|---|---|
| `load_stations(source)` | JSON path/records → validated station DataFrame; checks identifiers, labels, coordinates and positive integer capacity. |
| `load_settings(source, stations)` | JSON path/dict → calendar dict; checks timezone, ordered unique dates/hours and matching station IDs. |
| `planned_timestamps(settings)` | Chronological timezone-aware scheduled `DatetimeIndex`. |
| `load_observations(source, stations, settings, check_fleet=False)` | CSV path/file-like object or DataFrame → validated/sorted DataFrame, adding `service_date` and `hour`; optional docked-total upper bound 300, not proof of conservation. |
| `load_bundle(data_dir, source=None, check_fleet=False)` | `(observations, stations, settings)`; `source=None` selects `data_dir/normal.csv`, otherwise uses the supplied CSV/DataFrame source. |
| `snapshot_at(observations, stations, as_of_time)` | Complete station table with exact-current inventory, older-reading context and operational actions; time must include timezone. |
| `snapshot_metrics(snapshot)` | Counts, coverage, availability and occupancy dictionary. |
| `hourly_changes(observations)` | Copy adding `net_change` for adjacent same-day one-hour readings only. |
| `individual_limits(values, timestamps=None)` | Limit/estimator dictionary; missing values break pairs. Optional timestamps restrict pairs to consecutive same-day hours. Invalid/unsupported estimates raise `ValueError`. |
| `station_history(observations, settings, station_id, start_time, end_time)` | `(history, summary)` across inclusive scheduled hours; caller must cap the ending instant for as-of behavior. |
| `station_hour_history(observations, settings, station_id, start_date, end_date, hour, as_of_time)` | `(history, summary)` across inclusive dates at one hour, excluding future slots and retaining missing readings. Consecutive scheduled dates form moving ranges across weekends. |

History wrappers return null limits plus reasons for insufficient/constant data; invalid selections raise `ValueError`. Additional module-level functions are:

| Import and function | Result and purpose |
|---|---|
| `dockwatch.qc.realtime_history(observations, settings, as_of_time)` | All stations × last eight elapsed scheduled slots; missing counts retained, no carry-forward. |
| `dockwatch.patterns.detect_special_causes(values, centerline, sigma)` | Diagnosis structure; matches T1–T8 without estimating limits or enforcing calendar scope. Missing values interrupt windows; non-finite nonmissing values are rejected. |
| `dockwatch.plots.inventory_plot(observations, station_id, as_of_time, capacity, planned_hours=range(7, 22))` | plotnine plot of the selected day's elapsed scheduled counts. |
| `dockwatch.plots.occupancy_heatmap(observations, stations, as_of_time, settings)` | plotnine station/hour occupancy heatmap through the selected instant. |
| `dockwatch.plots.history_plot(history, summary, capacity)` | plotnine Individuals chart using the supplied selection and summary; no new statistical fitting. |

```python
from dockwatch import load_bundle, snapshot_at, snapshot_metrics

observations, stations, settings = load_bundle("data", check_fleet=True)
snapshot = snapshot_at(observations, stations, "2026-09-28T09:00:00-04:00")
print(snapshot_metrics(snapshot))
```

## Demonstration and known-answer results

Use the default seed-5300 files included in the repository. The following
checkpoints are calculated from the current Python functions/API.

### Compare the two scenarios

At **September 28, 2026, 09:00 EDT** (cursor 377):

| Result | Normal operations | Disruption |
|---|---:|---:|
| Observed / planned stations | 20 / 20 | 20 / 20 |
| Two-way availability | 100% | 90% |
| Empty / full stations | 0 / 0 | 1 / 1 |
| Docked / in-transit bikes in the simulator | 291 / 9 | 296 / 4 |
| S01 count / suggested change | 9 / 0 | 0 / +15 |
| S06 count / suggested change | 20 / 0 | 30 / −15 |

In Disruption, S02=3 suggests +12 and S07=27 suggests −12. S03=6 and S08=24
illustrate the exact no-warning boundaries. S04=5 and S09=25 are low/high.
The queue order is S01, S06, S02, S04, S07, S09. Hover its rows to locate them.

Step to 10:00: S01=10 and S06=20 in Disruption; no station is empty/full,
although four stations still have low/high warnings. The clock, map, queue and
rolling charts update together. Normal remains free of inventory warnings.

### Reproduce History results

Open S01 History in Normal, keep Diagnosis off, select **09:00** and
**September 22–28**. Values are **11,12,8,11,9** on five scheduled dates:
CL=10.2, MR mean=2.5, sigma=2.216312, LCL=3.551064, UCL=16.848936.

Then demonstrate:

| Selection | Result and meaning |
|---|---|
| Normal S01, 07:00, Diagnosis on | CL 17.55; limits 11.412520–23.687480; T3 only, four highlighted points in one window. No operational warning is implied. |
| Normal S01, 09:00, Aug 24–27, Diagnosis off | Four counts of 10; CL 10; limits unavailable because MR is zero. |
| Normal S01, 07:00, Aug 24 only | One count of 15; CL 15; insufficient adjacent data for limits. |
| Disruption S01, 09:00, Diagnosis on | CL 9.85; limits 3.848909–15.851091; T1/T2/T4. T1 and T2 each highlight two points in two windows; T4 highlights ten in three overlapping windows. |
| Disruption S14, 12:00, Diagnosis on | T4 highlights Sep 28–Oct 7: 16,17,16,17,16,17,16,17. These counts stay inside inventory thresholds. T1/T2/T3/T7 also occur. |
| Disruption S17, 14:00, Diagnosis on | T5 highlights Sep 28–Oct 5: 10,11,12,13,14,15; T3 also occurs. A trend alone does not prescribe a move. |

A short presentation sequence is: **user decision → normal inventory → disruption
and linked map → exact thresholds → same-hour calculation → Diagnosis →
limitations**. Explain both what staff can do now and what a historical pattern
cannot establish.

### Independent known answers

- Capacity-30 counts **[0,0,9,15,30]** give empty 40%, full 20%, two-way availability
  40%, mean occupancy 36%, and coverage 100% if all five stations were planned.
- Values **[10,12,11,13,14]** give MR **[2,1,2,1]**, CL **12**, MR mean **1.5**,
  sigma **1.329787234**, LCL **8.010638298**, UCL **15.989361702**.

These arithmetic cases and degenerate/boundary tests are in the repository;
they are not invented charts or placeholders.

## Reproduction, checks and handoff

### Run the checks

```bash
uv sync --frozen --extra api
npm ci --prefix app/frontend
uv run --frozen --extra api pytest tests data/test_generate_data.py -q
npm test --prefix app/frontend
npm run build --prefix app/frontend
uv build
```

Use `--prefix app/frontend` for npm commands or run them inside that directory;
a frontend fixture resolves data relative to its working directory. Tests cover
data validation, constants/gaps, date/hour isolation, exact threshold equality,
eight-rule boundaries, API behavior, frontend state and independent bike-event replay.

**Evidence and scope:** on October 17 the preceding main revision `47e05fe`
passed **240 Python/data tests and 89 frontend tests**, production frontend build
and Python source/wheel builds. Comparing it with this revision `253ecc7` shows
only SPEC and task-ledger changes; application code, data, dependency locks and
tests are identical. This documentation update does not describe those earlier
runs as newly executed full suites.

For this documentation update, current-source checks reconfirmed both CSVs'
12,000-row schema, unique observation keys, normal's 6–24 bounds, identical first
25 dates, and all four published CSV/event-file hashes. Snapshot metrics and
suggested quantities at the demo time, the known-answer estimator, and the
S01/S14/S17 diagnosis examples above were recalculated. All 32 relative links
and anchors across this document and the three README entry points resolve;
the task ledger parses and the whitespace check passes. Application code,
observations, configuration and audit data remain unchanged. No new browser
walkthrough, remote deployment or submission was performed for this update.

### Package and publish

`./app/manifestme` builds React, exports locked runtime requirements, creates
`build/connect`, and writes/verifies a FastAPI manifest. It changes local generated
deployment artifacts. The target must provide Python 3.12.

When publishing is intended and publisher credentials are configured in
`CONNECT_SERVER` and `CONNECT_API_KEY`, `./app/deployme` publishes the prepared
bundle. Never store credentials in documentation or tracked files. A local
build or successful test is not proof of a public deployment.

Before submission, verify the deployed page and `/api/docs` without the publisher's
login, reproduce the demo on that build, and supply the public app and repository
links. A teammate should follow these instructions from a fresh checkout.
On October 17, 2026, anonymous HTTP requests without credentials or cookies
returned 200 for the hosted dashboard, API documentation, health and configuration.
The hosted Disruption snapshot at cursor 377 also returned the expected 20/20
coverage, 90% two-way availability, one empty station and one full station.
This establishes public page/API access and that numerical checkpoint; it is not
a new complete browser walkthrough or proof of a completed Devpost submission.

## Requirements and sources

The organizer asks for a React/Vite dashboard plus a statistical library and/or
REST API, two or three field-shaped test datasets, a dataset codebook/README, and
public reproducible code. Synthetic datasets are permitted. This document embeds
the explanations rather than requiring readers to assemble separate guides.

| Rubric item | Evidence contained here |
|---|---|
| Tool documentation, 10 points | Setup, each dashboard function, inputs, parameters, formulas, outputs, API/library behavior and troubleshooting |
| Working datasets, 5 points | Two scenario definitions, input contract and reproducible numeric examples |
| Codebook and dataset README, 5 points | File inventory, variables/units, missingness, provenance, generation and real collection |
| Public reproducibility, 5 points | Repository, locked dependencies, commands, checks and public app/API links; final submission remains separate |
| Clear demonstration, 10 design points | Normal/disruption walkthrough and known-answer interpretation |

This maps evidence to the rubric; it is not a claim that points have been awarded.

- [Official requirements](https://github.com/timothyfraser/sixsigmahackathon/blob/main/docs/prompts.md)
  and [rubric](https://github.com/timothyfraser/sixsigmahackathon/blob/main/docs/criteria.md),
  checked October 17, 2026.
- [Current product SPEC](../SPEC.md), [Python QC](../app/dockwatch/qc.py),
  [pattern detector](../app/dockwatch/patterns.py), [API](../app/api.py) and
  [React implementation](../app/frontend/src/App.jsx).
- [NIST Individuals control charts](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc322.htm)
  for the moving-range estimator. Exact eight-rule conditions are the project's
  documented course convention, not a claim that every external ruleset is identical.
- [Team repository](https://github.com/raymondBRXu/sixsigmahackathon-vanta),
  [data-specific README](../data/README.md), [extended demo](../demo/README.md)
  and [MIT license](../LICENSE).
