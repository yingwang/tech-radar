import itertools
import unittest
from unittest import mock

import fetch_radar


class DigestSafetyTests(unittest.TestCase):
    def test_digest_escapes_external_html_and_rejects_non_http_links(self):
        story = {
            "id": 1,
            "title": "&lt;script&gt;alert(1)&lt;/script&gt;",
            "text": "&lt;img src=x onerror=alert(2)&gt;",
            "url": "javascript:alert(3)",
            "score": 1,
            "descendants": 0,
        }
        repo = {
            "path": "owner/repo",
            "desc": "<img src=x onerror=alert(4)>",
            "stars_today": "1",
        }

        with mock.patch.object(fetch_radar, "fetch_hn", return_value=[story]), mock.patch.object(
            fetch_radar, "fetch_github_trending", return_value=[repo]
        ):
            digest = fetch_radar.build_digest("2026-07-10")

        self.assertNotIn("<script>", digest)
        self.assertNotIn("<img ", digest)
        self.assertIn("&lt;script&gt;alert\\(1\\)&lt;/script&gt;", digest)
        self.assertIn("https://news.ycombinator.com/item?id=1", digest)
        self.assertNotIn("javascript:alert", digest)


class HackerNewsTimeoutTests(unittest.TestCase):
    def test_fetch_hn_stops_when_its_total_time_budget_is_exhausted(self):
        calls = []

        def get_json(url, timeout):
            calls.append((url, timeout))
            if url == fetch_radar.HN_TOP:
                return [1, 2, 3]
            raise TimeoutError("timed out")

        clock = itertools.count(start=0, step=0.6)
        with mock.patch.object(fetch_radar, "get_json", side_effect=get_json), mock.patch.object(
            fetch_radar, "HN_FETCH_BUDGET", 1
        ), mock.patch.object(fetch_radar.time, "monotonic", side_effect=lambda: next(clock)):
            with self.assertRaisesRegex(RuntimeError, "未能在时间预算内"):
                fetch_radar.fetch_hn()

        item_calls = [url for url, _ in calls if url != fetch_radar.HN_TOP]
        self.assertEqual(len(item_calls), 1)


if __name__ == "__main__":
    unittest.main()
