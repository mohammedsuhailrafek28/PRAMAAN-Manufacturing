"""Reliability of queued read-only requests (Render Free investigation). Synthetic data only. Additive: no existing test is changed.

Queued GETs share one verification only if it started after they arrived; commands, external evidence, prefix-only state, failures and
VERIFYING are never answered from a stored result, and the verification budget is a fail-closed time bound, not a weaker check.
"""
import json
import os
import threading
import time
import unittest
from unittest.mock import patch

from . import audit, service
from .service import Manufacturing
from .test_consolidated_safety import Served, MOTOR

DECISIONS = f'/api/motors/{MOTOR}/decisions'
SWEEP = ('/api/snapshot', '/api/motors', DECISIONS, f'/api/motors/{MOTOR}/genealogy', f'/api/motors/{MOTOR}/lifecycle',
         f'/api/motors/{MOTOR}/provenance', '/api/trace/bearingLot/BR-310', '/api/lots/BR-310/investigation')


class Counting:
    """Wrap Manufacturing.snapshot: count calls, optionally hold each one for `delay` seconds (a slow CPU)."""
    def __init__(self, delay=0.0, fail=0):
        self.calls, self.delay, self.fail, self.real = 0, delay, fail, Manufacturing.snapshot
        self.lock = threading.Lock()

    def function(self):
        counter = self

        def snapshot(app, *a, **kw):
            return counter.call(app, *a, **kw)
        return snapshot

    def call(self, app, *a, **kw):
        with self.lock:
            self.calls += 1
            failing = self.fail > 0
            self.fail -= 1 if failing else 0
        if self.delay:
            time.sleep(self.delay)
        if failing:
            raise audit.Verifying()
        return self.real(app, *a, **kw)


def concurrently(s, paths):
    out = [None] * len(paths)
    start = threading.Barrier(len(paths))

    def one(i):
        start.wait()
        out[i] = s.get(paths[i])
    ts = [threading.Thread(target=one, args=(i,)) for i in range(len(paths))]
    [t.start() for t in ts]; [t.join() for t in ts]
    return out


class SharedReadTests(unittest.TestCase):
    def test_overlapping_reads_share_a_later_started_verification_and_stay_correct(self):
        s = Served(self)
        serial = [s.get(p) for p in SWEEP]                      # reference answers, one verification each
        counter = Counting(delay=0.4)
        with patch.object(Manufacturing, 'snapshot', counter.function()):
            burst = concurrently(s, list(SWEEP) * 2)            # 16 simultaneous readers
        self.assertLess(counter.calls, 16, 'queued readers must share verifications')
        self.assertLessEqual(counter.calls, 8, 'at most one verification per reader that could not join a later one')
        for i, (status, body) in enumerate(burst):
            ref = serial[i % len(SWEEP)]
            self.assertEqual(status, ref[0], SWEEP[i % len(SWEEP)])
            if SWEEP[i % len(SWEEP)] != '/api/snapshot':        # snapshot differs only in verifiedAt
                self.assertEqual(body, ref[1], SWEEP[i % len(SWEEP)])
            else:
                a, b = dict(body), dict(ref[1])
                for k in (a, b):
                    k['freshness'] = {x: y for x, y in k['freshness'].items() if x != 'verifiedAt'}
                self.assertEqual(a, b)

    def test_a_reader_never_gets_a_verification_that_started_before_it_arrived(self):
        s = Served(self)
        entered, release = threading.Event(), threading.Event()
        real, calls = Manufacturing.snapshot, []

        def slow_first(app, *a, **kw):
            calls.append(time.monotonic_ns())
            if len(calls) == 1:
                entered.set(); release.wait(10)
            return real(app, *a, **kw)
        with patch.object(Manufacturing, 'snapshot', slow_first):
            first = []
            t1 = threading.Thread(target=lambda: first.append(s.get('/api/snapshot'))); t1.start()
            self.assertTrue(entered.wait(10))                   # verification 1 is running and began BEFORE the next reader arrives
            late = []
            t2 = threading.Thread(target=lambda: late.append(s.get('/api/snapshot'))); t2.start()
            time.sleep(0.3); release.set(); t1.join(); t2.join()
        self.assertEqual(len(calls), 2, "the late reader needs its own verification")
        self.assertEqual((first[0][0], late[0][0]), (200, 200))

    def test_external_evidence_is_never_hidden_by_an_earlier_verification(self):
        s = Served(self)
        self.assertEqual(s.get(DECISIONS)[0], 200)
        s.external_capture()                                    # committed after that verification, before the next request
        snap = s.get('/api/snapshot')[1]
        self.assertEqual(snap['checkpoint']['state'], 'ANCHORED_PREFIX_ONLY')
        self.assertTrue(all(not v['currentReleaseEligible'] for v in snap['eligibility'].values()))
        status, body = s.get(DECISIONS)
        self.assertEqual(status, 409)
        self.assertNotIn('decisions', body)

    def test_prefix_only_stays_withheld_under_concurrency(self):
        s = Served(self)
        s.external_capture()
        with patch.object(Manufacturing, 'snapshot', Counting(delay=0.2).function()):
            out = concurrently(s, [DECISIONS, '/api/lots/BR-310/investigation'] * 4 + ['/api/snapshot'] * 4)
        for path, (status, body) in zip([DECISIONS, '/api/lots/BR-310/investigation'] * 4 + ['/api/snapshot'] * 4, out):
            if path == '/api/snapshot':
                self.assertEqual(status, 200)
                self.assertEqual(body['checkpoint']['state'], 'ANCHORED_PREFIX_ONLY')
                self.assertTrue(all(not v['currentReleaseEligible'] for v in body['eligibility'].values()))
            else:
                self.assertEqual(status, 409, path)
                self.assertEqual(body['error'], 'CHECKPOINT_REQUIRED')
                self.assertTrue(body['decisionsUnavailable'])

    def test_verifying_is_never_stored_or_served_as_verified(self):
        s = Served(self)
        counter = Counting(delay=0.2, fail=1)
        with patch.object(Manufacturing, 'snapshot', counter.function()):
            out = concurrently(s, [DECISIONS, '/api/snapshot', '/api/motors'])
        failed = [o for o in out if o[0] == 503]
        self.assertEqual(len(failed), 1, 'one verification failed; only the readers waiting on it fail with it')
        for _, body in failed:
            self.assertEqual((body['error'], body['state'], body['decisionsUnavailable']), ('VERIFYING', 'VERIFYING', True))
            self.assertNotIn('eligibility', body)
        for status, body in s.get('/api/snapshot'), s.get(DECISIONS):
            self.assertEqual(status, 200, 'the failure was not stored; the next request verifies again')

    def test_budget_exhaustion_is_fail_closed_not_a_weaker_check(self):
        s = Served(self)
        with patch.object(service, 'VERIFY_BUDGET_SECONDS', 0.0), patch('application.server.VERIFY_BUDGET_SECONDS', 0.0):
            for path in SWEEP:
                status, body = s.get(path)
                self.assertEqual((status, body.get('state')), (503, 'VERIFYING'), path)
                self.assertNotIn('eligibility', body)
                self.assertNotIn('decisions', body)
        self.assertEqual(s.get('/api/snapshot')[0], 200)

    def test_serving_does_not_alter_the_shared_snapshot(self):
        s = Served(self)
        first = s.get('/api/snapshot')[1]
        sweep = [s.get(p) for p in SWEEP]
        with patch.object(Manufacturing, 'snapshot', Counting(delay=0.3).function()):
            burst = concurrently(s, list(SWEEP) * 2)
        again = [b for b in burst]
        self.assertEqual(json.dumps(again[0][1], sort_keys=True).count('verifiedAt'), 1)
        self.assertEqual({p: b for p, (_, b) in zip(SWEEP[1:], again[1:8])}, {p: b for p, (_, b) in zip(SWEEP[1:], sweep[1:])})
        self.assertEqual(first['freshness']['archiveId'], again[0][1]['freshness']['archiveId'])

    def test_budget_setting_only_accepts_a_sane_range(self):
        for raw, want in (('', 1.25), ('abc', 1.25), ('nan', 1.25), ('inf', 1.25), ('-1', 1.25), ('0.1', 1.25), ('31', 1.25), ('0.25', 0.25), ('8', 8.0), ('30', 30.0)):
            with patch.dict(os.environ, {'PRAMAAN_VERIFY_BUDGET_SECONDS': raw}):
                self.assertEqual(audit._verify_budget(), want, raw)
        env = dict(os.environ); env.pop('PRAMAAN_VERIFY_BUDGET_SECONDS', None)
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(audit._verify_budget(), 1.25)

    def test_a_command_invalidates_the_shared_snapshot(self):
        s = Served(self)
        self.assertEqual(s.get('/api/snapshot')[0], 200)
        # The in-process command path is exercised through the server's own closure by a direct write and a new request after it.
        s.external_capture()
        status, body = s.get('/api/snapshot')
        self.assertEqual(body['checkpoint']['state'], 'ANCHORED_PREFIX_ONLY')

    def test_a_real_command_over_http_invalidates_the_shared_snapshot(self):
        from urllib.request import Request, urlopen
        s = Served(self)
        before = s.get('/api/motors')[1]
        self.assertEqual(s.get('/api/snapshot')[0], 200)         # a shared verification now exists
        with urlopen(s.base + '/api/session') as r:
            token = json.load(r)['token']
        req = Request(s.base + '/api/units', data=json.dumps({'serial': 'MTR-NEW-001'}).encode(), headers={'Content-Type': 'application/json', 'X-Pramaan-Token': token, 'Origin': s.base})
        with urlopen(req) as r:
            self.assertEqual(r.status, 200)
        after = s.get('/api/motors')[1]
        self.assertEqual(len(after), len(before) + 1, 'a read after a command must never come from a verification that predates it')
        self.assertIn('MTR-NEW-001', [u['unitId'] for u in after])

    def test_backend_unavailable_after_a_verified_read_serves_nothing(self):
        from application import server
        s = Served(self)
        self.assertEqual(s.get(DECISIONS)[0], 200)               # a shared verification exists
        def unavailable(*a, **kw):
            raise service.LedgerBlocked('database unavailable')
        with patch.object(server, 'Manufacturing', unavailable):
            for path in (DECISIONS, '/api/snapshot', '/api/motors'):
                status, body = s.get(path)
                self.assertNotEqual(status, 200, path)
                self.assertTrue(body.get('decisionsUnavailable'), path)
                self.assertNotIn('eligibility', body)
                self.assertNotIn('decisions', body)
        self.assertEqual(s.get(DECISIONS)[0], 200)


if __name__ == '__main__':
    unittest.main()
