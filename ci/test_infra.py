"""Verification-tooling tests only; no product source is mutated."""
import hashlib
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch
import yaml
import run_gates as gates
from prepare import check_file


class InfrastructureTests(unittest.TestCase):
    def test_frozen_fixture_change_is_fatal(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p=root/'fixture';p.write_bytes(b'original')
            pin={'fixture':hashlib.sha256(p.read_bytes()).hexdigest()}
            gates.frozen(root,pin);p.write_bytes(b'changed')
            with self.assertRaises(RuntimeError):gates.frozen(root,pin)

    def test_missing_or_mismatched_artifact_is_fatal(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'artifact'
            with self.assertRaises(RuntimeError):check_file(p,'incorrect')
            p.write_bytes(b'wrong')
            with self.assertRaises(RuntimeError):check_file(p,'incorrect')

    def test_nonzero_exit_cannot_become_success(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(gates,'OUT',Path(temp)):
            with self.assertRaises(RuntimeError):gates.command('failing',[sys.executable,'-c','raise SystemExit(9)'])

    def test_workflow_is_read_only_pinned_and_does_not_skip_drafts(self):
        path=gates.ROOT/'.github/workflows/phase31-release-gates.yml'
        workflow=yaml.load(path.read_text(),Loader=yaml.BaseLoader)
        self.assertEqual(workflow['permissions'],{'contents':'read'})
        self.assertIn('pull_request',workflow['on']);self.assertIn('push',workflow['on'])
        self.assertNotIn('pull_request_target',workflow['on'])
        for job in workflow['jobs'].values():
            self.assertNotIn('continue-on-error',job)
            for step in job.get('steps',[]):
                self.assertNotIn('continue-on-error',step)
                if 'uses' in step:self.assertRegex(step['uses'],r'^actions/[a-z-]+@[0-9a-f]{40}$')
        self.assertEqual(workflow['jobs']['required']['if'],'always()')
        self.assertEqual(workflow['jobs']['required']['needs'],'verify')


if __name__=='__main__':unittest.main()
