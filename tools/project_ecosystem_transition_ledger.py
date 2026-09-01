#!/usr/bin/env python3
import argparse,json,os
from pathlib import Path

def ledger_root():
    override=os.getenv("STEGVERSE_ECOSYSTEM_LEDGER_ROOT")
    if override:return Path(override).expanduser().resolve()
    return (Path(os.getenv("XDG_STATE_HOME",str(Path.home()/".local/state")))/"stegverse/ecosystem-ledger").resolve()

def main():
    p=argparse.ArgumentParser();p.add_argument("--out");a=p.parse_args()
    root=ledger_root();receipts=root/"receipts";rows=[]
    if receipts.exists():
        for fp in sorted(receipts.glob("*.json")):
            try:
                r=json.loads(fp.read_text())
                if r.get("schema")=="stegverse.ecosystem-transition-custody-receipt/v1":
                    rows.append(r)
            except Exception: pass
    by_org={}
    for r in rows:
        by_org[r["source_organization"]]=by_org.get(r["source_organization"],0)+1
    head=json.loads((root/"HEAD.json").read_text()) if (root/"HEAD.json").exists() else None
    projection={"schema":"master-records.ecosystem-ledger-monitoring-projection/v1","read_only":True,"custody_authority":False,"transition_count":len(rows),"by_organization":dict(sorted(by_org.items())),"head":head,"source":"master-records/orchestration ecosystem transition ledger"}
    text=json.dumps(projection,indent=2,sort_keys=True)+"\n"
    if a.out: Path(a.out).write_text(text)
    print(text,end="")
if __name__=="__main__":main()
