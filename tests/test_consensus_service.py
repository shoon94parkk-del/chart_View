import unittest

from consensus_service import _parse_root


class ConsensusParsingTests(unittest.TestCase):
    def test_parse_eps_revenue_and_revisions(self):
        root = {
            "price": {"shortName": "Example", "currency": "USD"},
            "earningsTrend": {
                "trend": [
                    {
                        "period": "0y",
                        "endDate": "2026-12-31",
                        "earningsEstimate": {
                            "avg": {"raw": 10.5}, "low": {"raw": 9.0}, "high": {"raw": 12.0},
                            "numberOfAnalysts": {"raw": 20},
                        },
                        "epsTrend": {
                            "current": {"raw": 10.5}, "7daysAgo": {"raw": 10.4},
                            "30daysAgo": {"raw": 10.0}, "60daysAgo": {"raw": 9.8},
                            "90daysAgo": {"raw": 9.5},
                        },
                        "epsRevisions": {
                            "upLast7days": {"raw": 3}, "upLast30days": {"raw": 8},
                            "downLast7days": {"raw": 1}, "downLast30days": {"raw": 2},
                        },
                        "revenueEstimate": {
                            "avg": {"raw": 100_000_000_000}, "low": {"raw": 95_000_000_000},
                            "high": {"raw": 110_000_000_000}, "numberOfAnalysts": {"raw": 18},
                            "growth": {"raw": 0.25},
                        },
                    }
                ]
            },
        }
        parsed = _parse_root("EXM", root)
        row = parsed["periods"]["0y"]
        self.assertEqual(parsed["name"], "Example")
        self.assertEqual(parsed["currency"], "USD")
        self.assertEqual(row["earnings"]["avg"], 10.5)
        self.assertEqual(row["epsTrend"]["90daysAgo"], 9.5)
        self.assertEqual(row["revisions"]["up30"], 8.0)
        self.assertEqual(row["revenue"]["avg"], 100_000_000_000.0)
        self.assertEqual(row["revenue"]["growth"], 0.25)

    def test_ignores_unneeded_periods_and_keeps_nulls(self):
        root = {
            "price": {"shortName": "Example"},
            "earningsTrend": {"trend": [
                {"period": "+5y", "earningsEstimate": {"avg": {"raw": 1}}},
                {"period": "+1y", "endDate": "2027-12-31", "earningsEstimate": {}, "revenueEstimate": {}},
            ]},
        }
        parsed = _parse_root("EXM", root)
        self.assertNotIn("+5y", parsed["periods"])
        self.assertIsNone(parsed["periods"]["+1y"]["earnings"]["avg"])
        self.assertIsNone(parsed["periods"]["+1y"]["revenue"]["avg"])


if __name__ == "__main__":
    unittest.main()
