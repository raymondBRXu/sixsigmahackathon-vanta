# SPEC: Six Sigma Hackathon team project

What your tool IS. Your agent reads this before every task. Where the code and this file
disagree, the code is the bug: change this file first, then the code.

Most of this page is already decided by the event and the [rubric](docs/criteria.md).
**Only the `FILL IN` lines change, and you do not have to write them by hand:** describe your app and ask your agent to update them. They depend on the prompt your team picks at kickoff
(prompts are secret until then, see [`docs/prompts.md`](docs/prompts.md)) and on your team.
The examples after each `FILL IN` show the shape of an answer. They are not hints about the prompts.

## 1. Team and prompt
- **Team name:** Team Vanta. Product: DockWatch. Members: Raymond Xu, Chi Zhang, Siyu Yao, Ruoxi Wang, Huiyu Zhu.
- **Track:** On-campus (24 hours), October 16–17, 2026. Submit October 17 by 1 PM America/New_York; showcase 2–3 PM.
- **Prompt we chose:** Urban Systems — Bikeshare Fleets ([Devpost](https://six-sigma-hackathon.devpost.com/)); no numeric identifier was published. Track station availability and support informed rebalancing.
- **Our public repo:** https://github.com/raymondBRXu/sixsigmahackathon-vanta

## 2. User and use case (rubric: scope 5, user and use case 5)
- **User:** The supervisor of a fictional bikeshare network in the Ithaca, New York area, reviewing hourly station snapshots collected automatically.
- **Decision the tool helps them make, and when:** At each hourly review, identify empty/full or low/high-stock stations, inspect inventory patterns over a selected time interval, and prioritize bike replenishment or removal.
- **Why this matches the prompt:** Uses directly observable station inventory to reveal where and when service is unavailable and to provide explained rebalancing suggestions without assuming access to unobserved customer attempts.

## 3. Inputs (rubric: minimal inputs 5)
Only what this user can actually measure or already knows. Fewer is better; every input a user
cannot measure costs points.

| Input | Type and units | Where the user gets it |
|---|---|---|
| Hourly inventory CSV: `timestamp`, `station_id`, `bikes` | Timestamp with timezone; station identifier; integer bikes | Automatic station snapshot once per station per scheduled hour |
| Station configuration: `station_id`, `name`, `area`, `type`, `latitude`, `longitude`, `capacity` | Identifier, display name, area/type labels, WGS84 decimal-degree coordinates, positive integer positions | Configured once for 20 fictional Ithaca-area stations; field workers do not enter coordinates at every inspection |

Require 0 <= bikes <= capacity and one record per station/scheduled hourly slot. Preserve
missing readings as missing, never zero; reject invalid and duplicate rows. MVP capacity
is fixed at 30 positions for each of 20 stations; the fleet totals 300 bikes.
The synthetic instantaneous-transfer model conserves 300 bikes across all stations
at every complete snapshot (600 total positions, 50% network occupancy). Stations are open, and all bikes/docks usable, so free docks = capacity - bikes.
Faults and closures require an explicit future schema extension. Use actual observation
times; the demo and upload contract are exactly on scheduled hours. Compare matched scheduled hours and show missing coverage.

Geographic setting: Ithaca, New York and nearby areas shown in the team's reference
screenshot, rather than a strict municipal-boundary model. Place 20 fictional stations
around Downtown Ithaca, the Cornell area, the waterfront/Stewart Park area, Cayuga
Heights, East Ithaca and South Hill. Exact station locations will be set and visually
checked during data preparation; do not claim they are existing bikeshare facilities.
Use the same station IDs and coordinates in all scenarios. The map is labeled
“Ithaca — simulated bikeshare network”; coordinates locate stations but do not change
the statistical formulas or imply measured local demand.

## 4. The statistics, and why (rubric: valid QC analysis 25)
Say the method in words before any code exists. Load the `stats-first-steering` skill first.
- **Method:** Descriptive snapshot metrics plus an exploratory Individuals (I) chart for all hourly bike counts from one station inside a user-selected inclusive time interval. For valid snapshots, occupancy = bikes/capacity; empty proportion = count(bikes=0)/N; full proportion = count(bikes=capacity)/N; two-way availability = count(0<bikes<capacity)/N. Report N and observation coverage. Hourly net change = current bikes minus previous bikes only for adjacent, one-hour-separated observations within the same service day. For the selected interval, CL=mean(valid x), MR_i=abs(x_i-x_(i-1)) for consecutive valid one-hour readings within a service day, sigma_hat=mean(MR)/1.128, LCL=CL-3*sigma_hat, UCL=CL+3*sigma_hat. Recalculate estimated limits when the interval changes. There is no baseline approval, frozen monitoring period, automated SPC alarm or crossing count.
- **Why it fits the use case:** The measured unit is a bike count at a scheduled inspection, not a customer success/failure. The user can inspect hourly inventory patterns and estimated Individuals limits for a chosen interval. Intraday patterns, bounded counts and serial dependence can affect interpretation; the chart does not establish process stability or a calibrated false-alarm rate.
- **Assumptions and how the tool handles them:** All stations are open with usable bikes/docks and positive fixed capacity. Reindex the selected interval to the planned hourly calendar; preserve missing readings, and never bridge missing hours or overnight gaps when estimating moving ranges. At least one adjacent valid pair and positive moving-range variation are required for UCL/LCL. Still show observed data and its mean when limits cannot be estimated. Do not clip I-chart limits to physical capacity or confuse them with inventory targets. Interpretation and investigation belong to the user; no suitability-review form or diagnostic baseline plots are included. The playback timestamp caps all analysis data.
- **Known-answer check:** Five-station snapshot fixture with capacity 30 and bikes [0,0,9,15,30] gives empty=40%, full=20%, two-way availability=40%, and mean occupancy=36%. A single-station hourly sequence [10,12,11,13,14] gives CL=12, MR=[2,1,2,1], MR_bar=1.5, sigma_hat=1.329787234, LCL=8.010638298 and UCL=15.989361702. Test selected-window isolation, no future data, missing/overnight gaps, constant data, one observation and invalid input. Source: course sysen/functions/functions_process_control.py (moving-range estimator and plot layers), with deterministic d2=1.128 from [NIST Individuals charts](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc322.htm).

Fixed for every team:
- The statistic lives in **one plain, tested function** (`app/dockwatch/qc.py`). The API, app or
  package only calls it and displays the result. No statistics inside UI code.
- Every statistic has a test against a known answer and a degenerate case (constant data, n = 1, missing values).
- You can explain every number the tool prints. If you cannot, it is not done.

## 5. Delivery (rubric: working tool 25)
- **Stack:** React/Vite dashboard, MapLibre station map, FastAPI HTTP API and the independently installable `dockwatch` Python library. Plotnine renders the existing analysis charts to SVG. No Streamlit runtime.
- **Implementation reference:** Adapt `demos/fastapi/` and `demos/reactfront/`. Reuse the previously verified framework-free data validation, statistics and plotnine functions. The React migration preserves the final interval-based dashboard behavior, not the superseded baseline-review design.
- **Environment:** Python 3.12 with `uv.lock`; Node.js 22 or newer supported by the frontend engine constraint, with `package-lock.json`. All source comments and docstrings are English.
- **Local run:** `./app/testme` installs locked dependencies, builds React, then serves the dashboard and API on one origin. A Vite development command is also documented.
- **Deployment target:** Course Posit Connect, as one FastAPI application containing the built React assets and synthetic datasets. `app/manifestme` creates a self-contained bundle; `app/deployme` publishes only when explicitly invoked with configured credentials. Actual remote publication is separate from local verification.
- **Plan:** [MVP](docs/MVP.md) and [implementation plan](docs/plan.md).

## 6. Outputs
- **What the user sees:** An interactive Ithaca-area map with all 20 simulated stations, a scenario date/hour selector, and hoverable station markers showing bike count out of 30, free docks, observation time, status, and action suggestion. Missing/stale observations have their own marker states. Double-clicking a station marker or using the sidebar selects its details and analysis. The action queue includes station IDs and names. Also show hourly inventory and occupancy, empty/full/two-way-available observation proportions with counts and coverage, station/hour heatmaps, adjacent-hour net changes, and a station detail chart. Analysis has an inclusive time-range slider and an Individuals chart with the selected interval mean and estimated UCL/LCL. Insufficient or constant data keep their observations and mean visible with a short explanation. CSV uploads use the same validation and scheduled grid as bundled data. All demo data are labeled synthetic.

Suggestions use the most recent eligible snapshot, never inferred customer demand. As an
explicit demo policy, occupancy below 20% suggests adding bikes toward floor(capacity/2);
above 80% suggests removing bikes toward that target. Exactly 20% or 80% does not trigger.
For capacity 30, bikes=3 suggests add 12; bikes=27 suggests remove 12. The target is 15 bikes per station. These are business
rules, not statistical conclusions. Missing records or records at least 60 minutes old
require reinspection; even fresh counts are labeled with their timestamp and require
confirmation before a physical move. Demo freshness uses the displayed scenario time.
Rank fresh empty/full stations first, then low/high stock; include missing/stale stations for reinspection. No automatic dispatch or guaranteed route.

Hourly snapshots do not measure failed attempts, exact downtime, separate pickup/return
counts, or the cause of inventory changes. The MVP supports snapshot export; manual entry, persistent review records and session logging are deferred.

## 7. Test datasets and codebook (rubric: demo 10, datasets 5, codebook 5)
2-3 small CSVs in `data/`, invented but shaped like real field data, each showing one behavior.
`data/README.md` is the codebook: every file, every column with units, and what it would take to
collect this data for real.
- **Datasets:** normal.csv (hourly inventory under a repeatable daily pattern), disruption.csv (identical baseline, stronger morning residential-to-office transfers in monitoring), and edge_cases.csv (valid empty/full, threshold and constant-baseline examples; missing-hour and insufficient-history fixtures live in software tests). Schema: timestamp, station_id, bikes; capacity is in stations.json. Generator scale: 20 fictional Ithaca-area stations with fixed mapped locations, capacity 30 each, total fleet 300 bikes, 15 hourly snapshots from 07:00 through 21:00 (inclusive, America/New_York), 40 comparable synthetic service days; first 25 baseline, last 15 monitoring as generation-only labels with no application gating (12,000 rows per complete scenario: 20 stations × 40 days × 15 observations). Start from 15 bikes per station and apply conserving random transfers for variation. A fixed-seed, bounded, fleet-conserving transfer simulator produces snapshots; generation-only transfers and scenario labels are not product inputs. Inventory continues across service dates with no daily reset, overnight movements or rebalancing. The first snapshot starts at 15 bikes per station. This continuity can create serial dependence, so interval-based I-chart limits are exploratory estimates and do not certify stability. Include a generator, metadata and codebook. Invalid records belong in test fixtures. No customer failure probabilities or attempted-trip counts are required. Morning/evening transfer weights may reflect hypothetical residential-to-campus/employment-area travel, but are disclosed synthetic assumptions, not measured Ithaca commuting patterns. The initial map uses the team screenshot as a geographic reference, not as live telemetry.

## 8. Documentation and reproducibility (rubric: docs 10, public repo 5)
- `README.md` says what the tool does, for whom, every input and parameter, how to run it in one
  command, and walks through the demo on each test dataset.
- Public GitHub repo; a fresh clone runs `testme` and the tests pass with no extra steps.
- Submit on Devpost: the repo link plus a demo.

## 9. Out of scope
What we will NOT build, so nobody (human or agent) builds it by accident.
- Default: logins, databases, real customer data, a second statistic before the first one is tested.
- No customer-attempt or failure-rate inference, exact stockout duration, demand forecasting, machine learning, route optimization, automatic dispatch, faults/closures, real telemetry, or causal claims about rebalancing. No p chart treating successive inventory snapshots as independent customer trials. The data generator uses a minimal instantaneous-transfer abstraction, not a travel-time or full traffic simulator.
