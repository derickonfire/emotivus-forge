from __future__ import annotations
import json, shutil, tempfile
from pathlib import Path
from tools.check_progress_status import check_progress
from tests.support import FORGE_ROOT, ForgeTestCase

class ProgressStatusTests(ForgeTestCase):
    def _copy(self, root: Path) -> None:
        for relative in ('FORGE-PRODUCT.json','PROGRESS-STATUS.md','ROADMAP.md','planning/README.md'):
            target=root/relative; target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes((FORGE_ROOT/relative).read_bytes())

    def test_packaged_goal_and_chunk_surfaces_match(self) -> None:
        result=check_progress(FORGE_ROOT)
        self.assertEqual(result['status'],'PASS',result['problems'])
        self.assertEqual([g['id'] for g in result['goals']],['G1','G2','G3'])
        self.assertEqual(result['active_chunks'],['P2-01'])

    def test_goal_status_drift_in_a_planning_doc_is_detected(self) -> None:
        # The one cross-surface check kept after the 0.573 anti-bloat pass: a reader
        # of a planning doc must not see a goal status that contradicts the canonical
        # goals. Ceremony (timebox format, retired-percentage guards, exact nav labels,
        # same-file duplication) was removed; this genuine misstatement stays caught.
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); self._copy(root); p=root/'PROGRESS-STATUS.md'
            p.write_text(p.read_text().replace('| G2 · One-Command Session Continuity | **ACTIVE** |','| G2 · One-Command Session Continuity | **COMPLETE** |',1))
            result=check_progress(root); self.assertEqual(result['status'],'FAIL'); self.assertTrue(any('goal rows differ' in x for x in result['problems']))

    def test_roadmap_chunk_drift_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); self._copy(root); p=root/'ROADMAP.md'; p.write_text(p.read_text().replace('| P1-01 |','| P1-99 |',1)); result=check_progress(root); self.assertEqual(result['status'],'FAIL'); self.assertTrue(any('chunk IDs' in x for x in result['problems']))
