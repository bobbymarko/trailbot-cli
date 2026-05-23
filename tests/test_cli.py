"""Unit tests for trailbot.cli — client calls are mocked."""

import argparse
import json
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name):
    return json.loads((FIXTURES / name).read_text())


SAMPLE_STATUS = _load("trail_status.json")["pageProps"]["trail"]
SAMPLE_DIRECTORY = _load("trail_directory.json")["pageProps"]["trails"]


class TestCmdStatus(unittest.TestCase):
    def _run(self, trail_arg, trail_dir=None, trail_status=None):
        if trail_dir is None:
            trail_dir = SAMPLE_DIRECTORY[0]
        if trail_status is None:
            trail_status = SAMPLE_STATUS
        args = argparse.Namespace(trail=trail_arg)
        with patch("trailbot.cli.find_trail", return_value=trail_dir), \
             patch("trailbot.cli.get_trail_status", return_value=trail_status), \
             patch("sys.stdout", new_callable=StringIO) as mock_out:
            from trailbot.cli import cmd_status
            cmd_status(args)
            return mock_out.getvalue()

    def test_prints_trail_name(self):
        output = self._run("detroit-mountain")
        self.assertIn(SAMPLE_STATUS["trailName"], output)

    def test_prints_status(self):
        output = self._run("detroit-mountain")
        self.assertIn(SAMPLE_STATUS["trailStatus"], output)

    def test_prints_description(self):
        output = self._run("detroit-mountain")
        desc = (SAMPLE_STATUS.get("description") or "").strip()
        if desc:
            self.assertIn(desc[:30], output)

    def test_exits_on_unknown_trail(self):
        args = argparse.Namespace(trail="zzznope")
        with patch("trailbot.cli.find_trail", return_value=None), \
             self.assertRaises(SystemExit):
            from trailbot.cli import cmd_status
            cmd_status(args)


class TestCmdSearch(unittest.TestCase):
    def _run(self, query, state=None, results=None):
        if results is None:
            results = SAMPLE_DIRECTORY[:3]
        args = argparse.Namespace(query=query, state=state)
        with patch("trailbot.cli.search_trails", return_value=results), \
             patch("sys.stdout", new_callable=StringIO) as mock_out:
            from trailbot.cli import cmd_search
            cmd_search(args)
            return mock_out.getvalue()

    def test_prints_trail_names(self):
        output = self._run("alpine")
        for trail in SAMPLE_DIRECTORY[:3]:
            self.assertIn(trail["trailName"], output)

    def test_no_results_message(self):
        output = self._run("zzznotfound", results=[])
        self.assertIn("No trails found", output)


class TestCmdNear(unittest.TestCase):
    NEARBY = [
        {"trailName": "Close Trail", "city": "Chaska", "state": "MN",
         "trailStatus": "Open", "organization": {"shortName": "CT"}, "_dist_miles": 5.0},
        {"trailName": "Far Trail", "city": "Duluth", "state": "MN",
         "trailStatus": "Closed", "organization": {"shortName": "FT"}, "_dist_miles": 150.0},
    ]

    def _run(self, location="44.856,-93.530", radius=75, state=None, show_all=False, no_sync=True, results=None):
        if results is None:
            results = self.NEARBY
        args = argparse.Namespace(location=location, radius=radius, state=state,
                                  all=show_all, no_sync=no_sync)
        with patch("trailbot.cli.trails_near", return_value=results), \
             patch("sys.stdout", new_callable=StringIO) as mock_out:
            from trailbot.cli import cmd_near
            cmd_near(args)
            return mock_out.getvalue()

    def test_shows_open_by_default(self):
        output = self._run()
        self.assertIn("Close Trail", output)
        self.assertNotIn("Far Trail", output)

    def test_all_flag_shows_closed(self):
        output = self._run(show_all=True)
        self.assertIn("Far Trail", output)

    def test_bad_location_format_exits(self):
        args = argparse.Namespace(location="notacoord", radius=75, state=None,
                                  all=False, no_sync=True)
        with self.assertRaises(SystemExit):
            from trailbot.cli import cmd_near
            cmd_near(args)

    def test_no_results_message(self):
        output = self._run(results=[])
        self.assertIn("No trails", output)


class TestCmdOpen(unittest.TestCase):
    OPEN_TRAILS = [
        {"trailName": "Open Trail", "city": "Minneapolis", "state": "MN",
         "organization": {"shortName": "MORC"}},
    ]

    def _run(self, state=None, results=None):
        if results is None:
            results = self.OPEN_TRAILS
        args = argparse.Namespace(state=state)
        with patch("trailbot.cli.open_trails", return_value=results), \
             patch("sys.stdout", new_callable=StringIO) as mock_out:
            from trailbot.cli import cmd_open
            cmd_open(args)
            return mock_out.getvalue()

    def test_lists_open_trails(self):
        output = self._run()
        self.assertIn("Open Trail", output)
        self.assertIn("🟢", output)

    def test_no_results_message(self):
        output = self._run(results=[])
        self.assertIn("No open trails", output)


class TestIntegration(unittest.TestCase):
    """Live API tests — run with: pytest -m integration"""

    @unittest.skipUnless(
        __import__("os").environ.get("TRAILBOT_INTEGRATION"),
        "set TRAILBOT_INTEGRATION=1 to run"
    )
    def test_detroit_mountain_status(self):
        from trailbot.client import find_trail, get_trail_status
        trail = find_trail("detroit-mountain")
        self.assertIsNotNone(trail)
        status = get_trail_status(trail["organization"]["slug"], trail["slug"])
        self.assertIn("trailStatus", status)
        self.assertIn(status["trailStatus"], ["Open", "Closed", "Caution"])

    @unittest.skipUnless(
        __import__("os").environ.get("TRAILBOT_INTEGRATION"),
        "set TRAILBOT_INTEGRATION=1 to run"
    )
    def test_directory_has_trails(self):
        from trailbot.client import get_directory
        trails = get_directory()
        self.assertGreater(len(trails), 100)


if __name__ == "__main__":
    unittest.main()
