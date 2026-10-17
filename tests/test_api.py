"""Exercise the public API against known values, gaps and invalid inputs."""

from io import StringIO

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api


@pytest.fixture
def client():
    with TestClient(api.app) as test_client:
        yield test_client
    api.UPLOADS.clear()


def upload_csv(client, content, filename="readings.csv"):
    response = client.post("/api/uploads", files={"file": (filename, content, "text/csv")})
    assert response.status_code == 201, response.text
    return response.json()["source"]["id"]


def test_configuration_and_health_match_existing_demo(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/api/health").json() == {"status": "ok"}
    config = client.get("/api/config").json()
    assert config["default_cursor"] == 377
    assert config["timestamps"][377] == "2026-09-28T09:00:00-04:00"
    assert len(config["timestamps"]) == 600
    assert len(config["stations"]) == 20
    assert config["source"] == {"id": "normal", "label": "normal.csv", "observations": 12000}
    assert config["stations"][0]["display_name"] == "Robert Purcell Community Center"
    assert [scenario["id"] for scenario in config["scenarios"]] == ["normal", "disruption", "edge_cases"]
    assert client.get("/api/docs").status_code == 200
    assert "/api/analysis" in client.get("/api/openapi.json").json()["paths"]


@pytest.mark.parametrize("source", ["normal", "disruption", "edge_cases"])
def test_snapshot_matches_core_and_preserves_queue_names(client, source):
    response = client.get("/api/snapshot", params={"source": source, "cursor": 377})
    assert response.status_code == 200
    result = response.json()
    direct = api.snapshot_at(api._builtin(source), api.STATIONS, api.PLAN[377])
    assert result["metrics"] == api.snapshot_metrics(direct)
    assert sum(row["bikes"] for row in result["stations"]) == 300
    assert all(row["display_name"] and "net_change" in row for row in result["stations"])
    assert [(row["priority"], row["station_id"]) for row in result["queue"]] == sorted(
        (row["priority"], row["station_id"]) for row in result["queue"]
    )
    assert all(row["priority"] < 4 for row in result["queue"])


def test_uploaded_known_answer_keeps_the_statistical_core(client):
    content = "timestamp,station_id,bikes\n" + "".join(
        f"2026-08-24T{hour:02}:00:00-04:00,S01,{bikes}\n"
        for hour, bikes in zip(range(7, 12), [10, 12, 11, 13, 14])
    )
    source = upload_csv(client, content)
    response = client.get("/api/analysis", params={"source": source, "cursor": 4, "start": 0, "end": 4})
    assert response.status_code == 200
    result = response.json()
    assert result["summary"]["limits"] == pytest.approx({
        "cl": 12, "lcl": 8.01063829787234, "ucl": 15.98936170212766,
        "mr_mean": 1.5, "sigma": 1.3297872340425534, "n": 5, "pairs": 4,
    })
    assert result["start"] == "2026-08-24T07:00:00-04:00"
    assert result["end"] == "2026-08-24T11:00:00-04:00"
    assert [row["bikes"] for row in result["history"]] == [10, 12, 11, 13, 14]
    assert not {"baseline", "reviewed", "signals"} & result["summary"].keys()


def test_upload_preserves_missingness_and_excludes_future_data(client):
    source = upload_csv(client, "timestamp,station_id,bikes\n"
                        "2026-08-24T07:00:00-04:00,S01,10\n"
                        "2026-08-24T09:00:00-04:00,S01,30\n")
    snapshot = client.get("/api/snapshot", params={"source": source, "cursor": 1}).json()
    selected = next(row for row in snapshot["stations"] if row["station_id"] == "S01")
    assert selected["bikes"] is None
    assert selected["latest_bikes"] == 10
    assert selected["latest_timestamp"] == "2026-08-24T07:00:00-04:00"
    assert selected["status"] == "stale"
    assert selected["net_change"] is None
    assert snapshot["metrics"]["coverage"] == 0
    analysis = client.get("/api/analysis", params={"source": source, "cursor": 1, "end": 1}).json()
    assert [row["bikes"] for row in analysis["history"]] == [10, None]
    assert analysis["summary"]["cl"] == 10
    assert analysis["summary"]["limits"] is None
    assert analysis["summary"]["pairs"] == 0


def test_no_fleet_requirement_for_uploads_and_empty_upload_is_missing(client):
    source = upload_csv(client, "timestamp,station_id,bikes\n")
    result = client.get("/api/snapshot", params={"source": source, "cursor": 0}).json()
    assert result["metrics"]["n"] == 0
    assert result["metrics"]["availability"] is None
    assert all(row["bikes"] is None for row in result["stations"])
    assert all(row["status"] == "missing" for row in result["stations"])


@pytest.mark.parametrize("path,params", [
    ("/api/config", {"source": "../normal.csv"}),
    ("/api/snapshot", {"cursor": -1}),
    ("/api/snapshot", {"cursor": 600}),
    ("/api/analysis", {"station_id": "unknown"}),
    ("/api/analysis", {"cursor": 10, "start": 5, "end": 11}),
    ("/api/analysis", {"cursor": 10, "start": 5, "end": 4}),
    ("/api/charts/history.svg", {"cursor": 10, "end": 11}),
    ("/api/charts/unknown.svg", {}),
])
def test_invalid_queries_have_readable_client_errors(client, path, params):
    response = client.get(path, params=params)
    assert response.status_code in {404, 422}
    assert response.json()["detail"]


@pytest.mark.parametrize("content,message", [
    ("timestamp,station_id,bikes\n2026-08-24T07:00:00-04:00,S01,31\n", "outside station capacity"),
    ("timestamp,station_id,bikes\n2026-08-24T07:00:00,S01,10\n", "include a timezone"),
    ("timestamp,station_id,bikes\n2026-08-24T07:30:00-04:00,S01,10\n", "not a planned"),
    ("timestamp,station_id,bikes\n2026-08-24T07:00:00-04:00,S99,10\n", "unknown station"),
    ("", "No columns"),
])
def test_upload_errors_are_reported_without_creating_a_source(client, content, message):
    response = client.post("/api/uploads", files={"file": ("readings.csv", content, "text/csv")})
    assert response.status_code == 422
    assert message in response.json()["detail"]
    assert not api.UPLOADS


def test_upload_size_and_source_count_are_bounded(client, monkeypatch):
    monkeypatch.setattr(api, "MAX_UPLOAD_BYTES", 100)
    response = client.post("/api/uploads", files={"file": ("large.csv", b"x" * 101, "text/csv")})
    assert response.status_code == 413
    monkeypatch.setattr(api, "MAX_UPLOAD_SOURCES", 2)
    first = upload_csv(client, "timestamp,station_id,bikes\n")
    second = upload_csv(client, "timestamp,station_id,bikes\n")
    third = upload_csv(client, "timestamp,station_id,bikes\n")
    assert client.get("/api/config", params={"source": first}).status_code == 404
    assert client.get("/api/config", params={"source": second}).status_code == 200
    assert client.get("/api/config", params={"source": third}).status_code == 200


def test_snapshot_download_preserves_original_columns(client):
    response = client.get("/api/snapshot.csv", params={"cursor": 377})
    assert response.status_code == 200
    assert "dockwatch-20260928-0900.csv" in response.headers["content-disposition"]
    exported = pd.read_csv(StringIO(response.text))
    direct = api.snapshot_at(api._builtin("normal"), api.STATIONS, api.PLAN[377])
    assert exported.columns.tolist() == direct.columns.tolist()
    assert exported["bikes"].tolist() == direct["bikes"].tolist()
    assert "2026-09-28 09:00:00-04:00" in response.text


@pytest.mark.parametrize("chart", ["history", "inventory", "heatmap"])
def test_chart_endpoints_render_svg_without_leaking_figures(client, chart):
    response = client.get(f"/api/charts/{chart}.svg", params={"cursor": 377, "start": 375, "end": 377})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert b"<svg" in response.content and b"</svg>" in response.content
    assert not api.plt.get_fignums()
