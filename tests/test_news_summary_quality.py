import unittest
from unittest.mock import patch

import news_summary_service as svc


class NewsSummaryQualityTests(unittest.TestCase):
    def test_promotional_sentence_is_removed(self):
        text = "Nvidia reported revenue growth of 20%. Subscribe now for a limited time deal."
        cleaned = svc._strip_promotional_text(text)
        self.assertIn("revenue growth", cleaned)
        self.assertNotIn("Subscribe", cleaned)

    def test_low_information_summary_is_blocked_or_falls_back(self):
        summary, status = svc._finalize_summary("좋은 소식입니다.", "Nvidia earnings", "Nvidia revenue rose 20% year over year.")
        self.assertNotEqual(summary, "좋은 소식입니다.")
        self.assertNotEqual(status, "ok")

    def test_concrete_korean_summary_passes(self):
        text = "삼성전자 매출은 전년 대비 18% 증가했습니다."
        summary, status = svc._finalize_summary(text, "삼성전자 실적 발표", text)
        self.assertEqual(summary, text)
        self.assertEqual(status, "ok")

    def test_build_summary_exposes_quality_status(self):
        with patch.object(svc, "_disk_cache_get", return_value=None), \
             patch.object(svc, "_safe_fetch_html", side_effect=RuntimeError("blocked")), \
             patch.object(svc, "_translate_ko", return_value=("엔비디아 매출은 전년 대비 20% 증가했습니다.", True)), \
             patch.object(svc, "_disk_cache_put"):
            svc.SUMMARY_CACHE.clear()
            payload = svc._build_summary("https://example.com/story", "Nvidia revenue rises", "Nvidia revenue rose 20% year over year as data-center demand increased.")
        self.assertIn("qualityStatus", payload)
        self.assertTrue(payload["summary"])


if __name__ == "__main__":
    unittest.main()
