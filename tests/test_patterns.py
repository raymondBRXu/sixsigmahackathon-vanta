"""Hand-planted patterns, exact boundaries and missing-data cases for all rules."""

import math

import pytest

from dockwatch.patterns import RULES, detect_special_causes


def events_for(values, rule, centerline=0, sigma=1):
    return [event for event in detect_special_causes(values, centerline, sigma)["events"] if event["rule"] == rule]


@pytest.mark.parametrize("rule,values,contributors,direction", [
    ("T1", [3.1], [0], "above"),
    ("T1", [-3.1], [0], "below"),
    ("T2", [2.1, 2.2, 0], [0, 1], "above"),
    ("T2", [-2.1, 0, -2.2], [0, 2], "below"),
    ("T3", [1.1, 1.2, 0, 1.3, 1.4], [0, 1, 3, 4], "above"),
    ("T3", [-1.1, -1.2, -1.3, -1.4, 0], [0, 1, 2, 3], "below"),
    ("T4", [0.5] * 8, list(range(8)), "above"),
    ("T4", [-0.5] * 8, list(range(8)), "below"),
    ("T5", [-2, -1, 0, 1, 2, 3], list(range(6)), "increasing"),
    ("T5", [3, 2, 1, 0, -1, -2], list(range(6)), "decreasing"),
    ("T6", [1] * 15, list(range(15)), "within"),
    ("T6", [-1, 1] * 7 + [0], list(range(15)), "within"),
    ("T7", [1.1] * 7 + [-1.1], list(range(8)), "both"),
    ("T8", [0, 1] * 7, list(range(14)), "alternating"),
    ("T8", [1, 0] * 7, list(range(14)), "alternating"),
])
def test_each_rule_has_a_known_positive_with_exact_contributors(rule, values, contributors, direction):
    events = events_for(values, rule)
    assert events == [{"rule": rule, "start_index": 0, "end_index": len(values) - 1,
                       "trigger_index": len(values) - 1, "contributing_indices": contributors,
                       "direction": direction}]


@pytest.mark.parametrize("rule,values", [
    ("T1", [3, -3, 0]),
    ("T2", [2, 2.1, 0]),
    ("T2", [2.1, -2.1, 0]),
    ("T3", [1, 1.1, 1.2, 1.3, 0]),
    ("T3", [1.1, 1.2, -1.1, -1.2, 0]),
    ("T4", [1] * 7 + [0]),
    ("T4", [1] * 7 + [-1]),
    ("T5", [1, 2, 3, 3, 4, 5]),
    ("T5", [1, 2, 3, 2, 4, 5]),
    ("T6", [0] * 14 + [1.01]),
    ("T7", [1.1] * 8),
    ("T7", [1.1] * 6 + [1, -1.1]),
    ("T8", [0, 1] * 6 + [0, 0]),
    ("T8", [0, 1] * 6 + [2, 3]),
])
def test_rule_boundaries_opposite_sides_ties_and_broken_sequences_do_not_match(rule, values):
    result = detect_special_causes(values, 0, 1)
    assert not events_for(values, rule)
    assert result["rule_status"][rule]["status"] == "not_detected"


@pytest.mark.parametrize("rule,values", [
    ("T1", [3.1]), ("T2", [2.1, 2.2, 0]), ("T3", [1.1] * 5),
    ("T4", [1] * 8), ("T5", list(range(6))), ("T6", [0] * 15),
    ("T7", [1.1, -1.1] * 4), ("T8", [0, 1] * 7),
])
def test_missing_scheduled_reading_interrupts_every_rule(rule, values):
    values[len(values) // 2] = None
    result = detect_special_causes(values, 0, 1)
    assert not events_for(values, rule)
    assert result["rule_status"][rule] == {
        "status": "unavailable", "reason": f"Requires {RULES[rule][0]} consecutive observed reading{'s' if RULES[rule][0] != 1 else ''}.",
        "evaluated_windows": 0,
    }


def test_overlapping_windows_preserve_raw_events_but_issue_indices_are_unique():
    values = [None, 2.1, 2.2, 0, 2.3, 2.4]
    result = detect_special_causes(values, 0, 1)
    matches = [event for event in result["events"] if event["rule"] == "T2"]
    assert [(event["start_index"], event["trigger_index"]) for event in matches] == [(1, 3), (2, 4), (3, 5)]
    assert matches[0]["contributing_indices"] == [1, 2]
    issue = next(issue for issue in result["issues"] if issue["id"] == "T2")
    assert issue["event_count"] == 3
    assert issue["point_indices"] == [1, 2, 4, 5]
    assert result["rule_status"]["T2"]["evaluated_windows"] == 3
    assert result == detect_special_causes(values, 0, 1)
    assert values[0] is None


@pytest.mark.parametrize("values", [[], [None] * 20, [math.nan] * 20])
def test_empty_and_all_missing_series_are_unavailable_not_passed(values):
    result = detect_special_causes(values, None, None)
    assert result["events"] == result["issues"] == []
    assert all(rule["status"] == "unavailable" for rule in result["rule_status"].values())
    assert all(rule["evaluated_windows"] == 0 for rule in result["rule_status"].values())


def test_single_observation_evaluates_only_the_single_point_rule():
    result = detect_special_causes([0], 0, 1)
    assert result["rule_status"]["T1"] == {"status": "not_detected", "reason": None, "evaluated_windows": 1}
    assert all(result["rule_status"][rule]["status"] == "unavailable" for rule in RULES if rule != "T1")


@pytest.mark.parametrize("sigma", [None, 0, -1, math.nan, math.inf])
def test_zero_or_unavailable_variation_never_fabricates_zone_matches(sigma):
    result = detect_special_causes([15] * 20, 15, sigma)
    assert result["events"] == result["issues"] == []
    for rule in ("T1", "T2", "T3", "T6", "T7"):
        assert result["rule_status"][rule]["status"] == "unavailable"
        assert "sigma" in result["rule_status"][rule]["reason"]
    for rule in ("T4", "T5", "T8"):
        assert result["rule_status"][rule]["status"] == "not_detected"


def test_order_rules_do_not_require_estimated_center_or_sigma():
    assert events_for(list(range(6)), "T5", None, None)
    assert events_for([0, 1] * 7, "T8", None, None)
    assert events_for([1] * 8, "T4", 0, None)
    assert not events_for([1] * 8, "T4", None, 1)


@pytest.mark.parametrize("value", [math.inf, -math.inf])
def test_infinite_observations_are_rejected(value):
    with pytest.raises(ValueError, match="finite or missing"):
        detect_special_causes([0, value], 0, 1)
