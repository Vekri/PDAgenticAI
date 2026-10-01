import tempfile
import unittest
from pathlib import Path

from app.formatting import fmt_ratio
from app.orchestrator import run_decision
from app.policy_rules import APPROVE_WHY
from app.rag import get_index
from app.samples import get_sample
from app.store import get_decision, list_decisions


class PipelineTests(unittest.TestCase):
    def test_apex_matches_the_sample_decision(self):
        result = run_decision(get_sample("apex"), use_llm=False, persist=False)
        self.assertEqual(result.recommendation, "APPROVE")
        self.assertEqual(result.pd_display, "3.8%")
        self.assertEqual(result.risk_grade, "Low")
        self.assertEqual(result.key_ratios["credit_score"], 720)
        self.assertAlmostEqual(result.key_ratios["debt_to_ebitda"], 2.0, places=6)
        self.assertAlmostEqual(result.key_ratios["dscr"], 1.62, places=4)
        self.assertEqual(fmt_ratio(result.key_ratios["debt_to_ebitda"]), "2.0x")
        self.assertEqual(fmt_ratio(result.key_ratios["dscr"]), "1.62x")
        self.assertEqual(result.why, APPROVE_WHY)
        self.assertEqual(result.explanation_source, "local-template")
        self.assertEqual(result.app_version, "1.1.0")
        self.assertTrue(result.policy_version)
        self.assertTrue(result.rag_corpus_version.startswith("corpus-"))
        self.assertIn("APPROVE", result.explanation)
        self.assertIn("Apex Manufacturing Co.", result.explanation)
        self.assertTrue(all(abs(item["logit"]) < 1e-9 for item in result.drivers))
        self.assertIsNotNone(result.ml_pd)
        self.assertGreater(result.ml_pd, 0.0)
        self.assertLess(result.ml_pd, 0.25)
        self.assertEqual([step["step"] for step in result.audit], list(range(1, 9)))
        names = {agent["name"] for agent in result.agents}
        self.assertTrue(
            {
                "Data Agent",
                "Knowledge Agent",
                "Financial Agent",
                "Risk Agent",
                "Policy Agent",
                "Orchestrator Agent",
                "Decision Agent",
            }.issubset(names)
        )
        self.assertTrue(all(check["passed"] for check in result.policy_checks if check["level"] != "control"))
        self.assertTrue(any(check["code"] == "fair_lending" and check["passed"] for check in result.policy_checks))

    def test_harbor_goes_to_review_without_a_hard_stop(self):
        result = run_decision(get_sample("harbor"), use_llm=False, persist=False)
        self.assertEqual(result.recommendation, "REVIEW")
        self.assertGreater(result.pd_score, 0.05)
        self.assertLess(result.pd_score, 0.15)
        self.assertTrue(all(check["passed"] or check["level"] != "hard" for check in result.policy_checks))
        self.assertTrue(any(check["code"] == "pd" and not check["passed"] for check in result.policy_checks))

    def test_northwind_is_declined(self):
        result = run_decision(get_sample("northwind"), use_llm=False, persist=False)
        self.assertEqual(result.recommendation, "REJECT")
        self.assertTrue(any(not check["passed"] and check["level"] == "hard" for check in result.policy_checks))

    def test_bankruptcy_is_a_hard_stop(self):
        application = get_sample("apex").model_copy(update={"bankruptcy": True})
        result = run_decision(application, use_llm=False, persist=False)
        self.assertEqual(result.recommendation, "REJECT")
        self.assertTrue(any(check["code"] == "bankruptcy" and not check["passed"] for check in result.policy_checks))

    def test_missing_ebitda_stays_in_review(self):
        application = get_sample("apex").model_copy(update={"ebitda": 0})
        result = run_decision(application, use_llm=False, persist=False)
        self.assertEqual(result.recommendation, "REVIEW")
        self.assertIsNone(result.pd_score)
        self.assertTrue(result.errors)

    def test_policy_sections_are_retrievable(self):
        index = get_index()
        cited = index.get("§4.2")
        self.assertIsNotNone(cited)
        self.assertEqual(cited["source"], "Credit Policy")
        self.assertIn("5 percent", cited["text"])
        self.assertIsNotNone(index.get("§3.1"))
        hits = index.search("straight-through approval DSCR debt EBITDA", k=3)
        self.assertTrue(hits)
        self.assertTrue(any("4.2" in hit["section"] or "straight-through" in hit["text"].lower() for hit in hits))

    def test_audit_log_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "decisions.db"
            result = run_decision(get_sample("apex"), use_llm=False, persist=True, db_path=path)
            self.assertEqual(len(list_decisions(path=path)), 1)
            stored = get_decision(result.run_id, path=path)
            self.assertIsNotNone(stored)
            self.assertEqual(stored["recommendation"], "APPROVE")
            self.assertEqual(stored["pd_display"], "3.8%")


if __name__ == "__main__":
    unittest.main()
