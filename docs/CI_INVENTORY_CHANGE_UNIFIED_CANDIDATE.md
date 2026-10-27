# Reviewed unified inventory change

Design base d90306c07b52b839ece5296d7cd4869f55a3bd4d; compatibility source 93f31f9366afba098c9d320f621ee5c793f535f0.

449 -> 528 entries. All original 449 pins unchanged, zero removals. Protected verification: {"baseline": "4a9e8f2c11e5e12bfd6926bfb9f9a0ee0dd3fa57", "files": 126, "engineTreeUnmodified": true, "foundationTreeUnmodified": true, "integrationTreeUnmodified": true}. Added paths are the same 79 reviewed paths from the compatibility candidate. Compared with that candidate, the following newly registered frontend/test entries reflect the approved design or explicit test-only history investigation. No original runner, expected test count, assertion or original test was changed. Compatibility now runs 30 Node and 14 component checks separately; the 14th characterizes an unresolved defect and is not proof of remediation.

- `compatibility/run.py`
- `compatibility/tests/unified.test.tsx`
- `stitch-nextjs/src/app/(dashboard)/dash.css`
- `stitch-nextjs/src/app/(dashboard)/dashboard/evidence/page.tsx`
- `stitch-nextjs/src/app/(dashboard)/dashboard/genealogy/page.tsx`
- `stitch-nextjs/src/app/(dashboard)/dashboard/impact/page.tsx`
- `stitch-nextjs/src/app/(dashboard)/dashboard/page.tsx`
- `stitch-nextjs/src/app/(dashboard)/dashboard/passport/page.tsx`
- `stitch-nextjs/src/app/(dashboard)/dashboard/performance/page.tsx`
- `stitch-nextjs/src/app/(dashboard)/dashboard/recall/page.tsx`
- `stitch-nextjs/src/app/(landing)/page.tsx`
- `stitch-nextjs/src/dash/ImpactParts.tsx`
- `stitch-nextjs/src/landing/landing.src.css`
- `stitch-nextjs/tailwind.landing.config.cjs`
