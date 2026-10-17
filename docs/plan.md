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

These are local verification results. No public deployment, Git commit or push has been performed. H-09 remains checked out until the repository's commit-based check-in is requested.
