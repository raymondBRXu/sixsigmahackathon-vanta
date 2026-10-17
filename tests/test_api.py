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
    assert config["service_dates"] == api.SETTINGS["service_dates"]
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


@pytest.mark.parametrize("cursor", [0, 7, 8, 15])
def test_realtime_returns_named_stations_and_scheduled_window(client, cursor):
    response = client.get("/api/realtime", params={"cursor": cursor})
    assert response.status_code == 200
    result = response.json()
    timestamps = [stamp.isoformat() for stamp in api.PLAN[max(0, cursor - 7):cursor + 1]]
    assert result["timestamp"] == api.PLAN[cursor].isoformat()
    assert result["window_size"] == 8
    assert result["timestamps"] == timestamps
    assert result["reference_lines"] == {"center": 15, "upper": 24, "lower": 6}
    assert [station["station_id"] for station in result["stations"]] == api.STATIONS["station_id"].tolist()
    assert len(result["stations"]) == 20
    assert result["stations"][0]["display_name"] == "Robert Purcell Community Center"
    expected = api._builtin("normal").set_index(["station_id", "timestamp"])["bikes"]
    for station in result["stations"]:
        assert station["display_name"] == api.NAMES[station["station_id"]]
        assert station["capacity"] == 30
        assert [row["timestamp"] for row in station["history"]] == timestamps
        assert [row["bikes"] for row in station["history"]] == [
            expected.loc[station["station_id"], pd.Timestamp(stamp)] for stamp in timestamps
        ]


def test_realtime_appends_drops_oldest_and_rewinds_deterministically(client):
    before = client.get("/api/realtime", params={"cursor": 7}).json()
    after = client.get("/api/realtime", params={"cursor": 8}).json()
    assert after["timestamps"] == before["timestamps"][1:] + [api.PLAN[8].isoformat()]
    for old_station, new_station in zip(before["stations"], after["stations"]):
        assert new_station["history"][:-1] == old_station["history"][1:]
    assert client.get("/api/realtime", params={"cursor": 7}).json() == before


def test_realtime_upload_keeps_missing_slots_all_stations_and_current_cutoff(client):
    source = upload_csv(client, "timestamp,station_id,bikes\n"
                        "2026-08-24T07:00:00-04:00,S01,10\n"
                        "2026-08-24T09:00:00-04:00,S01,30\n")
    result = client.get("/api/realtime", params={"source": source, "cursor": 1}).json()
    assert result["timestamps"] == [stamp.isoformat() for stamp in api.PLAN[:2]]
    assert len(result["stations"]) == 20
    assert [row["bikes"] for row in result["stations"][0]["history"]] == [10, None]
    assert all(row["bikes"] is None for station in result["stations"][1:] for row in station["history"])
    assert all(row["timestamp"] <= result["timestamp"]
               for station in result["stations"] for row in station["history"])
    advanced = client.get("/api/realtime", params={"source": source, "cursor": 2}).json()
    assert [row["bikes"] for row in advanced["stations"][0]["history"]] == [10, None, 30]
    assert advanced["reference_lines"] == {"center": 15, "upper": 24, "lower": 6}
    assert client.get("/api/realtime", params={"source": source, "cursor": 1}).json() == result


def test_realtime_empty_upload_has_eight_missing_slots_for_every_station(client):
    source = upload_csv(client, "timestamp,station_id,bikes\n")
    result = client.get("/api/realtime", params={"source": source, "cursor": 15}).json()
    assert len(result["stations"]) == 20
    assert len(result["timestamps"]) == 8
    assert all(len(station["history"]) == 8 for station in result["stations"])
    assert all(row["bikes"] is None for station in result["stations"] for row in station["history"])


def test_realtime_source_switch_preserves_window_and_fixed_references(client):
    normal = client.get("/api/realtime", params={"source": "normal", "cursor": 377}).json()
    disrupted = client.get("/api/realtime", params={"source": "disruption", "cursor": 377}).json()
    assert normal["timestamps"] == disrupted["timestamps"]
    assert normal["reference_lines"] == disrupted["reference_lines"] == {"center": 15, "upper": 24, "lower": 6}
    assert normal["stations"] != disrupted["stations"]
    assert client.get("/api/realtime", params={"source": "normal", "cursor": 377}).json() == normal


def test_realtime_window_size_is_fixed_and_not_a_query_parameter(client):
    schema = client.get("/api/openapi.json").json()["paths"]["/api/realtime"]["get"]
    assert {parameter["name"] for parameter in schema["parameters"]} == {"source", "cursor"}
    response = client.get("/api/realtime", params={"cursor": 15, "window_size": 1})
    assert response.status_code == 200
    assert response.json()["window_size"] == 8
    assert len(response.json()["timestamps"]) == 8


@pytest.mark.parametrize("params,status", [
    ({"cursor": -1}, 422),
    ({"cursor": 600}, 422),
    ({"cursor": 1.5}, 422),
    ({"source": "unknown"}, 404),
])
def test_realtime_invalid_queries_return_client_errors(client, params, status):
    response = client.get("/api/realtime", params=params)
    assert response.status_code == status
    assert response.json()["detail"]


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


def test_same_hour_analysis_upload_matches_known_answer_and_metadata(client):
    content = "timestamp,station_id,bikes\n" + "".join(
        f"{day}T09:00:00-04:00,S01,{bikes}\n"
        f"{day}T08:00:00-04:00,S01,30\n"
        f"{day}T09:00:00-04:00,S02,0\n"
        for day, bikes in zip(api.SETTINGS["service_dates"][:5], [10, 12, 11, 13, 14])
    )
    source = upload_csv(client, content)
    params = {"source": source, "cursor": 62, "station_id": "S01", "hour": 9,
              "start_date": "2026-08-24", "end_date": "2026-08-28"}
    response = client.get("/api/analysis", params=params)
    assert response.status_code == 200
    result = response.json()
    assert {key: result[key] for key in ("hour", "start_date", "end_date")} == {
        "hour": 9, "start_date": "2026-08-24", "end_date": "2026-08-28",
    }
    assert result["timestamp"] == "2026-08-28T09:00:00-04:00"
    assert result["summary"]["limits"] == pytest.approx({
        "cl": 12, "lcl": 8.01063829787234, "ucl": 15.98936170212766,
        "mr_mean": 1.5, "sigma": 1.3297872340425534, "n": 5, "pairs": 4,
    })
    assert result["summary"]["hour"] == 9
    assert [row["bikes"] for row in result["history"]] == [10, 12, 11, 13, 14]
    assert all("T09:00:00" in row["timestamp"] for row in result["history"])
    chart = client.get("/api/charts/history.svg", params=params)
    assert chart.status_code == 200
    assert "Scheduled service date" in chart.text and "CL = 12.00" in chart.text
    assert not api.plt.get_fignums()


def test_same_hour_defaults_and_demo_checkpoint(client):
    result = client.get("/api/analysis", params={"cursor": 377, "hour": 9}).json()
    assert result["start_date"] == "2026-08-24" and result["end_date"] == "2026-09-28"
    assert result["summary"]["planned"] == 26
    result = client.get("/api/analysis", params={"cursor": 377, "hour": 9, "start_date": "2026-09-22"}).json()
    assert [row["bikes"] for row in result["history"]] == [17, 23, 19, 15, 17]
    assert result["summary"]["limits"] == pytest.approx({
        "cl": 18.2, "mr_mean": 4, "sigma": 3.546099290780142,
        "lcl": 7.561702127659572, "ucl": 28.838297872340426, "n": 5, "pairs": 4,
    })


def test_same_hour_missing_date_breaks_pairs_and_future_slot_is_not_missing(client):
    source = upload_csv(client, "timestamp,station_id,bikes\n"
                        "2026-08-24T09:00:00-04:00,S01,10\n"
                        "2026-08-25T09:00:00-04:00,S01,12\n"
                        "2026-08-27T09:00:00-04:00,S01,13\n"
                        "2026-08-28T09:00:00-04:00,S01,14\n")
    result = client.get("/api/analysis", params={"source": source, "cursor": 61, "hour": 9}).json()
    assert [row["bikes"] for row in result["history"]] == [10, 12, None, 13]
    assert result["summary"]["planned"] == 4
    assert result["summary"]["n"] == 3
    assert result["summary"]["pairs"] == 1
    assert result["summary"]["limits"]["mr_mean"] == 2
    assert all(row["timestamp"] < result["timestamp"] for row in result["history"])
    result = client.get("/api/analysis", params={"source": source, "cursor": 62, "hour": 9}).json()
    assert [row["bikes"] for row in result["history"]] == [10, 12, None, 13, 14]
    assert result["summary"]["planned"] == 5 and result["summary"]["pairs"] == 2


@pytest.mark.parametrize("params,message", [
    ({"hour": 6}, "operating hour"),
    ({"hour": 24}, None),
    ({"hour": 8.5}, None),
    ({"hour": 9, "start_date": "2026-08-30", "end_date": "2026-08-28"}, "start_date"),
    ({"hour": 9, "end_date": "2026-09-29"}, "playback date"),
    ({"hour": 9, "start_date": "2026-08-32"}, "ISO date"),
    ({"hour": 9, "start_date": "2026-08-24T09:00:00"}, "ISO date"),
    ({"start_date": "2026-08-24"}, "Select an hour"),
])
@pytest.mark.parametrize("path", ["/api/analysis", "/api/charts/history.svg"])
def test_same_hour_invalid_queries_are_client_errors(client, params, message, path):
    response = client.get(path, params={"cursor": 377, **params})
    assert response.status_code == 422
    if message:
        assert message in response.json()["detail"]


def test_same_hour_empty_future_selection_renders_without_counting_future_data(client):
    params = {"cursor": 0, "hour": 9}
    response = client.get("/api/analysis", params=params)
    assert response.status_code == 200
    result = response.json()
    assert result["history"] == []
    assert result["summary"]["planned"] == result["summary"]["n"] == 0
    assert result["summary"]["cl"] is None and result["summary"]["limits"] is None
    assert "No elapsed" in result["summary"]["reason"]
    chart = client.get("/api/charts/history.svg", params=params)
    assert chart.status_code == 200 and "<svg" in chart.text
    assert not api.plt.get_fignums()


def diagnosis_params(**overrides):
    return {"cursor": len(api.PLAN) - 1, "hour": 7, "diagnosis": True,
            "start_date": api.SETTINGS["service_dates"][0],
            "end_date": api.SETTINGS["service_dates"][-1], **overrides}


@pytest.mark.parametrize("params", [{}, {"cursor": 377, "hour": 7}, {"cursor": 599, "hour": 7, "diagnosis": False}])
def test_diagnosis_is_opt_in_and_default_requests_never_call_detector(client, monkeypatch, params):
    def unexpected_detection(*args):
        raise AssertionError("Disabled diagnosis must not run the detector.")

    monkeypatch.setattr(api, "detect_special_causes", unexpected_detection)
    response = client.get("/api/analysis", params=params)
    assert response.status_code == 200
    assert response.json()["summary"]["special_causes"] == {
        "status": "disabled", "ruleset": "course-eight-tests-v1", "rule_status": {}, "events": [], "issues": [],
    }


@pytest.mark.parametrize("overrides", [
    {"start_date": "2026-08-25"},
    {"end_date": "2026-10-15"},
    {"start_date": "2026-08-23"},
    {"cursor": 585, "hour": 9},
    {"cursor": 598, "hour": 21},
])
def test_diagnosis_rejects_partial_calendar_or_same_day_hour_cutoff(client, overrides):
    response = client.get("/api/analysis", params=diagnosis_params(**overrides))
    assert response.status_code == 422
    assert "full service-date range" in response.json()["detail"]


def test_diagnosis_rejects_legacy_history_and_earlier_playback_date(client):
    response = client.get("/api/analysis", params={"cursor": 599, "diagnosis": True})
    assert response.status_code == 422
    assert "selected operating hour" in response.json()["detail"]
    response = client.get("/api/analysis", params=diagnosis_params(cursor=377))
    assert response.status_code == 422
    assert "playback date" in response.json()["detail"]


def test_diagnosis_accepts_complete_selected_hour_before_final_daily_hour(client):
    response = client.get("/api/analysis", params=diagnosis_params(cursor=585))
    assert response.status_code == 200
    result = response.json()
    assert result["summary"]["planned"] == 40
    assert result["history"][-1]["timestamp"] == "2026-10-16T07:00:00-04:00"
    assert result["summary"]["special_causes"]["status"] == "enabled"
    assert set(result["summary"]["special_causes"]["rule_status"]) == {f"T{i}" for i in range(1, 9)}


def test_diagnosis_uses_full_station_hour_estimates_and_qualifying_contributors_only(client):
    days = api.SETTINGS["service_dates"]
    source = upload_csv(client, "timestamp,station_id,bikes\n" + "".join(
        f"{day}T07:00:00-04:00,S01,{bikes}\n"
        f"{day}T08:00:00-04:00,S01,15\n"
        f"{day}T07:00:00-04:00,S02,10\n"
        for day, bikes in zip(days, [17, 18] + [15] * 38)
    ))
    params = diagnosis_params(source=source)
    result = client.get("/api/analysis", params=params).json()
    assert result["summary"]["cl"] == 15.125
    assert result["summary"]["limits"]["sigma"] == pytest.approx((4 / 39) / 1.128)
    causes = result["summary"]["special_causes"]
    t2 = [event for event in causes["events"] if event["rule"] == "T2"]
    assert t2 == [{"rule": "T2", "start_index": 0, "end_index": 2, "trigger_index": 2,
                   "contributing_indices": [0, 1], "direction": "above"}]
    issue = next(issue for issue in causes["issues"] if issue["id"] == "T2")
    assert issue["point_indices"] == [0, 1] and issue["event_count"] == 1
    assert issue["title"] and issue["description"]
    for selection in ({"hour": 8}, {"station_id": "S02"}):
        isolated = client.get("/api/analysis", params={**params, **selection}).json()
        assert isolated["summary"]["special_causes"]["issues"] == []
        assert isolated["summary"]["special_causes"]["events"] == []
    assert client.get("/api/analysis", params=params).json() == result
    normal = client.get("/api/analysis", params=diagnosis_params()).json()
    assert normal["history"] != result["history"]
    assert normal["summary"]["special_causes"] != causes
    undiagnosed = client.get("/api/analysis", params={**params, "diagnosis": False}).json()
    assert undiagnosed["history"] == result["history"]
    assert undiagnosed["summary"]["limits"] == result["summary"]["limits"]


def test_diagnosis_missing_upload_slots_break_windows_without_disabling_full_range(client):
    counts = [17, 18, None] + [15] * 37
    source = upload_csv(client, "timestamp,station_id,bikes\n" + "".join(
        f"{day}T07:00:00-04:00,S01,{bikes}\n"
        for day, bikes in zip(api.SETTINGS["service_dates"], counts) if bikes is not None
    ))
    response = client.get("/api/analysis", params=diagnosis_params(source=source))
    assert response.status_code == 200
    result = response.json()
    assert [row["bikes"] for row in result["history"]] == counts
    assert result["summary"]["n"] == 39 and result["summary"]["planned"] == 40
    causes = result["summary"]["special_causes"]
    assert causes["status"] == "enabled"
    assert all(not event["start_index"] <= 2 <= event["end_index"] for event in causes["events"])
    assert all(2 not in issue["point_indices"] for issue in causes["issues"])
    assert causes["rule_status"]["T2"]["evaluated_windows"] == 35


def test_diagnosis_constant_and_empty_uploads_report_unavailable_estimates(client):
    content = "timestamp,station_id,bikes\n" + "".join(
        f"{day}T07:00:00-04:00,S01,15\n" for day in api.SETTINGS["service_dates"]
    )
    source = upload_csv(client, content)
    result = client.get("/api/analysis", params=diagnosis_params(source=source)).json()
    assert result["summary"]["cl"] == 15 and result["summary"]["limits"] is None
    causes = result["summary"]["special_causes"]
    assert causes["events"] == causes["issues"] == []
    for rule in ("T1", "T2", "T3", "T6", "T7"):
        assert causes["rule_status"][rule]["status"] == "unavailable"
        assert "sigma" in causes["rule_status"][rule]["reason"]
    for rule in ("T4", "T5", "T8"):
        assert causes["rule_status"][rule]["status"] == "not_detected"
    empty_source = upload_csv(client, "timestamp,station_id,bikes\n")
    empty = client.get("/api/analysis", params=diagnosis_params(source=empty_source)).json()
    assert empty["summary"]["special_causes"]["status"] == "enabled"
    assert all(rule["status"] == "unavailable" for rule in empty["summary"]["special_causes"]["rule_status"].values())


def test_diagnosis_parameter_is_only_on_json_analysis_endpoint(client):
    paths = client.get("/api/openapi.json").json()["paths"]
    analysis_parameters = {parameter["name"] for parameter in paths["/api/analysis"]["get"]["parameters"]}
    svg_parameters = {parameter["name"] for parameter in paths["/api/charts/{chart}.svg"]["get"]["parameters"]}
    assert "diagnosis" in analysis_parameters
    assert "diagnosis" not in svg_parameters
