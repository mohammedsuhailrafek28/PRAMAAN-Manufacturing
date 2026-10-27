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

    def test_hosted_ansi_count_is_checked_without_relaxing_count_or_exit(self):
        line='\x1b[2m      Tests \x1b[22m \x1b[1m\x1b[32m33 passed\x1b[39m\x1b[22m'
        self.assertIsNone(re.search(r'Tests\s+33 passed',line))
        self.assertRegex(gates.terminal_text(line),r'Tests\s+33 passed')
        with tempfile.TemporaryDirectory() as temp,patch.object(gates,'OUT',Path(temp)):
            command=[sys.executable,'-c',f'print({line!r})']
            self.assertEqual(gates.command('colored',command,pattern=r'Tests\s+33 passed')['exitCode'],0)
            self.assertEqual((Path(temp)/'colored.txt').read_text().strip(),line)
            with self.assertRaises(RuntimeError):gates.command('wrong-count',command,pattern=r'Tests\s+34 passed')
            with self.assertRaises(RuntimeError):gates.command('failed',command[:-1]+[command[-1]+';raise SystemExit(3)'],pattern=r'Tests\s+33 passed')

    def test_a_failed_gate_is_recorded_and_fails_the_run(self):
        result={'gates':{}}
        gates.gate(result,'X',lambda:(_ for _ in ()).throw(RuntimeError('boom')))
        self.assertIn('X',result['failures']);self.assertNotIn('X',result['gates'])
        src=(gates.ROOT/'ci/run_gates.py').read_text()
        self.assertIn("if result.get('failures'):raise RuntimeError",src)       # a recorded failure can never end as PASSED
        self.assertLess(src.index("if result.get('failures')"),src.index("result['status']='PASSED'"))

    def test_expected_counts_are_exact_and_cover_every_application_module(self):
        modules={p.stem for p in (gates.ROOT/'application').glob('test_*.py')}
        self.assertEqual(modules,set(gates.EXPECTED['application']))
        self.assertEqual({p.stem for p in (gates.ROOT/'performance').glob('test_*.py')},set(gates.EXPECTED['performance']))

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
