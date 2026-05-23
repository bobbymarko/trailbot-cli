"""Unit tests for trailbot.client — all HTTP calls are mocked."""

import json
import time
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name):
    return json.loads((FIXTURES / name).read_text())


def _mock_response(data: dict, status=200):
    body = json.dumps(data).encode()
    mock = MagicMock()
    mock.read.return_value = body
    mock.status = status
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    return mock


HTML_WITH_BUILD_ID = b'<script id="__NEXT_DATA__" type="application/json">{"buildId":"TEST_BUILD_ID"}</script>'


class TestHaversine(unittest.TestCase):
    def test_same_point(self):
        from trailbot.client import _haversine_miles
        self.assertAlmostEqual(_haversine_miles(44.0, -93.0, 44.0, -93.0), 0.0, places=5)

    def test_known_distance(self):
        # Chanhassen MN to Detroit Lakes MN (~190 miles)
        from trailbot.client import _haversine_miles
        dist = _haversine_miles(44.856, -93.530, 46.814, -95.787)
        self.assertGreater(dist, 170)
        self.assertLess(dist, 210)

    def test_symmetry(self):
        from trailbot.client import _haversine_miles
        d1 = _haversine_miles(44.0, -93.0, 45.0, -94.0)
        d2 = _haversine_miles(45.0, -94.0, 44.0, -93.0)
        self.assertAlmostEqual(d1, d2, places=5)


class TestGetBuildId(unittest.TestCase):
    def setUp(self):
        # Patch cache file to a temp path so tests don't interfere with real cache
        self._cache_patcher = patch("trailbot.client.BUILD_ID_CACHE")
        self.mock_cache = self._cache_patcher.start()
        self.mock_cache.exists.return_value = False

    def tearDown(self):
        self._cache_patcher.stop()

    def test_extracts_build_id_from_html(self):
        from trailbot.client import _get_build_id
        mock_resp = MagicMock()
        mock_resp.read.return_value = HTML_WITH_BUILD_ID
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        self.mock_cache.write_text = MagicMock()

        with patch("urllib.request.urlopen", return_value=mock_resp):
            build_id = _get_build_id()

        self.assertEqual(build_id, "TEST_BUILD_ID")

    def test_returns_cached_build_id(self):
        from trailbot.client import _get_build_id
        self.mock_cache.exists.return_value = True
        self.mock_cache.read_text.return_value = json.dumps({
            "buildId": "CACHED_ID",
            "ts": time.time(),
        })

        with patch("urllib.request.urlopen") as mock_url:
            build_id = _get_build_id()
            mock_url.assert_not_called()

        self.assertEqual(build_id, "CACHED_ID")

    def test_refreshes_stale_cache(self):
        from trailbot.client import _get_build_id
        self.mock_cache.exists.return_value = True
        self.mock_cache.read_text.return_value = json.dumps({
            "buildId": "OLD_ID",
            "ts": time.time() - 9999,  # expired
        })
        self.mock_cache.write_text = MagicMock()

        mock_resp = MagicMock()
        mock_resp.read.return_value = HTML_WITH_BUILD_ID
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            build_id = _get_build_id()

        self.assertEqual(build_id, "TEST_BUILD_ID")

    def test_raises_if_no_build_id_in_html(self):
        from trailbot.client import _get_build_id
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"<html>no build id here</html>"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        self.mock_cache.write_text = MagicMock()

        with patch("urllib.request.urlopen", return_value=mock_resp):
            with self.assertRaises(RuntimeError):
                _get_build_id()


class TestFindTrail(unittest.TestCase):
    def _directory(self):
        return _load("trail_directory.json")["pageProps"]["trails"]

    def test_exact_slug_match(self):
        from trailbot.client import find_trail
        with patch("trailbot.client.get_directory", return_value=self._directory()):
            result = find_trail("air-capital-memorial-park-singletrack")
        self.assertIsNotNone(result)
        self.assertEqual(result["slug"], "air-capital-memorial-park-singletrack")

    def test_fuzzy_name_match(self):
        from trailbot.client import find_trail
        with patch("trailbot.client.get_directory", return_value=self._directory()):
            result = find_trail("alpine")
        self.assertIsNotNone(result)
        self.assertIn("alpine", result["trailName"].lower())

    def test_returns_none_for_unknown(self):
        from trailbot.client import find_trail
        with patch("trailbot.client.get_directory", return_value=self._directory()):
            result = find_trail("zzznotarealtrailzzz")
        self.assertIsNone(result)


class TestSearchTrails(unittest.TestCase):
    def _directory(self):
        return _load("trail_directory.json")["pageProps"]["trails"]

    def test_search_by_name(self):
        from trailbot.client import search_trails
        with patch("trailbot.client.get_directory", return_value=self._directory()):
            results = search_trails("alpine")
        self.assertTrue(any("alpine" in t["trailName"].lower() for t in results))

    def test_state_filter(self):
        from trailbot.client import search_trails
        with patch("trailbot.client.get_directory", return_value=self._directory()):
            results = search_trails("a", state="IL")
        self.assertTrue(all(t["state"] == "IL" for t in results))

    def test_empty_query_with_state(self):
        from trailbot.client import search_trails
        with patch("trailbot.client.get_directory", return_value=self._directory()):
            results = search_trails("", state="KS")
        # KS trails should appear but not IL ones
        states = {t["state"] for t in results}
        self.assertNotIn("IL", states)


class TestTrailsNear(unittest.TestCase):
    def _cached_trails(self):
        return _load("org_trails.json")["pageProps"]["trails"]

    def test_returns_trails_within_radius(self):
        from trailbot.client import trails_near
        with patch("trailbot.client.get_cached_trails", return_value=self._cached_trails()):
            # Battle Creek is in St Paul (~25mi from Chanhassen)
            results = trails_near(44.856, -93.530, radius_miles=50)
        self.assertTrue(len(results) > 0)
        self.assertTrue(all(t["_dist_miles"] <= 50 for t in results))

    def test_excludes_trails_beyond_radius(self):
        from trailbot.client import trails_near
        with patch("trailbot.client.get_cached_trails", return_value=self._cached_trails()):
            results = trails_near(44.856, -93.530, radius_miles=1)
        self.assertEqual(len(results), 0)

    def test_results_sorted_by_distance(self):
        from trailbot.client import trails_near
        with patch("trailbot.client.get_cached_trails", return_value=self._cached_trails()):
            results = trails_near(44.856, -93.530, radius_miles=200)
        dists = [t["_dist_miles"] for t in results]
        self.assertEqual(dists, sorted(dists))

    def test_state_filter(self):
        from trailbot.client import trails_near
        with patch("trailbot.client.get_cached_trails", return_value=self._cached_trails()):
            results = trails_near(44.856, -93.530, radius_miles=200, state="WI")
        self.assertTrue(all(t["state"] == "WI" for t in results))


class TestOpenTrails(unittest.TestCase):
    def _make_trails(self):
        return [
            {"trailName": "Open One", "state": "MN", "trailStatus": "Open"},
            {"trailName": "Closed One", "state": "MN", "trailStatus": "Closed"},
            {"trailName": "Open Two", "state": "WI", "trailStatus": "Open"},
        ]

    def test_returns_only_open(self):
        from trailbot.client import open_trails
        with patch("trailbot.client.get_cached_trails", return_value=self._make_trails()):
            results = open_trails()
        self.assertTrue(all(t["trailStatus"] == "Open" for t in results))
        self.assertEqual(len(results), 2)

    def test_state_filter(self):
        from trailbot.client import open_trails
        with patch("trailbot.client.get_cached_trails", return_value=self._make_trails()):
            results = open_trails(state="MN")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["trailName"], "Open One")


if __name__ == "__main__":
    unittest.main()
