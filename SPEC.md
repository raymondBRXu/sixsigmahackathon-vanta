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
- **Method:** Descriptive snapshot metrics plus an exploratory Individuals (I) chart for one station at one selected operating hour across an inclusive service-date range. Each point is that station's observed bike count at the selected hour on one date, not an hourly average or net change. For valid snapshots, occupancy = bikes/capacity; empty proportion = count(bikes=0)/N; full proportion = count(bikes=capacity)/N; two-way availability = count(0<bikes<capacity)/N. Report N and observation coverage. Hourly net change remains current bikes minus previous bikes only for adjacent, one-hour-separated observations within the same service day. For the Individuals chart, CL=mean(valid x), MR_i=abs(x_i-x_(i-1)) at the same selected hour on consecutive scheduled service dates, sigma_hat=mean(MR)/1.128, LCL=CL-3*sigma_hat, UCL=CL+3*sigma_hat. Non-service days do not create missing observations; missing scheduled readings break moving-range pairs. Recalculate estimates when station, hour or date range changes. The Operations realtime station charts additionally show each station’s latest eight scheduled hourly slots against user-specified fixed lines: center 15, upper 24, lower 6 bikes. These are configured inventory references, not limits estimated from the window. There is no baseline approval, frozen monitoring period, automated SPC alarm or crossing count.
- **Why it fits the use case:** The measured unit is a bike count at a scheduled inspection, not a customer success/failure. Comparing the same operating hour across dates separates the chart from within-day inventory patterns. Bounded counts and serial dependence can still affect interpretation; the chart does not establish process stability or a calibrated false-alarm rate.
- **Assumptions and how the tool handles them:** All stations are open with usable bikes/docks and positive fixed capacity. Reindex the selected date range to the planned service dates at the selected hour, preserve missing readings, and never bridge a missing scheduled reading when estimating moving ranges. At least one adjacent valid pair and positive moving-range variation are required for UCL/LCL. Still show observed data and its mean when limits cannot be estimated. Do not clip I-chart limits to physical capacity or confuse them with inventory targets. Interpretation and investigation belong to the user. Station History reads the full configured collection timeline independently of playback. Its date range defaults to the full service-date range; narrowing it selects the observations used for estimates. The API retains explicit cutoff support for other callers. Existing all-hour library/API calls remain available for compatibility; the dashboard uses the same-hour date series.
- **Known-answer check:** Five-station snapshot fixture with capacity 30 and bikes [0,0,9,15,30] gives empty=40%, full=20%, two-way availability=40%, and mean occupancy=36%. A single-station sequence [10,12,11,13,14] at one selected hour on five consecutive scheduled service dates gives CL=12, MR=[2,1,2,1], MR_bar=1.5, sigma_hat=1.329787234, LCL=8.010638298 and UCL=15.989361702. Test station/hour/date isolation, no future data, missing scheduled dates, non-service-day gaps, constant data, one observation and invalid input. Source: course sysen/functions/functions_process_control.py (moving-range estimator and plot layers), with deterministic d2=1.128 from [NIST Individuals charts](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc322.htm).

Fixed for every team:
- Each statistic lives in **one plain, tested function** (`app/dockwatch/qc.py` and `app/dockwatch/patterns.py`). The API, app or
  package only calls it and displays the result. No statistics inside UI code.
- Every statistic has a test against a known answer and a degenerate case (constant data, n = 1, missing values).
- You can explain every number the tool prints. If you cannot, it is not done.

### Optional History diagnosis

Diagnosis is an explicit toggle, off each time History opens. Enabling it selects
the full service-date range and disables every range control until toggled off.
The selected station/hour remains the analysis unit. Compute CL and sigma once
from that full sequence using the existing Individuals estimator, then scan all
eight course-image rules: T1 one point strictly beyond 3 sigma; T2 at least 2 of
3 beyond 2 sigma on the same side; T3 at least 4 of 5 beyond 1 sigma on the same
side; T4 eight strictly on the same side of CL; T5 six strictly increasing or
decreasing; T6 fifteen within inclusive +/-1 sigma; T7 eight outside +/-1 sigma
with both sides represented; T8 fourteen points with thirteen alternating nonzero differences.
Missing planned readings interrupt every window; non-service days do not.
Equal observations break trends/alternation; equality with CL breaks T4.
Unavailable estimates or insufficient contiguous readings are explicit, not a
passed test. Keep raw windows and contributing indices distinct from the point
where the final observation confirms a rule. These are exploratory pattern
matches, not calibrated alarms or diagnoses of their physical cause.

The History chart renders as interactive React SVG with hover/focus information
for every observed point, retaining date selection, gaps, CL and unclipped limits.
Diagnosis flags the union of all contributing points; one tab per detected rule
selects its contributing points in red and a short English explanation above the
chart. Multiple matches of one rule share a tab, and overlapping windows do not
duplicate points. Changing hour recomputes diagnosis while retaining the lock;
closing History resets diagnosis. Python owns all rule decisions; React only
renders API results. Existing static SVG endpoints remain compatible.

## 5. Delivery (rubric: working tool 25)
- **Stack:** React/Vite dashboard, MapLibre station map, FastAPI HTTP API and the independently installable `dockwatch` Python library. History uses interactive React SVG; Plotnine retains the static chart API. No Streamlit runtime.
- **Implementation reference:** Adapt `demos/fastapi/` and `demos/reactfront/`. Reuse the previously verified framework-free data validation, statistics and plotnine functions. The React migration preserves the final interval-based dashboard behavior, not the superseded baseline-review design.
- **Environment:** Python 3.12 with `uv.lock`; Node.js 22 or newer supported by the frontend engine constraint, with `package-lock.json`. All source comments and docstrings are English.
- **Local run:** `./app/testme` installs locked dependencies, builds React, then serves the dashboard and API on one origin. A Vite development command is also documented.
- **Deployment target:** Course Posit Connect, as one FastAPI application containing the built React assets and synthetic datasets. `app/manifestme` creates a self-contained bundle; `app/deployme` publishes only when explicitly invoked with configured credentials. Actual remote publication is separate from local verification.
- **Plan:** [MVP](docs/MVP.md) and [implementation plan](docs/plan.md).

## 6. Outputs
- **What the user sees:** An interactive Ithaca-area map with all 20 simulated stations, a scenario date/hour selector, and hoverable station markers showing bike count out of 30, free docks, observation time, status, and action suggestion. Missing/stale observations have their own marker states. Double-clicking a station marker or using the sidebar selects its Overview details. The action queue includes station IDs and names. Also show hourly inventory and occupancy, empty/full/two-way-available observation proportions with counts and coverage, station/hour heatmaps, adjacent-hour net changes, and a station detail chart. The dashboard has Overview / View by Station navigation, with no separate Operations or Analysis tabs. View by Station shows 20 fixed-size station charts. Every station card has a History button in its upper-right corner. History opens a modal for that station containing the former Analysis Individuals chart, its operating-hour selector, full service-date range slider and observed/CL/LCL/UCL metrics. Each opening defaults to 07:00 (or the first configured hour when 07:00 is unavailable) and the full date range. Opening History pauses playback, which remains paused after closing. Closing or Escape returns focus to the originating History button. The modal uses dates on the horizontal axis, one selected-hour reading per date, and estimated control limits. The clicked History station is independent of the sidebar station selection. Each chart shows up to the last eight scheduled observations through the current playback time, on a fixed 0–30 bike scale and eight horizontal slots. Advancing playback appends the new point and removes the oldest slot; before eight slots have elapsed, no data are invented. Missing readings stay gaps, and lines do not bridge overnight gaps. The existing two-second-per-scheduled-hour playback, pause, step, and scrub controls drive the page. These charts render as lightweight SVG in React from one batched API response; they use fixed inventory reference lines 15/24/6, separately from the estimated Individuals limits in Analysis. The History modal shows only the Individuals chart; the daily inventory and heatmap endpoints remain available to API callers. Insufficient or constant data keep their observations and mean visible with a short explanation. CSV uploads use the same validation and scheduled grid as bundled data. All demo data are labeled synthetic.

Suggestions use the most recent eligible snapshot, never inferred customer demand. As an
explicit demo policy, occupancy below 20% suggests adding bikes toward floor(capacity/2);
above 80% suggests removing bikes toward that target. Exactly 20% or 80% does not trigger.
For capacity 30, bikes=3 suggests add 12; bikes=27 suggests remove 12. The target is 15 bikes per station. These are business
rules, not statistical conclusions. Missing records or records at least 60 minutes old
require reinspection; even fresh counts are labeled with their timestamp and require
confirmation before a physical move. Demo freshness uses the displayed scenario time.
Rank fresh empty/full stations first, then low/high stock; include missing/stale stations for reinspection. No automatic dispatch or guaranteed route.

Clicking any realtime station card opens a larger, single-station chart in the
same View by Station page. The shared playback controls remain available, and the
eight-slot window and fixed 15/24/6 lines continue updating. A Back to all
stations button or Escape restores the 20 fixed-size cards and keyboard focus
to the station chart that was opened. Focused charts support Enter or Space to enlarge. The separate History button opens history without also enlarging the realtime chart; Escape inside History closes only that modal.

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
