# Deployment bundle (synthetic demonstration data)

`ledger-bundle/` holds the four reference-ledger files of the approved 47-event, 9-motor demo ledger (archive `8322f95011cc4e6d83c7d9e17cd6c01a`, sequence 10, checkpoint ANCHORED_CURRENT).
They are a byte-exact consistent copy (SQLite backup, logically identical to the running reference) of `review2.demo prepare`'s output. `manifest.json` has its local paths replaced by file names.
`SHA256SUMS` is verified by `start.sh` before every start; `IDENTITY.json` is checked against the live backend by `wait_ready.py`. A mismatch stops the container (fail closed).

The reference is a **self-exported demo checkpoint, not independent custody, external anchoring or release authorization.** All data are synthetic.

Persistence: the ledger is copied to a writable ephemeral directory on every start (SQLite WAL needs a writable directory). No state is written that must survive a restart; a restart restores the identical archive from the bundle.

Rebuilding the bundle changes the archive id (it is random per `prepare`); do not regenerate it casually. Publicly exposed: only the Next.js port. The backend binds 127.0.0.1 and refuses foreign Host headers.
Run `python deploy/check_release.py` before every release.
