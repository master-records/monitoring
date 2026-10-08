import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("projector",ROOT/"tools/project_ecosystem_transition_ledger.py")
mod=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(mod)

class MonitoringProjectionTests(unittest.TestCase):
    def _write_chain(self,root,schema):
        receipts=root/"receipts"; receipts.mkdir()
        rows=[
            {
                "schema":schema,
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
                "schema":schema,
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
        return rows

    def test_projection_preserves_ordered_organization_record_identity_chain(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            rows=self._write_chain(root,"stegverse.ecosystem-transition-organization-record-receipt/v1")
            projection=mod.build_projection(root)
            self.assertEqual(projection["schema"],"master-records.ecosystem-ledger-monitoring-projection/v2")
            self.assertEqual(projection["transition_count"],2)
            self.assertEqual([r["index"] for r in projection["ordered_organization_record_receipts"]],[0,1])
            self.assertEqual(projection["ordered_organization_record_receipts"][1]["previous_receipt_sha256"],rows[0]["receipt_sha256"])
            self.assertTrue(projection["sequence_verification"]["complete_for_projected_ecosystem_organization_record_receipts"])
            self.assertNotIn("ordered_custody_receipts",projection)
            self.assertFalse(projection["custody_authority"])

    def test_projection_accepts_legacy_receipt_schema(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            rows=self._write_chain(root,mod.LEGACY_ORGANIZATION_RECORD_RECEIPT_SCHEMA)
            self.assertEqual(mod.LEGACY_ORGANIZATION_RECORD_RECEIPT_SCHEMA,"stegverse.ecosystem-transition-custody-receipt/v1")
            projection=mod.build_projection(root)
            self.assertEqual(projection["transition_count"],2)
            self.assertEqual(projection["ordered_organization_record_receipts"][1]["previous_receipt_sha256"],rows[0]["receipt_sha256"])

    def test_projection_can_expose_sv002_principal_sequence_reference(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); (root/"receipts").mkdir()
            reconstruction=root/"sv002-reconstruction.json"
            reconstruction.write_text(json.dumps({
                "experiment_id":"STEGVERSE-002-SELF-CHARACTERIZATION-001",
                "status":"PASS",
                "reconstruction":"PASS",
                "evidence":{
                    "ordered_transition_receipts":[
                        {"sequence":0,"transition_receipt_id":"TR-1","transition_receipt_sha256":"a"*64}
                    ],
                    "repository_ledger_root":{"root_hash":"b"*64},
                    "organization_ledger_root":{"root_hash":"c"*64},
                    "transition_receipt_terminal_sha256":"a"*64,
                },
            }),encoding="utf-8")
            projection=mod.build_projection(root,reconstruction)
            ref=projection["sv002_self_characterization_reference"]
            self.assertEqual(ref["status"],"PASS")
            self.assertEqual(ref["ordered_transition_receipts"][0]["transition_receipt_id"],"TR-1")
            self.assertEqual(ref["repository_ledger_root"]["root_hash"],"b"*64)
            self.assertFalse(projection["custody_authority"])


if __name__=="__main__":
    unittest.main()
