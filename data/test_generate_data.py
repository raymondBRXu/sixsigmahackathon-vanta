"""Independent acceptance checks for the synthetic data, using only the stdlib."""

import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("generate_data.py")
SCENARIOS = ("normal", "disruption", "edge_cases")


class GeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.output = Path(cls.temp.name) / "all"
        cls.run_generator("--output-dir", str(cls.output))
        cls.settings = json.loads((cls.output / "settings.json").read_text())
        cls.rows = {}
        for scenario in SCENARIOS:
            with (cls.output / (scenario + ".csv")).open(newline="") as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames != ["timestamp", "station_id", "bikes"]:
                    raise AssertionError(reader.fieldnames)
                cls.rows[scenario] = list(reader)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def run_generator(cls, *arguments, expect_success=True):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *arguments], capture_output=True, text=True
        )
        if expect_success and result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        if not expect_success and result.returncode == 0:
            raise AssertionError("Expected a configuration error")
        return result

    def test_calendar_and_station_configuration(self):
        dates = self.settings["service_dates"]
        self.assertEqual((len(dates), dates[0], dates[-1]), (40, "2026-08-24", "2026-10-16"))
        self.assertTrue(all(datetime.fromisoformat(day).weekday() < 5 for day in dates))
        self.assertEqual(self.settings["baseline_dates"], dates[:25])
        self.assertEqual(self.settings["monitoring_dates"], dates[25:])
        self.assertEqual(self.settings["hours"], list(range(7, 22)))
        self.assertEqual(self.settings["timezone"], "America/New_York")
        stations = json.loads((self.output / "stations.json").read_text())
        self.assertEqual(len(stations), 20)
        self.assertEqual(len({station["station_id"] for station in stations}), 20)
        self.assertGreaterEqual(sum(station["area"].startswith("Cornell") for station in stations), 12)
        self.assertEqual(sum(station["type"] == "academic" for station in stations), 6)
        self.assertTrue(all(station["capacity"] == 30 for station in stations))
        for station in stations:
            self.assertEqual(set(station), {"station_id", "name", "area", "type", "latitude", "longitude", "capacity"})
            self.assertTrue(42.3 < station["latitude"] < 42.6)
            self.assertTrue(-76.6 < station["longitude"] < -76.3)

    def test_complete_conserved_bounded_snapshots(self):
        expected_ids = {"S%02d" % number for number in range(1, 21)}
        for scenario, rows in self.rows.items():
            with self.subTest(scenario=scenario):
                self.assertEqual(len(rows), 12000)
                snapshots = defaultdict(dict)
                previous = None
                for row in rows:
                    instant = datetime.fromisoformat(row["timestamp"])
                    self.assertIsNotNone(instant.utcoffset())
                    self.assertEqual(instant.utcoffset().total_seconds(), -4 * 3600)
                    self.assertEqual((instant.minute, instant.second), (0, 0))
                    self.assertIn(instant.date().isoformat(), self.settings["service_dates"])
                    self.assertIn(instant.hour, range(7, 22))
                    count = int(row["bikes"])
                    self.assertEqual(str(count), row["bikes"])
                    self.assertTrue(0 <= count <= 30)
                    station = row["station_id"]
                    self.assertNotIn(station, snapshots[instant])
                    snapshots[instant][station] = count
                    key = (instant, station)
                    if previous is not None:
                        self.assertGreater(key, previous)
                    previous = key
                self.assertEqual(len(snapshots), 600)
                for instant, snapshot in snapshots.items():
                    self.assertEqual(set(snapshot), expected_ids)
                    self.assertEqual(sum(snapshot.values()), 300)
                    if instant.hour == 7 and instant.date().isoformat() == self.settings["service_dates"][0]:
                        self.assertEqual(set(snapshot.values()), {15})

    def test_inventory_carries_across_all_service_dates_including_weekends(self):
        days = self.settings["service_dates"]
        for scenario, rows in self.rows.items():
            with self.subTest(scenario=scenario):
                snapshots = defaultdict(dict)
                for row in rows:
                    instant = datetime.fromisoformat(row["timestamp"])
                    snapshots[(instant.date().isoformat(), instant.hour)][row["station_id"]] = int(row["bikes"])
                weekend_transitions = 0
                for previous, following in zip(days, days[1:]):
                    self.assertEqual(snapshots[(previous, 21)], snapshots[(following, 7)])
                    if (datetime.fromisoformat(following) - datetime.fromisoformat(previous)).days == 3:
                        weekend_transitions += 1
                self.assertEqual(weekend_transitions, 7)
                self.assertTrue(any(set(snapshots[(day, 7)].values()) != {15} for day in days[1:]))

    def test_shared_baseline_and_changed_monitoring(self):
        self.assertEqual(self.rows["normal"][:7500], self.rows["disruption"][:7500])
        self.assertNotEqual(self.rows["normal"][7500:], self.rows["disruption"][7500:])
        self.assertEqual(len(self.rows["normal"][7500:]), 4500)

    def test_edge_examples_and_constant_later_hour(self):
        values = {(row["timestamp"], row["station_id"]): int(row["bikes"]) for row in self.rows["edge_cases"]}
        day = self.settings["monitoring_dates"][0]
        balanced = [values[(day + "T09:00:00-04:00", "S%02d" % number)] for number in range(1, 21)]
        polarized = [values[(day + "T10:00:00-04:00", "S%02d" % number)] for number in range(1, 21)]
        self.assertEqual(balanced, [15] * 20)
        self.assertEqual(polarized, [0] * 10 + [30] * 10)
        thresholds = [values[(day + "T11:00:00-04:00", "S%02d" % number)] for number in range(1, 7)]
        self.assertEqual(thresholds, [6, 24, 5, 25, 0, 30])
        later_hour = [values[(day + "T12:00:00-04:00", "S20")] for day in self.settings["baseline_dates"]]
        self.assertEqual(later_hour, [15] * 25)

    def test_separate_runs_match_all_byte_for_byte(self):
        output = Path(self.temp.name) / "separate"
        for scenario in reversed(SCENARIOS):
            self.run_generator("--scenario", scenario, "--output-dir", str(output))
        for filename in [name + ".csv" for name in SCENARIOS] + ["stations.json", "settings.json", "generation_metadata.json"]:
            self.assertEqual((output / filename).read_bytes(), (self.output / filename).read_bytes(), filename)

    def test_repeated_run_is_identical(self):
        before = {path.name: path.read_bytes() for path in self.output.iterdir()}
        self.run_generator("--output-dir", str(self.output))
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.output.iterdir()})

    def test_prevent_mixed_configuration(self):
        output = Path(self.temp.name) / "guard"
        self.run_generator("--scenario", "normal", "--output-dir", str(output))
        result = self.run_generator("--scenario", "disruption", "--seed", "10", "--output-dir", str(output), expect_success=False)
        self.assertIn("different configuration", result.stderr)
        self.assertFalse((output / "disruption.csv").exists())
        self.run_generator("--seed", "10", "--output-dir", str(output))
        self.assertNotEqual((output / "normal.csv").read_bytes(), (self.output / "normal.csv").read_bytes())

    def test_changed_station_anchors_cannot_mix_with_existing_csvs(self):
        output = Path(self.temp.name) / "anchor_guard"
        self.run_generator("--output-dir", str(output))
        altered = Path(self.temp.name) / "altered_generator"
        altered.mkdir()
        (altered / SCRIPT.name).write_bytes(SCRIPT.read_bytes())
        anchors = json.loads(SCRIPT.with_name("station_anchors.json").read_text())
        anchors[0]["latitude"] += 0.001
        (altered / "station_anchors.json").write_text(json.dumps(anchors))
        result = subprocess.run(
            [sys.executable, str(altered / SCRIPT.name), "--scenario", "normal", "--output-dir", str(output)],
            capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("different configuration", result.stderr)

    def test_invalid_start_date_is_clear_error(self):
        result = self.run_generator("--start-date", "2026-08-23", "--output-dir", str(Path(self.temp.name) / "bad"), expect_success=False)
        self.assertIn("weekday", result.stderr)

    def test_alternate_calendar_handles_daylight_saving_change(self):
        output = Path(self.temp.name) / "dst"
        self.run_generator("--scenario", "normal", "--start-date", "2026-10-26", "--output-dir", str(output))
        with (output / "normal.csv").open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(rows[0]["timestamp"], "2026-10-26T07:00:00-04:00")
        self.assertEqual(rows[5 * 300]["timestamp"], "2026-11-02T07:00:00-05:00")
        self.assertEqual(len(rows), 12000)

    def test_modified_sibling_is_not_silently_mixed(self):
        output = Path(self.temp.name) / "modified"
        self.run_generator("--scenario", "normal", "--output-dir", str(output))
        with (output / "normal.csv").open("a") as handle:
            handle.write("modified\n")
        result = self.run_generator("--scenario", "edge_cases", "--output-dir", str(output), expect_success=False)
        self.assertIn("recorded hash", result.stderr)
        self.assertFalse((output / "edge_cases.csv").exists())

    def test_settings_exclude_generation_only_labels(self):
        self.assertEqual(set(self.settings), {"schema_version", "timezone", "service_dates", "baseline_dates", "monitoring_dates", "hours", "station_ids", "collection_mode"})
        metadata = json.loads((self.output / "generation_metadata.json").read_text())
        self.assertTrue(metadata["synthetic"])
        self.assertEqual(metadata["configuration"]["seed"], 5300)
        self.assertTrue(metadata["edge_fixtures"])
        self.assertEqual(metadata["configuration"]["generator_version"], 3)

    def test_student_flow_audit(self):
        metadata = json.loads((self.output / "generation_metadata.json").read_text())
        audits = metadata["transfer_audit"]
        self.assertEqual(audits["normal"]["baseline"], audits["disruption"]["baseline"])
        phases = {"background", "morning_to_class", "midday_exchange", "afternoon_return", "evening_return"}
        for scenario in SCENARIOS:
            for phase in ("baseline", "monitoring"):
                self.assertEqual(set(audits[scenario][phase]), phases)
                for result in audits[scenario][phase].values():
                    self.assertGreaterEqual(result["successful_transfers"], 0)
                    self.assertLessEqual(result["successful_transfers"], result["planned_transfers"])
        normal = audits["normal"]["monitoring"]["morning_to_class"]["planned_transfers"]
        abnormal = audits["disruption"]["monitoring"]["morning_to_class"]["planned_transfers"]
        self.assertGreater(abnormal, normal)


if __name__ == "__main__":
    unittest.main(verbosity=2)
