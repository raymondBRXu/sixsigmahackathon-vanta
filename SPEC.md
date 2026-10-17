# SPEC: DockWatch — Team Vanta

DockWatch helps an Ithaca-area bikeshare supervisor inspect station inventory,
prioritize manual inventory actions, and investigate historical patterns.
This specification describes the current React/FastAPI implementation on `main`;
it supersedes earlier project plans. Proposed enhancements are not implemented features.
The structure follows the [organizer's SPEC template](https://github.com/timothyfraser/sixsigmahackathon/blob/main/SPEC.md)
and [rubric](docs/criteria.md).

## 1. Team and prompt

- **Team name:** Team Vanta. Product: DockWatch.
- **Members:** Raymond Xu, Chi Zhang, Siyu Yao, Ruoxi Wang, Huiyu Zhu.
- **Track:** On-campus, 24-hour hackathon, October 16–17, 2026.
- **Prompt we chose:** Urban Systems — Bikeshare Fleets, as recorded by the team from [Devpost](https://six-sigma-hackathon.devpost.com/). A numeric prompt identifier is not recorded; do not invent one.
- **Our public repo:** https://github.com/raymondBRXu/sixsigmahackathon-vanta

## 2. User and use case (rubric: scope 5, user and use case 5)

- **User:** A bikeshare operations supervisor responsible for station inventory in the Ithaca, New York area.
- **Decision the tool helps them make, and when:** At an hourly inventory review, identify stations needing attention and inspect suggested replenishment/removal quantities. During a historical review, compare one station at the same operating hour across dates and investigate unusual patterns.
- **Why this matches the prompt:** It uses observable docked-bike counts to show station service availability and support manual inventory decisions, without assuming that unobserved customer attempts can be measured.

The demonstration has 20 fictional stations, 30 positions per station (600 total),
and 300 bikes docked or in transit. Locations are defined in `data/stations.json`
around Cornell, Collegetown, downtown Ithaca and surrounding neighborhoods,
including Stewart Park. They are simulated facilities, not a real operating network.
The UI's current readings are synthetic playback, not a live telemetry feed.

## 3. Inputs (rubric: minimal inputs 5)

| Input | Type and units | Where the user gets it |
|---|---|---|
| `timestamp` | Timezone-aware timestamp, on a scheduled whole hour | Automatic station snapshot clock |
| `station_id` | Station identifier matching configuration | Station inventory system |
| `bikes` | Integer docked-bike count, 0 through capacity | Station dock sensors or a counted inventory snapshot |
| `data/stations.json` | IDs, names, area/type labels, latitude/longitude in decimal degrees, integer capacity | One-time station configuration |
| `data/settings.json` | Service dates, operating hours and timezone | Collection schedule configured by the operator |

CSV observations contain only `timestamp,station_id,bikes`; coordinates and capacity
are not repeated in every observation. The bundled calendar has 40 weekdays,
August 24–October 16, 2026, with 15 readings per day from 07:00 through 21:00,
in `America/New_York`. A complete scenario has 12,000 rows.

Reject invalid counts, unknown stations, invalid/off-schedule timestamps and duplicate
station/time keys. Missing observations remain missing, never zero. All bikes and
docks are assumed usable and stations open; free docks therefore equal capacity
minus bikes. Faults and closures would need additional input fields.

CSV uploads use the configured stations/calendar, are limited to 5 MiB, and are
stored temporarily in process memory (at most eight uploaded sources). They do not
have the synthetic fleet's 300-bike constraint. Bundled data checks reject docked
totals above 300; independent event replay checks that docked plus in-transit bikes
remain 300. Snapshot CSVs alone cannot establish full fleet conservation.

## 4. The statistics, and why (rubric: valid QC analysis 25)

- **Method:** Descriptive station-inventory measures and an exploratory Individuals (I) chart of one station's bike count at one selected operating hour across service dates. Optional Diagnosis checks eight explicitly defined patterns in the full same-hour history.
- **Why it fits the use case:** Counts are directly observable, and matching operating hours avoids pooling different times of day into one chart. The results support investigation of inventory behavior rather than estimates of customer failure rates.
- **Assumptions and how the tool checks them:** Input validation checks the count bounds, station identities, timestamps and uniqueness. Scheduled grids expose missing observations and coverage. Statistical independence, normality and process stability are not automatically established: bounded inventory, serial dependence and synthetic fixture selection limit interpretation. Diagnosis uses the same full series for estimation and detection, including excursions; results are retrospective exploratory matches, not calibrated prospective SPC alarms. A validated stable reference period would be needed before making that stronger claim.

### Inventory measures and manual action policy

Let `N` be the number of currently observed stations and `P` the planned stations.

| Output | Calculation / interpretation |
|---|---|
| Occupancy | `bikes / capacity` at an observed station |
| Free docks | `capacity - bikes`, in positions |
| Empty proportion | Number of observed stations with `bikes = 0`, divided by `N` |
| Full proportion | Number of observed stations with `bikes = capacity`, divided by `N` |
| Two-way availability | Number with `0 < bikes < capacity`, divided by `N`; a proportion of stations, not customers |
| Observation coverage | `N / P`; show counts alongside percentages |
| Mean occupancy | Mean of observed station occupancy fractions |
| Hourly net change | Current count minus previous count, only for consecutive one-hour readings within the same local service day |

With no observed stations, inventory rates are unavailable rather than zero.
Missing/stale counts do not become empty/full observations.

The manual action policy is separate from statistical diagnosis: strictly below
20% occupancy suggests adding bikes toward `floor(capacity/2)`; strictly above
80% suggests removing bikes toward that target. At capacity 30, the target is 15:
3 bikes suggests adding 12; 27 bikes suggests removing 12. Exactly 6 or 24 bikes
does not trigger low/high-stock action. Rank fresh empty/full stations first,
then low/high stock; missing/stale records require reinspection. Records at least
60 minutes old are stale, measured against the displayed simulation time.
Confirm counts before moving bikes. Independent station suggestions are not a
balanced transport plan, optimized route, or automatically dispatched work order.

### Individuals chart calculation

For the selected station/hour/date range, use one observation `x_i` per planned
service date. Compute:

- `CL = mean(valid x_i)`.
- `MR_i = abs(x_i - x_(i-1))`, only for adjacent scheduled service dates with both readings present.
- `MR_bar = mean(valid MR_i)`; `sigma_hat = MR_bar / 1.128`.
- `LCL = CL - 3 * sigma_hat`; `UCL = CL + 3 * sigma_hat`.

Missing scheduled readings break moving-range pairs. Non-service weekends do not
create missing readings. Do not clip limits to 0 or capacity. At least one valid
adjacent pair and positive moving-range variation are needed to estimate limits;
otherwise show observations and their mean, with the reason limits are unavailable.
Changing hour or date range recalculates estimates.

History is independent of the playback clock and can inspect the entire configured
collection period. It defaults to all service dates and 07:00. This is historical
review, even when playback is positioned at an earlier date. API callers can use
an explicit cutoff, but the dashboard History uses the final timeline index.

### Optional eight-rule Diagnosis

Diagnosis defaults off. Enabling it selects and locks the full service-date range.
Estimate CL and sigma once from that full station/hour series, then apply:

| Rule | Pattern |
|---|---|
| T1 | One point strictly beyond 3 sigma |
| T2 | At least two of three points strictly beyond 2 sigma on the same side |
| T3 | At least four of five points strictly beyond 1 sigma on the same side |
| T4 | Eight consecutive points strictly on the same side of CL |
| T5 | Six strictly increasing or strictly decreasing points |
| T6 | Fifteen consecutive points within inclusive ±1 sigma |
| T7 | Eight consecutive points outside ±1 sigma, with both sides represented |
| T8 | Fourteen points whose thirteen nonzero successive differences alternate direction |

Missing readings interrupt rule windows. Ties break trends and alternation;
equality with CL breaks T4. Insufficient data or unavailable limits are distinct
from an evaluated rule with no matches. Store matching windows, contributing
points and confirmation positions separately. One tab per matched rule highlights
its contributing points in red; other matched points are outlined in amber.
Overlapping windows do not duplicate highlighted points. Rules do not establish
a physical cause or generate homepage inventory alerts.

### Known-answer checks and implementation boundary

- Counts `[0,0,9,15,30]` with capacity 30 give empty 40%, full 20%, two-way availability 40%, and mean occupancy 36%.
- Same-hour readings `[10,12,11,13,14]` on five consecutive service dates give CL 12, moving ranges `[2,1,2,1]`, MR mean 1.5, sigma 1.329787234, LCL 8.010638298 and UCL 15.989361702.
- Tests also cover constant data, one observation, absent readings, no adjacent pairs, scheduled/non-service gaps, station/hour/date isolation, API cutoffs, threshold equality, and planted/tied/missing rule sequences.

Statistical calculations live in framework-free Python functions in
`app/dockwatch/qc.py` and `app/dockwatch/patterns.py`; React renders API results.
Every statistic must retain a known-answer test and relevant degenerate cases.
The moving-range estimator uses `d2 = 1.128`, documented by
[NIST Individuals charts](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc322.htm).
The rule numbering follows the course image; exact rule definitions above are
part of this specification. The team must be able to explain every displayed number.

## 5. Delivery (rubric: working tool 25)

- **Stack:** React/Vite dashboard and MapLibre map, served by FastAPI; independently installable `dockwatch` Python library. Interactive history is React SVG; Plotnine supports static chart endpoints.
- **Starting demo:** FastAPI delivery structure from `demos/fastapi/`, with React frontend starter material from `demos/reactfront/`. The current integrated implementation is in `app/` and deploys as one FastAPI content item.
- **Four-script contract:** `app/testme`, `app/manifestme`, `app/deployme`, and `app/README.md` provide local startup, manifest/bundle creation, publication and instructions.
- **Local run:** From the repository root, `./app/testme`. Prerequisites are Python 3.12, uv, Node.js 22+ and npm. Dependencies are locked in `uv.lock` and `app/frontend/package-lock.json`. Initial dependency installation needs internet; map tiles also need internet, with a tile-free view available.
- **Deployment requirement:** Publish to the course Posit Connect server with public access. `app/manifestme` prepares the self-contained bundle; `app/deployme` publishes with configured credentials. Public access and the demo must be verified after publication. Local tests/builds do not prove remote deployment; this SPEC does not claim a verified live deployment.

## 6. Outputs

| View/output | What the user sees and how to read it |
|---|---|
| Overview metrics | Current station availability, empty/full counts and proportions, and coverage. Always interpret inventory proportions alongside the observed denominator. |
| Ithaca map | All 20 stations, colored by current inventory status. Popups show bikes, free docks, observation age and suggested action. Double-click a marker or use the sidebar to select a station. |
| Red inventory alerts | Current empty/full stations. Selecting an alert opens its enlarged realtime chart. These are inventory conditions, not History rule matches. |
| Action queue | Station, Bikes and State; empty/full first. Suggested move quantities are in map popups and snapshot exports, not a Move column in this queue. |
| Selected-station details/export | Current bikes out of capacity, free docks, adjacent-hour net change, and a downloadable current snapshot CSV. |
| View by Station | Twenty charts, each showing the latest eight scheduled hourly slots through playback time on a 0–30 bike scale. Click a chart to enlarge it. |
| History | Same-hour counts across dates, observed/planned count, CL and estimated LCL/UCL, with interactive point details and optional Diagnosis tabs. |

The sidebar has one shared simulation clock: play/pause, previous/next hour and a
full-range slider. Playback advances one scheduled hour every two seconds.
Current views follow this clock; missing readings stay gaps, and realtime lines
do not connect across overnight gaps. No observations are invented to fill an
eight-slot chart. Fixed realtime reference lines at 6, 15 and 24 bikes are
inventory references; although the center is labeled CL in the UI, it is not the
historically estimated center line or control limits shown in History.

Opening History pauses playback and starts with Diagnosis off, 07:00 (or the first
configured hour), and all dates. Changing hour recomputes results; enabling Diagnosis
locks all dates, and disabling it unlocks date selection. Closing History returns
to the originating view with playback paused and focus restored. The selected
History station is independent of the sidebar selection.

Hover/focus links map points, alert cards and queue rows. Dismissing an inventory
alert hides that continuous condition without changing the readings or queue.
Recovery and a later new condition allow another alert; source changes and
nonconsecutive seeks reset dismissals. Missing/loading observations do not create
empty/full alerts from stale counts. Opening an inventory alert preserves playback.

All data are visibly labeled synthetic. The History modal displays the Individuals
chart; daily-inventory and heatmap charts remain API outputs, not additional
visible dashboard panels. No customer-attempt, exact outage-duration or causal
performance claims are made.

## 7. Test datasets and codebook (rubric: demo 10, datasets 5, codebook 5)

Provide two field-shaped synthetic observation CSVs with the same schema and
station/calendar configuration, each demonstrating a different inventory scenario.

| Dataset | Contents and expected behavior |
|---|---|
| `data/normal.csv` | 12,000 observations; published counts stay within 6–24 bikes, so there are no empty/full or low/high operational warnings. Optional History diagnosis can still find patterns. |
| `data/disruption.csv` | 12,000 observations; same first 25 service dates, followed by disclosed event scenarios with empty/full, low/high, exact-threshold and historical pattern examples. |

`data/README.md` is the codebook: file purposes, columns, units, assumptions,
generation method and how station snapshots could be collected in reality.
`data/stations.json` and `data/settings.json` supply shared metadata, not additional
observation scenarios. Constant, missing, invalid and insufficient-data cases are
covered by independent software fixtures; a third demonstration CSV is not required.

The seed-5300 ride simulator assigns bike IDs and positive trip durations, with
inventory continuing overnight/weekends and no daily reset or operator rebalancing.
JSONL event logs and generation reports support fleet-accounting audits; they are
not required user inputs. Geography and rider behavior are synthetic assumptions.

The preserved generator checks use a different, three-rule reference-period
method from current History. They do not establish expected results for the
current eight-rule diagnosis. In particular, normal S01 at 07:00 has a T3 match
under the current full-series calculation. Use `demo/README.md` for the current
UI walkthrough and checkpoints, not the legacy generator walkthrough.

## 8. Documentation and reproducibility (rubric: docs 10, public repo 5)

- `README.md` and `app/README.md` explain the user, inputs, parameters, outputs, local startup, library/API and deployment.
- `data/README.md` documents both scenarios and real-world collection requirements; `demo/README.md` demonstrates each scenario with expected numbers and interpretation.
- The public repository includes code, dependency locks, data, generator, tests and packaging scripts. A fresh clone must run after the documented prerequisites are installed.
- Verification commands are `uv run --frozen --extra api pytest tests data/test_generate_data.py -q`, `npm test --prefix app/frontend`, and `npm run build --prefix app/frontend`.
- The current implementation was locally checked on October 17, 2026: 240 Python/data tests and 89 frontend tests passed, and the production frontend build succeeded. These are implementation checks, not proof of the statistical assumptions or public deployment.
- Before submission, verify the deployed public application in a logged-out browser and reproduce the demo checkpoints. Submit the repository link and demo on Devpost. Deployment, submission and teammate comprehension are separate acceptance checks, not claimed complete by this document.

## 9. Out of scope

- Live telemetry, login/accounts, databases, persistent uploads, persistent review records and manual data-entry forms.
- Customer failure/success rates, separate pickup/return counts, exact downtime, inferred demand or causes from hourly inventory differences.
- Prospective SPC alarms, frozen-reference monitoring, automated baseline approval, calibrated false-alarm claims or process-capability claims.
- Demand forecasting, machine learning, route optimization, balanced dispatch planning, automatic bike transfers or causal claims about intervention benefits.
- Faulty/unusable bikes, broken docks and closed stations without an extended input schema.

The product supports inventory inspection, manual action suggestions and retrospective
pattern investigation. It does not claim to predict shortages or prevent them automatically.
