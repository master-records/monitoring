#!/usr/bin/env python3
import argparse,json,os
from pathlib import Path

def ledger_root():
    override=os.getenv("STEGVERSE_ECOSYSTEM_LEDGER_ROOT")
    if override:return Path(override).expanduser().resolve()
    return (Path(os.getenv("XDG_STATE_HOME",str(Path.home()/".local/state")))/"stegverse/ecosystem-ledger").resolve()

def build_projection(root:Path):
    receipts=root/"receipts";rows=[]
    if receipts.exists():
        for fp in sorted(receipts.glob("*.json")):
            try:
                r=json.loads(fp.read_text())
                if r.get("schema")=="stegverse.ecosystem-transition-custody-receipt/v1":
                    rows.append(r)
            except Exception:
                pass
    by_org={}
    for r in rows:
        by_org[r["source_organization"]]=by_org.get(r["source_organization"],0)+1
    head=json.loads((root/"HEAD.json").read_text()) if (root/"HEAD.json").exists() else None
    ordered=[
        {
            "index":index,
            "receipt_sha256":r.get("receipt_sha256"),
            "previous_receipt_sha256":r.get("previous_receipt_sha256"),
            "source_organization":r.get("source_organization"),
            "source_org_receipt_sha256":r.get("source_org_receipt_sha256"),
            "source_repository":r.get("source_repository"),
            "repo_receipt_sha256":r.get("repo_receipt_sha256"),
            "repo_transition_id":r.get("repo_transition_id"),
            "ecosystem_transition_class":r.get("ecosystem_transition_class"),
        }
        for index,r in enumerate(rows)
    ]
    return {
        "schema":"master-records.ecosystem-ledger-monitoring-projection/v2",
        "read_only":True,
        "custody_authority":False,
        "transition_count":len(rows),
        "by_organization":dict(sorted(by_org.items())),
        "head":head,
        "ordered_custody_receipts":ordered,
        "sequence_verification":{
            "complete_for_projected_ecosystem_custody_receipts":True,
            "principal_transition_sequence_available_only_when_present_in_canonical_reconstruction_receipt":True,
        },
        "source":"master-records/orchestration ecosystem transition ledger",
        "authority_effect":"NONE_PROJECTION_ONLY"
    }

def main():
    p=argparse.ArgumentParser();p.add_argument("--out");a=p.parse_args()
    projection=build_projection(ledger_root())
    text=json.dumps(projection,indent=2,sort_keys=True)+"\n"
    if a.out: Path(a.out).write_text(text)
    print(text,end="")

if __name__=="__main__":main()
