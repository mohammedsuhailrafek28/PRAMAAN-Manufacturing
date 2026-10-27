# Recall blast-radius simulator and motion (Impact workspace)

**Simulate impact** on the Impact page opens a read-only, hypothetical simulator. It reuses the existing genealogy projection (`projectImpact` -> `ImpactGraph`, built from ledger fields only) and adds a pure directed traversal (`src/dash/simulate.ts`). No dataset, node or edge is added.

- Reach levels: CONFIRMED (every link recorded), CLAIMED (recorded lot claim), NOT COUNTED (conflicting or untrusted links only). Traversal follows edge direction; cycles and duplicate paths are collapsed.
- Zero known exposure is reported as such, never as safe. Motors with no recorded path are listed as absence of a record.
- Engine decisions are shown only when the original strict gate is current and are copied, not recomputed. Otherwise "Withheld". A changed snapshot epoch re-runs the result with a notice; a withdrawn gate withdraws the page.
- Everything is labelled HYPOTHETICAL — INVESTIGATION ONLY; the simulator writes nothing and issues no request of its own.

Motion: from `cb5d6d2` only `reveal.ts`, landing smooth anchors and Overview reveals (plus a scroll fallback so a block jumped past is never left hidden), and `src/motion/scroll.ts` for smooth movement to the simulator results. Warnings, banners, KPIs, decisions and errors are never animated; reduced motion disables all of it.
