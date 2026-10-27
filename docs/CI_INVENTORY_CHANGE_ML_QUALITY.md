# Inventory change: advisory ML quality inspection

Base: unified candidate with history consistency `7145f65`; ML commit `e36515d` cherry-picked without conflicts.

Frontend only. New pins (11): `stitch-nextjs/ml/DATASET.md`, `ml/train.mjs`, `ml/data/Faults.NNA`, `ml/data/Faults27x7_var`, `ml/data/heldout.csv`, `public/ml/model.json`, `public/ml/samples.json`, `src/ml/forest.ts`, `src/ml/input.ts`, `src/app/(dashboard)/dashboard/ml-inspection/page.tsx`, `tests/ml.test.ts`, `tsconfig.mltest.json` (12 files). Re-pinned (4, none among the original 449): `.gitignore`, `package.json` (two npm scripts), `src/app/(dashboard)/dash.css` (one scoped `.ml` block), `src/dash/ui.tsx` (one navigation entry).

No backend, evaluator, ledger, checkpoint, shipment, gate or history-consistency file changes. The page only issues GET requests for two static files; it creates no ledger event and has no write path. Model and data provenance: `stitch-nextjs/ml/DATASET.md` (UCI 198, CC BY 4.0; the unlicensed reference repository is not used).
