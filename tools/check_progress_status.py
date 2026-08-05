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
    if [g[0] for g in expected] != ['G1','G2','G3']: problems.append('active_roadmap must declare exactly G1, G2, and G3')
    if not roadmap.get('percentages_retired'): problems.append('legacy roadmap percentages must be explicitly retired')
    if any('percent' in c for c in chunks if isinstance(c,dict)): problems.append('roadmap chunks must not carry percentages')
    ids=[str(c.get('id','')) for c in chunks if isinstance(c,dict)]
    if len(ids)!=len(set(ids)) or not ids: problems.append('roadmap chunk IDs must be non-empty and unique')
    valid_status={'COMPLETE','ACTIVE','QUEUED','BLOCKED','RETIRED','FOUNDATION_ACTIVE','CONTINUOUS'}
    if any(status not in valid_status for _,_,status in expected): problems.append('goal status is outside the approved status vocabulary')
    if any(str(c.get('status','')) not in valid_status for c in chunks if isinstance(c,dict)): problems.append('chunk status is outside the approved status vocabulary')
    if any(not re.fullmatch(r'\d+–\d+ min',str(c.get('timebox',''))) for c in chunks if isinstance(c,dict)): problems.append('every chunk must declare an 8–20 minute timebox')
    for c in chunks:
        if isinstance(c,dict):
            a,b=map(int,re.fullmatch(r'(\d+)–(\d+) min',str(c['timebox'])).groups())
            if a<8 or b>20 or a>b: problems.append(f"chunk {c.get('id')} timebox is outside 8–20 minutes")
    progress=product.get('progress_status',{}) if isinstance(product.get('progress_status'),dict) else {}
    if progress.get('goal_status') != {gid:status for gid,_,status in expected}: problems.append('progress_status goal_status differs from active_roadmap')
    web=product.get('website',{}) if isinstance(product.get('website'),dict) else {}
    nav=web.get('primary_navigation',[])
    if nav != ['Home','Run Forge','Project Truth','Continuity & Evidence']: problems.append('website primary navigation must contain exactly four approved pages')
    summary=web.get('roadmap_summary',{}) if isinstance(web.get('roadmap_summary'),dict) else {}
    if [(g.get('id'),g.get('name'),g.get('status')) for g in summary.get('goals',[])] != expected: problems.append('website goal summary differs from canonical goals')
    docs=[]
    for rel in ('ROADMAP.md','PROGRESS-STATUS.md','planning/README.md'):
        text=(root/rel).read_text(encoding='utf-8'); rows=_goal_rows(text)
        if rows != expected: problems.append(f'{rel} goal rows differ from canonical goals: {rows!r}')
        docs.append(text)
    roadmap_ids=_chunk_ids((root/'ROADMAP.md').read_text(encoding='utf-8'))
    if roadmap_ids != ids: problems.append('ROADMAP.md chunk IDs differ from canonical chunks')
    if any(re.search(r'\b(?:roadmap average|overall percent|approximately \d+%)',t,re.I) for t in docs): problems.append('current progress documents still advertise a legacy percentage')
    return {'schema':2,'status':'PASS' if not problems else 'FAIL','version':product.get('version',''),'goals':[{'id':a,'name':b,'status':c} for a,b,c in expected],'completed_chunks':sum(1 for c in chunks if c.get('status')=='COMPLETE'),'active_chunks':[c.get('id') for c in chunks if c.get('status')=='ACTIVE'],'problems':problems,'truth_boundary':'Goal and chunk status is planning metadata, not efficacy, release authorization, or proof of correctness.'}

def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('root',nargs='?',default='.'); r=check_progress(Path(ap.parse_args().root)); print(json.dumps(r,indent=2)); return 0 if r['status']=='PASS' else 1
if __name__=='__main__': raise SystemExit(main())
