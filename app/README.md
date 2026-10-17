# DockWatch React + FastAPI

**[Open the public dashboard — no sign-in required](https://connect.systems-apps.com/content/ca01a272-5237-45e0-ac0c-4f3453f50c4c/)** ·
[Public API documentation](https://connect.systems-apps.com/content/ca01a272-5237-45e0-ac0c-4f3453f50c4c/api/docs).
Anonymous page and API access were checked on October 17, 2026.

The [complete Documentation](../docs/DOCUMENTATION.md) includes setup, each user
function, inputs, parameters, outputs, the data codebook and API/Python reference.

From the repository root, `./app/testme` installs locked dependencies, builds the React client and serves it with the Python API at http://127.0.0.1:8000/. Interactive API documentation is at `/api/docs`.

The frontend lives in `frontend/`, the HTTP adapter in `api.py`, and reusable data/statistics/plotting functions in `dockwatch/`. No statistical formula is duplicated in React.

`./app/manifestme` builds and verifies a self-contained `build/connect` bundle with entrypoint `api:app`. `./app/deployme` publishes that bundle only when explicitly invoked with `CONNECT_SERVER` and `CONNECT_API_KEY` in the environment. Python 3.12 is required on the target server.

See the root [README](../README.md) for installation, library and HTTP contracts, assumptions, tests and deployment details. See [demo checkpoints](../demo/README.md) to reproduce the two v5 sources, Normal operations and Disruption, including current eight-rule History results. The [data codebook](../data/README.md) distinguishes current results from the preserved generation-time three-rule reports.
