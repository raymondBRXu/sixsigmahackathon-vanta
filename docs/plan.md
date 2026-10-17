# React migration implementation plan

Task H-09 in CONTRACT.yaml records this user-authorized migration on ray/dashboard-react.

1. Recover the final approved behavior from the archived Streamlit implementation without restoring its runtime or popping the stash.
2. Reuse and verify framework-free data/QC functions against the known-answer and degenerate fixtures. Retain the plotnine analysis figures.
3. Expose configuration, snapshots, interval analysis, SVG charts, CSV uploads and downloads through FastAPI. Enforce the shared clock cutoff at the API boundary.
4. Rebuild the sidebar, Operations and Analysis views in React. Test state transitions, request freshness, missing values, map selection and interval bounds.
5. Verify the normal, disruption and edge-case checkpoints, both workspaces, uploads/downloads, map hover/double-click/pan, and mobile layout in the browser.
6. Build an installable library and self-contained single-origin deployment bundle. Document locked setup, API, dataset contracts and demo. Verify bundle checksums and runtime independently of the source checkout.

Numerical parity: S01 normal Sep 28 07:00–09:00 has [21,18,17], CL 18.666667, MR mean 2, LCL 13.347518 and UCL 23.985816. Edge cases have 100% two-way availability at Sep 28 09:00, then 0% at 10:00 despite unchanged 50% network occupancy.

The shared clock and analysis interval remain distinct controls. No baseline-review or automatic-SPC feature is reintroduced. Source changes reset time; station/workspace changes preserve the interval. Remote deployment, commit and push are separate from implementation verification.

## Local verification record — October 16, 2026

- Python: `104 passed` across statistics, input validation, plots, HTTP API, deployment packaging and data generation. The framework-free data, QC and plot modules retain the archived implementation.
- React: `22 passed` with the final locked dependencies; production build succeeds. Full npm dependency audit reports `0 vulnerabilities`.
- Default normal demo: 90% two-way availability, two empty stations, no full stations, 100% coverage. S01 shows 17 bikes, 13 free docks and net change -1. The Sep 28 07:00–09:00 analysis displays CL 18.67, LCL 13.35 and UCL 23.99.
- Scenario checks: disruption shows 60% availability, three empty and five full stations. Edge cases reproduce 100% availability at 09:00 and 0% at 10:00. A single reading and a constant interval show the mean and explain why limits cannot be estimated.
- Browser checks: map details, double-click selection, persistent map camera during stepping/basemap toggles, playback, automatic pause in Analysis, interval clamping, station switching, all three SVG figures and snapshot CSV download pass. OpenFreeMap street tiles render; a blank map remains available without tiles.
- Upload checks: an out-of-capacity row produces a row-specific error. A three-row file shows 5% current coverage, preserves a zero as an empty reading and labels S01's prior count of 12 as stale rather than current inventory.
- Responsive checks: Operations and Analysis render at 390px without horizontal page overflow. The temporary browser viewport override was reset after testing.
- `app/testme` installs/builds and starts the server; `/health` and the dashboard respond successfully. The separate temporary verification server was stopped afterward.
- `uv build` produces the wheel and source archive. The wheel installs in a fresh isolated Python environment and reproduces CL 12, LCL 8.010638298 and UCL 15.989361702 without importing the web or plotting runtime.
- `app/manifestme` verifies 17 bundled file checksums. An isolated import from `build/connect`, mounted beneath `/content/test/`, serves React assets, the map worker, API, charts, uploads, CSV and Swagger successfully.

These are local verification results; no public deployment was verified. H-09 was subsequently committed as b5a24a3.


## Same-hour Individuals chart — H-10

The user requested this follow-up after the React migration commit. Keep station
selection, add operating-hour selection, and replace the Individuals time-range
control with an inclusive service-date range. Each chart point is one observed
count for the station at the chosen hour on one date. The shared playback clock
still caps observations; a selected hour that has not elapsed today is omitted.

The chart mean uses valid selected values. Moving ranges use consecutive
scheduled service dates, preserving missing readings so no pair spans a missing
scheduled observation. Weekends outside the service calendar do not create gaps.
The existing d2=1.128 estimator and unclipped CL/LCL/UCL are retained. Legacy
all-hour library/API calls remain available; the React analysis uses the new
hour/date parameters.

Verification covers known-answer and degenerate statistics, station/hour/date
isolation, scheduled-date missingness, future cutoffs, API and SVG consistency,
state transitions and real-browser station/hour/date changes. The normal S01
09:00 series for Sep 22–28 is [17,23,19,15,17]: CL=18.2, MR mean=4,
LCL=7.561702128 and UCL=28.838297872.


H-10 local verification:

- `uv run --locked --extra api pytest`: `133 passed, 1 warning in 17.53s`.
  The warning is the existing Starlette/httpx test-client deprecation. This
  sandbox uses `UV_CACHE_DIR=/tmp/dockwatch-uv-cache` for the same locked command.
- `npm test --prefix app/frontend`: `Test Files 6 passed (6)`, `Tests 31 passed (31)`.
- `npm run build --prefix app/frontend`: `37 modules transformed`, production
  build succeeds; the existing MapLibre chunk-size warning remains.
- Browser: S01 at 09:00 on Sep 22–28 displays 5/5, CL 18.20, LCL 7.56, UCL
  28.84 and five points on a date-only axis. Changing to 10:00 at the 09:00 clock
  shows 4/4, excluding the future date/hour. Station switching preserves hour
  and dates; both range handles advance by scheduled date. Rewinding to the
  first snapshot clamps both date endpoints, displays 0/0 for a future hour,
  and displays 1/1 with CL 15.00 when selecting elapsed hour 07:00.
- Independent review found no actionable issues; probes also verified DST and
  timezone cutoff behavior, missing scheduled readings and non-service dates.

H-10 implementation is ready; it remains checked out until a commit is requested.


### H-10 follow-up: full-data Analysis

The user requested removing the Analysis simulation-time controls and loading
all data by default. Analysis now sends the final configured timeline index to
the existing API, independently of the Operations clock. Its single retained
date slider starts at the full service-date range, and Operations clock changes
never clamp or modify it. Station/workspace changes preserve the chosen range;
source changes restore the full range. Daily context figures use the final
collection date and are labeled as the latest day. Earlier H-10 cutoff/browser
records above document the superseded interaction; explicit API cutoffs remain
supported and the statistical estimator is unchanged.


Follow-up verification: `npm test --prefix app/frontend` reports `6 passed`
test files and `32 passed` tests; production build reports `37 modules
transformed` and `built in 1.11s`. The existing MapLibre chunk-size warning
remains. Browser verification on the user's existing server confirms that
Analysis has no playback controls, defaults to Aug 24–Oct 16 with 40/40
readings, and sends the final index 599. Selecting Oct 1–16 at 21:00 gives
12/12; rewinding Operations to Aug 24 preserves that selection and its
results. No extra preview server was started.

### H-10 follow-up: realtime station page

Operations now has Overview and Realtime View by Station subpages sharing the
existing simulation clock. The realtime page renders all 20 stations in fixed
336 × 275 pixel cards, each with an eight-slot hourly window and a fixed 0–30
bike scale. Center 15, upper 24 and lower 6 are configured inventory reference
lines, independent of the Analysis estimator. Playback advances one scheduled
hour every two seconds; rewinding and changing scenarios rebuild the windows.
The single `/api/realtime` response reindexes every station to the same latest
eight scheduled timestamps at or before the cursor. Missing values remain
missing, early windows contain fewer than eight observations, and charts do
not connect overnight gaps. SVG geometry is rendered in React from the Python
prepared series. Analysis keeps its full-data date range behavior.

Realtime verification:

- `UV_CACHE_DIR=/tmp/dockwatch-uv-cache uv run --locked --extra api pytest`:
  `152 passed, 1 warning in 16.99s`; the existing Starlette/httpx deprecation remains.
- `npm test --prefix app/frontend`: `Test Files 7 passed (7)`,
  `Tests 41 passed (41)`. `npm run build --prefix app/frontend`:
  `39 modules transformed`, `built in 1.22s`; the existing MapLibre chunk warning remains.
- Browser: all 20 charts have eight points at the default clock, with fixed
  Upper 24, CL 15 and Lower 6 labels. Stepping from Sep 28 09:00 to 10:00 drops
  Sep 25 17:00 and adds Sep 28 10:00. Continuous playback keeps eight points.
  Rewinding to Aug 24 07:00 shows one point, then two after one step.
  Switching to Edge cases restores the default clock and all 20 current values
  are 15. Overview returns normally; Analysis retains Aug 24–Oct 16 without
  playback controls.
- All cards measure 336 × 275 and SVGs 306 × 171 pixels. At 390px and 320px
  viewport widths, cards keep their dimensions and the page has no horizontal
  overflow; the 320px layout scrolls inside the chart grid.
- A temporary three-row upload shows S01 values 12 at 07:00 and 0 at 09:00,
  retains six missing slots, and draws no segment across the missing 08:00.
  Its future 10:00 value is absent at 09:00; the other 19 station cards remain
  visible with no reading. This fixture was used only on the temporary server.
- Independent read-only review found no actionable issues. The temporary
  port-8001 server and browser tab were stopped/closed after verification;
  the user's port-8000 process was left running and needs a restart for the
  new endpoint. The temporary viewport override was reset.

### H-10 follow-up: enlarge one realtime chart

Each realtime station card now opens a larger single-station chart when clicked.
Its enlarge button also works with the keyboard. The shared clock, fixed lines
and eight-slot window keep updating. Back to all stations or Escape restores
the grid and returns keyboard focus to the originating station's enlarge button.
The grid keeps its fixed card sizes; the enlarged chart fits the content width.

Verification: `npm test --prefix app/frontend` reports `Test Files 7 passed (7)`
and `Tests 41 passed (41)`; production build reports `39 modules transformed`
and `built in 1.20s`, with the existing MapLibre chunk warning. Browser checks
confirm clicking S02 shows one chart enlarged from 306 to 884 pixels wide,
playback advances from cursor 377 to 380 while retaining eight points, and Back
restores all 20 cards at 336 × 275 pixels with focus on S02. Enter opens S20;
Escape returns focus to S20. The enlarged view fits a 390px viewport without
horizontal overflow. No backend or statistical changes were needed. The
temporary port-8001 server and browser tab were closed, and viewport testing
was reset. `git diff --check` passes.

### H-10 follow-up: station History dialogs and simpler navigation

The dashboard now has only Overview / View by Station navigation. The former
Operations and Analysis tabs are removed. Every station chart has a History
button in its upper-right corner, which opens the Individuals chart for that
station in a native modal. Each opening resets the hour to 07:00 and dates to
the full configured range. The dialog retains hour/date selection, observed
counts and estimated CL/LCL/UCL, using the dataset's final cursor. Daily context
charts are no longer in this UI; their API endpoints remain available.

History pauses playback and leaves it paused on close. Its station is independent
of the Overview sidebar selection. Closing or Escape restores the original
History button's focus and leaves any enlarged realtime chart intact. Chart-body
clicks and Enter/Space still enlarge the live chart; the History button does not.

Verification: `npm test --prefix app/frontend` reports `Test Files 7 passed (7)`
and `Tests 44 passed (44)`; build reports `41 modules transformed` and
`built in 1.08s`, with the existing MapLibre chunk warning. Browser checks on
the user's existing port-8000 server confirm exactly 20 History controls,
S02 History selecting S02 despite sidebar S01, 07:00/default Aug 24–Oct 16,
and actual SVG rendering with 40/40 observations. Changing to 21:00/Oct 1–16
gives 12/12; opening S03 restores 07:00 and the full range. Opening S20 History
while its live chart is enlarged pauses playback; Escape closes only History,
and Back restores all 20 charts. Focus returns to the History button after the
modal closes. At 390px, the dialog fits at 370px without page or content overflow.
Temporary browser tabs were closed and the viewport override reset. No extra
server or backend changes were needed; `git diff --check` passes.

### H-11: interactive History diagnosis

Before implementation, the working tree was clean and the latest commit was
`f8b1e48` (`react v2`), preserving the H-10 snapshot. The user's explicit request
authorized this task. No new commit or remote publication was requested.

Diagnosis defaults off. Its toggle atomically selects the full configured date
range and locks both handles and both date selectors; the reducer also rejects
range mutations while enabled. Turning it off unlocks the full range, and closing
or reopening History resets diagnosis. Hour changes retain the lock and request
fresh results. Request keys and cancellation prevent stale findings from being
shown during selection changes.

The plain detector in `app/dockwatch/patterns.py` applies all eight course-image
rules to one station/hour's full service-date series using the existing mean and
MR/1.128 sigma. Missing slots break windows; contributing points are distinct
from each window's confirming endpoint. Raw events are retained and each detected
rule returns a deduplicated union of contributing indices. Unavailable tests are
explicit. `/api/analysis?diagnosis=true` enforces full planned timestamp coverage
and full configured bounds. Missing readings do not disable the feature. Default
requests skip detection; existing static SVG endpoints remain compatible.

History now uses React SVG with hover/focus/tap details, date slots, missing gaps
and unclipped limits. All matched points are flagged; the selected issue's points
are red and other matches have amber rings. Tabs below the chart collect each
detected rule and update its short English explanation above the chart. Tabs
support arrows/Home/End; keyboard users can focus individual observations.
The chart scrolls horizontally on narrow screens and the tooltip sits outside
the scroller to avoid clipping. Python supplies every rule decision.

Verification on 2026-10-17:

- Stats-first detector verification preceded UI implementation: `50 passed`.
- `UV_CACHE_DIR=/tmp/dockwatch-uv-cache uv run --locked --extra api pytest`:
  `216 passed, 1 warning in 17.07s`; only the existing Starlette/httpx warning.
- `npm test --prefix app/frontend`: `Test Files 8 passed (8)`,
  `Tests 60 passed (60)`. `npm run build --prefix app/frontend`:
  `43 modules transformed`, `built in 1.14s`; existing MapLibre chunk warning.
- Independent read-only review found no defects. Additional checks on 300 seeded
  boundary/gap series preserve results under positive affine transforms and
  reverse window/contributor indices correctly under time reversal. Five
  independently planted rule fixtures also passed.
- Browser: normal S01 at 07:00 narrows to 20 readings; Diagnosis restores 40,
  locks all four controls, flags 22 unique contributing points and initially
  highlights T1's one point. T2 selects 9 red points, T3 selects 12, with matching
  English text and keyboard tab focus. Point details include date/hour/count
  and rule IDs. Switching to 21:00 recomputes while locked; disabling diagnosis
  removes tabs/flags and permits Oct 1–16 (12 readings). Opening S02 resets
  diagnosis off, 07:00 and full dates.
- At 390px, dialog width 370px and body width 390px; modal content has no horizontal
  overflow. The 640px SVG scrolls inside its 334px chart viewport. Viewport override
  reset after checks.
- The updated server runs at the original localhost port 8000. The original page
  was reloaded and verified with Morning disruption, S01, 07:00 and diagnosis on
  (T1/T2/T3/T4/T7 tabs). The temporary port 8001 verification server/tab are cleaned
  up after testing. Work is verified and remains uncommitted.

## Linked inventory alerts and map interactions (H-12)

The starting snapshot was clean and saved in `10a2dcf` (`react + test`).
The Action queue now has Station, Bikes and State columns. A single horizontal
strip of red empty/full alerts replaces the old map heading. Each alert opens
its station's enlarged realtime chart without changing the playback state or
clock. Close controls dismiss only the current continuous station/status
condition; valid recovery or a different critical condition permits another
alert. Missing/loading readings hide alerts without implying recovery. A source
change, rewind or nonconsecutive seek resets dismissals.

The shared snapshot and alert lifecycle stay mounted in App so recovery is
observed while viewing live charts. Queue rows, alerts and map markers link on
hover/focus through a station ID. The marker halo preserves status color,
selection, camera and marker instances. Changing the source or cursor clears
transient interaction state, including old focus from removed queue rows.

Verification on 2026-10-17:

- `npm test --prefix app/frontend`: `Test Files 10 passed (10)`,
  `Tests 89 passed (89)`. Tests cover alert episodes, missing/loading states,
  source/seek resets, independent dismissals, close versus navigation, shared
  playback, direct station expansion and reciprocal hover/focus links.
- `npm run build --prefix app/frontend`: `47 modules transformed`,
  `built in 1.14s`; only the existing MapLibre bundle-size warning.
- Browser on port 8000: at cursor 377, queue row S15 highlights its alert and
  map halo. Closing S15 leaves S16 and keeps focus on its open button. At 378,
  S15 remains empty in the queue but its dismissed alert stays hidden; S08/S09/
  S12 show Full alerts. Opening S08 while playing preserves cursor 378 and
  continues to cursor 381 with exactly one live chart and eight readings.
  Back restores 20 cards. Returning to Overview shows S08 recovered to 29
  bikes with no Full alert, while the remaining critical stations stay visible.
- At 390px and 320px viewport widths, document width equals viewport width;
  all alert cards have the same vertical position and scroll inside the strip.
  Desktop screenshot confirms visible red prompts and a clear marker halo.
  Browser error log is empty; the temporary viewport override is reset.
- Independent review identified a possible stale focus on rewind; clearing
  transient state on source/cursor change resolves it and has regression coverage.

Implementation and validation are complete; changes remain uncommitted.

### Sidebar playback follow-up

The shared Clock component now appears once, below the Station selector in the
sidebar, with its existing reducer and timer unchanged. Its three buttons stay
on one row, with the selected date/time and timeline beneath the heading.
Loading and source errors hide the clock until a valid configuration is ready.
On narrow screens the clock spans the settings panel; the main content has no
duplicate playback controls. History retains its own date range and pause behavior.

- Existing App integration tests were extended to check sidebar containment
  through Overview, station view, History and modal close: `16 tests passed`.
- Production build: `47 modules transformed`, `built in 1.09s`; existing
  MapLibre chunk-size warning only.
- Browser: stepping 377 to 378 updates availability to 75%; playback advances
  and pauses; timeline Home disables previous Step at 0, and End disables Play
  and next Step at 599. All 20 realtime charts follow sidebar stepping.
  History opens and disables playback, then closes normally. Switching to
  Edge cases restores the sidebar clock and 100% availability at cursor 377.
- At 1024px the sidebar buttons fit its narrower width. At 390px and 320px,
  the page and clock have no horizontal overflow. Browser error log is empty;
  viewport override is reset and the temporary verification tab is closed.
