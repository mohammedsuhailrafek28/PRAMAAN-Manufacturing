# CI inventory change: single-container deployment preparation

Branch `deploy/ps10-render`, based on `feature/ps10-blast-radius` @ `0f99bfd`.

Added: `Dockerfile`, `.dockerignore`, `render.yaml` (Blueprint, not applied), `deploy/start.sh`, `deploy/wait_ready.py`, `deploy/check_release.py`, `deploy/README.md`, and `deploy/ledger-bundle/` (four checksummed synthetic reference-ledger files, `SHA256SUMS`, `IDENTITY.json`).
Changed: `.gitattributes` (bundle is stored byte-exact, `-text`) and `stitch-nextjs/src/app/api/[...path]/route.ts` (one allowlist line removed: `GET /api/session`, which returned the backend write token, is no longer proxied; the frontend never used it).

No change to the evaluator, genealogy, simulator, ML model, assistant rules, evidence integrity, recall logic, gates or tests. The reference checkpoint is a self-exported demo reference, not independent custody or external anchoring.
