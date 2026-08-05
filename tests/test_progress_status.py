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

    def test_website_goal_drift_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); self._copy(root); p=root/'FORGE-PRODUCT.json'; value=json.loads(p.read_text()); value['website']['roadmap_summary']['goals'][1]['status']='COMPLETE'; p.write_text(json.dumps(value,indent=2)+'\n'); result=check_progress(root); self.assertEqual(result['status'],'FAIL'); self.assertTrue(any('website goal summary' in x for x in result['problems']))

    def test_legacy_percentage_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); self._copy(root); p=root/'PROGRESS-STATUS.md'; p.write_text(p.read_text()+'\nApproximate roadmap average: **89%**\n'); result=check_progress(root); self.assertEqual(result['status'],'FAIL'); self.assertTrue(any('legacy percentage' in x for x in result['problems']))

    def test_invalid_timebox_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); self._copy(root); p=root/'FORGE-PRODUCT.json'; value=json.loads(p.read_text()); value['active_roadmap']['chunks'][0]['timebox']='2–30 min'; p.write_text(json.dumps(value,indent=2)+'\n'); result=check_progress(root); self.assertEqual(result['status'],'FAIL'); self.assertTrue(any('timebox' in x for x in result['problems']))

    def test_navigation_must_have_exactly_four_pages(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); self._copy(root); p=root/'FORGE-PRODUCT.json'; value=json.loads(p.read_text()); value['website']['primary_navigation'].append('Roadmap'); p.write_text(json.dumps(value,indent=2)+'\n'); result=check_progress(root); self.assertEqual(result['status'],'FAIL'); self.assertTrue(any('exactly four' in x for x in result['problems']))

    def test_roadmap_chunk_drift_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); self._copy(root); p=root/'ROADMAP.md'; p.write_text(p.read_text().replace('| P1-01 |','| P1-99 |',1)); result=check_progress(root); self.assertEqual(result['status'],'FAIL'); self.assertTrue(any('chunk IDs' in x for x in result['problems']))
