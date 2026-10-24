"""Decision-review prototype test: v1.0 data with an unknown lot cannot be accepted silently. Disposable synthetic DB."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import decision_review as R  # noqa: E402
from application import checkpoint_ops  # noqa: E402
from application.anchors import export_anchor, publish_candidate  # noqa: E402
from application.service import Manufacturing  # noqa: E402


class Review(unittest.TestCase):
    def test_review_lists_changes_and_blocks_unestablished_identity(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d); db, cur, custody = d / "r.sqlite", d / "c0.json", d / "custody"
            app = Manufacturing(db)
            app.create_unit("MTR-90001"); app.create_unit("MTR-90002"); app.create_unit("MTR-90003")
            app.close()
            app = Manufacturing(db); publish_candidate(cur, export_anchor(app)); app.close()
            app = Manufacturing(db)
            app.assemble("MTR-90001", "UNKNOWN", "BR-310"); app.ship("MTR-90001")      # v1.0 clears this
            app.assemble("MTR-90002", "BR-204", "BR-310"); app.ship("MTR-90002")       # recalled: hold
            app.assemble("MTR-90003", "BR-310", "BR-312"); app.ship("MTR-90003")       # registered unaffected
            app.announce("BR-204", ["DE"]); app.close()
            prop = checkpoint_ops.propose(db, cur, custody)
            review = R.build_review(db, cur, prop["candidate"])
            by = {r["motor"]: r for r in review["rows"]}
            self.assertEqual(by["MTR-90001"]["change"], "NEWLY_EXCLUDED"); self.assertTrue(by["MTR-90001"]["identityNotEstablished"])
            self.assertEqual(by["MTR-90002"]["change"], "NEWLY_HELD")
            self.assertEqual(by["MTR-90003"]["change"], "NEWLY_EXCLUDED"); self.assertFalse(by["MTR-90003"]["identityNotEstablished"])
            self.assertEqual(review["blockedByIdentity"], ["MTR-90001"])
            with self.assertRaises(SystemExit) as cm:      # even with every motor acknowledged
                R.accept_with_review(db, cur, custody, prop["candidate"], prop["candidateSha256"], "synthetic", ["MTR-90001", "MTR-90002", "MTR-90003"])
            self.assertIn("not established", str(cm.exception))
            self.assertFalse((custody / "accepted").exists())
            out = os.environ.get("LOT_REVIEW_OUT")
            if out:
                Path(out).write_text(json.dumps(review, indent=1, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
