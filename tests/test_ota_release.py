"""Ensure unattended runs cannot mix a reviewed kernel with a newer OTA."""
import io
import json
import os
from pathlib import Path
import runpy
import shutil
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/check-ota-release.py'


class ReleaseGate(unittest.TestCase):
    def run_gate(self, latest, event='schedule', snapshot='2026111800'):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'scripts').mkdir()
            (root/'ota').mkdir()
            (root/'kernel/tangorpro').mkdir(parents=True)
            shutil.copyfile(SCRIPT, root/'scripts/check.py')
            (root/'ota/tangorpro.json').write_text(json.dumps({'release': '2026111800'}))
            (root/'kernel/tangorpro/provenance.json').write_text(json.dumps({'grapheneos_release': snapshot}))
            with patch.dict(os.environ, {'GITHUB_EVENT_NAME': event, 'GITHUB_OUTPUT': ''}), \
                 patch('urllib.request.urlopen', return_value=io.BytesIO(latest.encode())):
                runpy.run_path(str(root/'scripts/check.py'), run_name='__main__')

    def test_matching_release(self):
        self.run_gate('2026111800 1794968526 tangorpro stable')

    def test_new_stable_cannot_publish_with_old_snapshot(self):
        with self.assertRaisesRegex(SystemExit, 'reviewed matching kernel'):
            self.run_gate('2026112800 1794968526 tangorpro stable')

    def test_manual_rebuild_can_use_reviewed_older_release(self):
        self.run_gate('2026112800 1794968526 tangorpro stable', event='workflow_dispatch')

    def test_mismatched_snapshot_rejected_even_manually(self):
        with self.assertRaisesRegex(SystemExit, 'snapshot release differ'):
            self.run_gate('2026111800', event='workflow_dispatch', snapshot='2026110100')

    def test_invalid_upstream_response(self):
        with self.assertRaisesRegex(SystemExit, 'Invalid upstream'):
            self.run_gate('<html>error</html>')


if __name__ == '__main__':
    unittest.main()
