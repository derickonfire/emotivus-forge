#!/usr/bin/env python3
"""Validate Forge outcome goals and timeboxed roadmap chunks across packaged surfaces."""
from __future__ import annotations
import argparse, json, re
from pathlib import Path
from typing import Any

GOAL_RE = re.compile(r"^\| (G[123]) · ([^|]+) \| \*\*([A-Z_]+)\*\* \|")
CHUNK_RE = re.compile(r"^\| (P[0-4]-\d{2}) \|")

def _product(root: Path) -> dict[str, Any]:
    value=json.loads((root/'FORGE-PRODUCT.json').read_text(encoding='utf-8'))
    if not isinstance(value,dict): raise ValueError('FORGE-PRODUCT.json must be an object')
    return value

def _goal_rows(text: str):
    return [(m.group(1),m.group(2).strip(),m.group(3)) for line in text.splitlines() if (m:=GOAL_RE.match(line))]

def _chunk_ids(text: str):
    return [m.group(1) for line in text.splitlines() if (m:=CHUNK_RE.match(line))]

def check_progress(root: Path) -> dict[str, Any]:
    root=root.resolve(); product=_product(root); problems=[]
    roadmap=product.get('active_roadmap',{}) if isinstance(product.get('active_roadmap'),dict) else {}
    goals=roadmap.get('goals',[]) if isinstance(roadmap.get('goals'),list) else []
    chunks=roadmap.get('chunks',[]) if isinstance(roadmap.get('chunks'),list) else []
    expected=[(str(g.get('id','')),str(g.get('name','')),str(g.get('status',''))) for g in goals if isinstance(g,dict)]
    # Structural sanity and reader-facing truth are kept; internal bookkeeping rituals
    # (per-chunk timebox format/range, re-litigating the long-retired percentage roadmap,
    # exact website nav labels, and same-file goal-status duplication) were removed in the
    # 0.573 anti-bloat pass because they enforced ceremony, not a truthful claim a reader
    # of Forge could be misled by. What remains catches a genuine misstatement of status.
    if [g[0] for g in expected] != ['G1','G2','G3']: problems.append('active_roadmap must declare exactly G1, G2, and G3')
    ids=[str(c.get('id','')) for c in chunks if isinstance(c,dict)]
    if len(ids)!=len(set(ids)) or not ids: problems.append('roadmap chunk IDs must be non-empty and unique')
    valid_status={'COMPLETE','ACTIVE','QUEUED','BLOCKED','RETIRED','FOUNDATION_ACTIVE','CONTINUOUS'}
    if any(status not in valid_status for _,_,status in expected): problems.append('goal status is outside the approved status vocabulary')
    if any(str(c.get('status','')) not in valid_status for c in chunks if isinstance(c,dict)): problems.append('chunk status is outside the approved status vocabulary')
    for rel in ('ROADMAP.md','PROGRESS-STATUS.md','planning/README.md'):
        rows=_goal_rows((root/rel).read_text(encoding='utf-8'))
        if rows != expected: problems.append(f'{rel} goal rows differ from canonical goals: {rows!r}')
    roadmap_ids=_chunk_ids((root/'ROADMAP.md').read_text(encoding='utf-8'))
    if roadmap_ids != ids: problems.append('ROADMAP.md chunk IDs differ from canonical chunks')
    return {'schema':2,'status':'PASS' if not problems else 'FAIL','version':product.get('version',''),'goals':[{'id':a,'name':b,'status':c} for a,b,c in expected],'completed_chunks':sum(1 for c in chunks if c.get('status')=='COMPLETE'),'active_chunks':[c.get('id') for c in chunks if c.get('status')=='ACTIVE'],'problems':problems,'truth_boundary':'Goal and chunk status is planning metadata, not efficacy, release authorization, or proof of correctness.'}

def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('root',nargs='?',default='.'); r=check_progress(Path(ap.parse_args().root)); print(json.dumps(r,indent=2)); return 0 if r['status']=='PASS' else 1
if __name__=='__main__': raise SystemExit(main())
