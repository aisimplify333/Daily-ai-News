"""Offline research-recovery contracts: no provider or TTS calls."""
import datetime as dt
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import grounded_news_v1 as news


def story(index, **changes):
    row = dict(headline=f"Distinct AI event {index}", publisher="Reuters",
               source_url=f"https://reuters.com/technology/event-{index}",
               published_at=dt.datetime.now(dt.timezone.utc).isoformat(),
               summary="Confirmed factual description of a newly reported AI development. " * 3,
               facts=["First sourced fact", "Second sourced fact"],
               original_publication_verified=True)
    row.update(changes)
    return row


class RecoveryTests(unittest.TestCase):
    def test_opinion_objection_is_not_actionable_fact_error(self):
        self.assertFalse(news._has_factual_evidence({
            "claim_type": "opinion", "reason": "Host calls the deal a land grab",
            "source_url": "https://example.com/deal", "factual_claim": "land grab",
            "evidence_quote": "Company announces deal"}))

    def test_mixed_opinion_requires_evidence_for_factual_correction(self):
        item = {"claim_type": "factual_assertion", "factual_claim": "Output tokens cost $5",
                "source_url": "https://example.com/pricing", "evidence_quote": "$50 per million output tokens"}
        self.assertTrue(news._has_factual_evidence(item))
        self.assertFalse(news._has_factual_evidence(dict(item, evidence_quote="")))
        self.assertFalse(news._has_factual_evidence(dict(item, source_url="https://example.com/")))

    def test_checker_keeps_opinion_advisory_but_corrects_embedded_false_price(self):
        price = {"claim_type": "factual_assertion", "factual_claim": "$5 output price",
                 "evidence_quote": "$50 per million output tokens",
                 "source_url": "https://example.com/pricing", "reason": "Incorrect price",
                 "exact_line": "JAMIE: I think it is a ripoff at five dollars.",
                 "replacement_line": "JAMIE: I think it is a ripoff at fifty dollars."}
        opinion = {"claim_type": "opinion", "reason": "Ripoff is too opinionated"}
        with patch.dict(os.environ, {"ENABLE_GROUNDED_FACT_AUDIT": "true"}), patch.object(
            news, "_grounded_text", return_value=json.dumps({
                "critical_errors": [opinion, price], "warnings": []})):
            result = news.fact_check_script(price["exact_line"], [], "2026-09-09")
        self.assertEqual(len(result["critical_errors"]), 1)
        self.assertTrue(result["warnings"])
        corrected, count = news.apply_fact_replacements(price["exact_line"], result)
        self.assertEqual(count, 1)
        self.assertIn("ripoff at fifty dollars", corrected)
    def test_second_fact_repair_is_verified_before_decision(self):
        from unittest.mock import Mock
        def defect(old, new):
            return {"pass": False, "critical_errors": [{"exact_line": old, "replacement_line": new}]}
        auditor = Mock(side_effect=[defect("ALEX: Wrong", "ALEX: Better"),
                                   defect("ALEX: Better", "ALEX: Correct"),
                                   {"pass": True, "critical_errors": []}])
        script, audits, count = news.audit_with_repairs(
            "ALEX: Wrong", auditor, lambda value: value, "repaired.txt")
        self.assertEqual(script, "ALEX: Correct")
        self.assertTrue(audits[-1]["pass"])
        self.assertEqual(count, 2)
        self.assertEqual(auditor.call_args.args[0], script)
        with open("repaired.txt") as handle:
            self.assertEqual(handle.read().strip(), script)

    def test_final_fact_pass_cannot_apply_unverified_correction(self):
        from unittest.mock import Mock
        auditor = Mock(side_effect=[
            {"pass": False, "critical_errors": [{"exact_line": f"ALEX: {i}", "replacement_line": f"ALEX: {i+1}"}]}
            for i in range(3)])
        script, audits, count = news.audit_with_repairs("ALEX: 0", auditor, lambda x: x)
        self.assertEqual(script, "ALEX: 2")
        self.assertFalse(audits[-1]["pass"])
        self.assertEqual((auditor.call_count, count), (3, 2))

    def test_clean_fact_audit_has_no_extra_calls(self):
        from unittest.mock import Mock
        auditor = Mock(return_value={"pass": True, "critical_errors": []})
        _, audits, count = news.audit_with_repairs("ALEX: Fine", auditor, lambda x: x)
        self.assertEqual((auditor.call_count, count), (1, 0))

    def test_unmatched_fact_correction_stops_without_false_pass(self):
        from unittest.mock import Mock
        auditor = Mock(return_value={"pass": False, "critical_errors": [
            {"exact_line": "missing", "replacement_line": "replacement"}]})
        script, audits, count = news.audit_with_repairs("ALEX: Original", auditor, lambda x: x)
        self.assertEqual(script, "ALEX: Original")
        self.assertFalse(audits[-1]["pass"])
        self.assertEqual((auditor.call_count, count), (1, 0))

    def setUp(self):
        news.build_grounded_story_slate.cache_clear()
        self.cwd = os.getcwd()
        self.temp = tempfile.TemporaryDirectory()
        os.chdir(self.temp.name)

    def tearDown(self):
        os.chdir(self.cwd)
        self.temp.cleanup()
        news.build_grounded_story_slate.cache_clear()

    def run_slate(self, primary, refill, n=3):
        with patch.object(news, "_grounded_text", return_value=json.dumps({"stories": primary})) as first, patch.object(news, "_recovery_search", return_value=json.dumps({"stories": refill})) as second:
            result = news.build_grounded_story_slate("2026-09-08", n=n)
            return result, first.call_count, second.call_count

    def test_sparse_result_refilled_and_retained(self):
        rows, first, second = self.run_slate([story(1)], [story(2), story(3)])
        self.assertEqual((len(rows), first, second), (3, 1, 1))
        self.assertEqual(rows[0]["headline"], "Distinct AI event 1")

    def test_sufficient_result_has_no_extra_spend(self):
        rows, _, second = self.run_slate([story(i) for i in range(3)], [])
        self.assertEqual(second, 0)

    def test_production_five_story_contract_refills_three(self):
        rows, first, second = self.run_slate(
            [story(i) for i in range(3)], [story(3), story(4)], n=5)
        self.assertEqual((len(rows), first, second), (5, 1, 1))

    def test_production_does_not_return_cached_incomplete_slate(self):
        with patch.object(news, "_grounded_text", return_value=json.dumps({"stories": [story(i) for i in range(3)]})), patch.object(news, "_recovery_search", return_value="{}"):
            with self.assertRaisesRegex(RuntimeError, "at least 5 required"):
                news.build_grounded_story_slate("2026-09-08")
        self.assertEqual(news.build_grounded_story_slate.cache_info().currsize, 0)

    def test_stale_duplicate_and_unverified_rejected(self):
        old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=60)).isoformat()
        rows, _, _ = self.run_slate([story(1), story(8, published_at=old), story(9, original_publication_verified=False)], [story(1), story(2), story(3)])
        self.assertEqual(len(rows), 3)
        with open("grounded_research_report.json") as handle:
            report = json.load(handle)
        self.assertEqual(report["attempts"][0]["rejections"]["outside_freshness_window"], 1)
        self.assertEqual(report["attempts"][1]["rejections"]["duplicate"], 1)

    def test_same_url_different_headline_not_two_stories(self):
        rows, _, second = self.run_slate([story(1), story(2, source_url=story(1)["source_url"])], [story(3), story(4)])
        self.assertEqual((len(rows), second), (3, 1))

    def test_provider_failure_recovers(self):
        with patch.object(news, "_grounded_text", side_effect=RuntimeError("sensitive body")), patch.object(news, "_recovery_search", return_value=json.dumps({"stories": [story(i) for i in range(3)]})):
            self.assertEqual(len(news.build_grounded_story_slate("2026-09-08", n=3)), 3)
        with open("grounded_research_report.json") as handle:
            self.assertNotIn("sensitive body", handle.read())

    def test_exhaustion_stops_before_generation(self):
        with patch.object(news, "_grounded_text", return_value="invalid JSON"), patch.object(news, "_recovery_search", return_value="{}") as second:
            with self.assertRaisesRegex(RuntimeError, "at least 5 required"):
                news.build_grounded_story_slate("2026-09-08")
            self.assertEqual(second.call_count, 1)

    def test_trusted_candidates_not_hidden_by_untrusted(self):
        weak = [story(i, publisher="Unknown", source_url=f"https://example.org/{i}") for i in range(5)]
        rows, _, second = self.run_slate(weak, [story(i) for i in range(5, 8)])
        self.assertEqual(second, 1)
        self.assertTrue(all(row["source_tier"] >= 2 for row in rows[:3]))

    def test_live_stale_pattern_uses_targeted_discovery_recovery(self):
        old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=60)).isoformat()
        primary = [story(1), story(2)] + [story(i, published_at=old) for i in range(10, 17)]
        refill = [story(1), story(3)] + [story(i, published_at=old) for i in range(20, 26)]
        seeds = json.dumps([{"title": "Fresh AI financial announcement",
                             "published": story(1)["published_at"]}])
        with patch.object(news, "_grounded_text", return_value=json.dumps({"stories": primary})), patch.object(news, "_recovery_search", side_effect=[
            json.dumps({"stories": refill}), json.dumps({"stories": [story(4), story(5)]})
        ]) as recover:
            result = news.build_grounded_story_slate("2026-09-08", discovery_json=seeds)
        self.assertEqual(len(result), 5)
        self.assertEqual(recover.call_count, 2)
        self.assertIn("Fresh AI financial announcement", recover.call_args.args[0])
        self.assertIn("outside_freshness_window", recover.call_args.args[0])
        self.assertIn(old, recover.call_args.args[0])

    def test_discovery_never_substitutes_for_verified_stories(self):
        seeds = json.dumps([{"title": "Unverified headline", "published": story(1)["published_at"]}])
        with patch.object(news, "_grounded_text", return_value="{}"), patch.object(news, "_recovery_search", return_value="{}") as recover:
            with self.assertRaisesRegex(RuntimeError, "at least 5 required"):
                news.build_grounded_story_slate("2026-09-08", discovery_json=seeds)
        self.assertEqual(recover.call_count, 2)

    def test_discovery_filters_stale_future_and_malformed_items(self):
        now = dt.datetime.now(dt.timezone.utc)
        rows = news._fresh_discovery_seeds([
            None, {"title": "missing date"},
            {"title": "old", "published": (now-dt.timedelta(hours=49)).isoformat()},
            {"title": "future", "published": (now+dt.timedelta(hours=1)).isoformat()},
            {"title": "fresh", "published": now.isoformat()},
            {"title": "fresh", "published": now.isoformat()},
        ], now)
        self.assertEqual([x["headline"] for x in rows], ["fresh"])

    def test_prompt_uses_exact_rolling_window(self):
        now = dt.datetime(2026, 9, 8, 22, 9, tzinfo=dt.timezone.utc)
        prompt = news._story_prompt("2026-09-08", 8, now)
        self.assertIn("2026-09-06T22:09:00+00:00", prompt)
        self.assertIn("2026-09-08T22:09:00+00:00", prompt)

    def test_installed_production_selector_passes_rss_to_research(self):
        import writer_room_v3_1 as writer
        namespace = {}
        writer.install_v3_1(namespace)
        rss = [{"title": "Current AI announcement", "published": story(1)["published_at"]}]
        with patch.object(news, "_grounded_text", return_value=json.dumps({
            "stories": [story(i) for i in range(5)]
        })) as search:
            result = namespace["pick_top_stories"](rss, n=5, date_str="2026-09-08")
        self.assertEqual(len(result), 5)
        self.assertIn("Current AI announcement", search.call_args.args[0])

    def test_same_launch_different_outlets_requires_new_event(self):
        rows, _, calls = self.run_slate([
            story(1, headline="Meta launches Muse personal agent"),
            story(2, headline="Meta says Muse uses a secure virtual machine"),
            story(3, headline="Meta launches Muse for email and travel"),
        ], [story(4), story(5)], n=3)
        self.assertEqual(calls, 1)
        self.assertEqual(len(rows), 3)
        self.assertEqual(sum("Muse" in row["headline"] for row in rows), 1)

    def test_event_key_and_distinct_product_handling(self):
        self.assertTrue(news._same_news_event(
            dict(headline="First title", event_key="launch-a"),
            dict(headline="Different title", event_key="launch-a")))
        self.assertFalse(news._same_news_event(
            dict(headline="Meta launches Muse"), dict(headline="Meta announces Llama")))


if __name__ == "__main__":
    unittest.main()
