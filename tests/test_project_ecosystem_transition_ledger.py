import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("projector",ROOT/"tools/project_ecosystem_transition_ledger.py")
mod=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(mod)

class MonitoringProjectionTests(unittest.TestCase):
    def test_projection_preserves_ordered_custody_identity_chain(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); receipts=root/"receipts"; receipts.mkdir()
            rows=[
                {
                    "schema":"stegverse.ecosystem-transition-custody-receipt/v1",
                    "receipt_sha256":"sha256:"+"a"*64,
                    "previous_receipt_sha256":None,
                    "source_organization":"StegVerse-002",
                    "source_org_receipt_sha256":"sha256:"+"b"*64,
                    "source_repository":"micro-node-runtime",
                    "repo_receipt_sha256":"sha256:"+"c"*64,
                    "repo_transition_id":"TR-1",
                    "ecosystem_transition_class":"ORGANIZATION_STATE_PROPAGATION",
                },
                {
                    "schema":"stegverse.ecosystem-transition-custody-receipt/v1",
                    "receipt_sha256":"sha256:"+"d"*64,
                    "previous_receipt_sha256":"sha256:"+"a"*64,
                    "source_organization":"StegVerse-002",
                    "source_org_receipt_sha256":"sha256:"+"e"*64,
                    "source_repository":"micro-node-runtime",
                    "repo_receipt_sha256":"sha256:"+"f"*64,
                    "repo_transition_id":"TR-2",
                    "ecosystem_transition_class":"ORGANIZATION_STATE_PROPAGATION",
                },
            ]
            for i,row in enumerate(rows):
                (receipts/f"{i:02d}.json").write_text(json.dumps(row),encoding="utf-8")
            projection=mod.build_projection(root)
            self.assertEqual(projection["schema"],"master-records.ecosystem-ledger-monitoring-projection/v2")
            self.assertEqual([r["index"] for r in projection["ordered_custody_receipts"]],[0,1])
            self.assertEqual(projection["ordered_custody_receipts"][1]["previous_receipt_sha256"],rows[0]["receipt_sha256"])
            self.assertFalse(projection["custody_authority"])

if __name__=="__main__":
    unittest.main()
