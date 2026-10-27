# CI inventory change: dashboard LEASE_EXPIRED flicker

Branch `fix/ps10-lease-flicker`, based on the deployed release `f2900f5`.

Changed: `stitch-nextjs/src/dash/data.tsx` (snapshot polling loop only). Added: `stitch-nextjs/src/dash/lease.ts` (two pure functions), `stitch-nextjs/tests/lease.test.ts` (9 tests), `stitch-nextjs/tsconfig.leasetest.json`. Ignore files list the test build directory.

Behaviour: (1) the next snapshot request starts when the previous one ends if it ran longer than 2 s (previously the ticks that fell inside a slow request were skipped), otherwise 2 s after it started. (2) A response that the strict gate rejects ONLY on freshness (cause LEASE_EXPIRED) is still not accepted and its body is never shown, but it no longer revokes a lease that an earlier accepted response still holds; that lease ends at the instant it always did and is never extended.

Not changed: the gate (`src/orig/contract/gate.ts`), the 5 s lease, the 1 s future-stamp allowance, prefix-only, unanchored, VERIFYING, anchor-invalid, regression and transport handling, the backend, the proxy, any decision or evidence.
