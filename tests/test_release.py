import unittest

from app.operator import choose_tool
from app.sql_chat import guard_select, narrow_to_application, sql_for_question
from app.platform.release import corpus_version, deployment_id, release_manifest


class ReleaseTests(unittest.TestCase):
    def test_manifest_is_stable_for_this_tree(self):
        first = release_manifest()
        second = release_manifest()
        self.assertEqual(first, second)
        self.assertEqual(first["app_version"], "1.1.0")
        self.assertEqual(first["pipeline_version"], "loan-graph-v1")
        self.assertEqual(deployment_id(first), deployment_id(second))
        self.assertTrue(corpus_version().startswith("corpus-"))

    def test_operator_picks_a_tool_from_the_words(self):
        self.assertEqual(choose_tool("score apex")["tool"], "score")
        self.assertEqual(choose_tool("score apex")["application_id"], "apex")
        self.assertEqual(choose_tool("why was harbor reviewed")["tool"], "explain")
        self.assertEqual(choose_tool("monitor the process")["tool"], "monitor")
        self.assertEqual(choose_tool("load the new inbox file")["tool"], "load_inbox")

    def test_sql_chat_maps_words_and_blocks_writes(self):
        self.assertIn("credit.latest_decision", sql_for_question("show latest decision"))
        self.assertIn("credit.loan_application", sql_for_question("loan application"))
        with self.assertRaises(ValueError):
            guard_select("DELETE FROM credit.decision")
        with self.assertRaises(ValueError):
            guard_select("SELECT * FROM credit.decision; DROP TABLE credit.decision")
        scoped, note = narrow_to_application(sql_for_question("latest decision"), "apex")
        self.assertIn("application_id = 'apex'", scoped)
        self.assertEqual(note, "")
        checks, _ = narrow_to_application(sql_for_question("check"), "harbor")
        self.assertIn("credit.decision WHERE application_id = 'harbor'", checks)
        untouched, skipped = narrow_to_application(sql_for_question("deployment"), "apex")
        self.assertNotIn("application_id = 'apex'", untouched)
        self.assertIn("no loan file id", skipped)
        with self.assertRaises(ValueError):
            narrow_to_application(sql_for_question("decision"), "apex; drop")


if __name__ == "__main__":
    unittest.main()
