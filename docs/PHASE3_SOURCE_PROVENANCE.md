# Phase 3 repository audit and source provenance

Audit date: 2026-10-21. Destination: https://github.com/mohammedsuhailrafek28/PRAMAAN-Manufacturing. Source: https://github.com/mohammedsuhailrafek28/HORIZONXT-PS10. This is Manufacturing PRAMAAN; no MSME repository was accessed or modified.

The destination had no Git refs or application content at audit. A documentation-only baseline (`8f1a79d`) established destination `main`, as authorized for an empty destination. Application work is isolated on `phase3/unified-application`; it has not been merged into main or deployed.

| Source branch | Verified commit |
| --- | --- |
| `feature/slot-attribution-safety` | `1620ed3a8c78d7ea41063107666d9482fd93dff9` |
| `feature/recall-investigation-ui` | `be20c17a789471c3149d34ec317a329442b98cd1` |
| `feature/epcis-recall-integration` | `ea2eee797dfceafec6b7ef2da4d5e55b7584e2f4` |
| `research/open-source-foundation` | `bc68dc0ca54f4e35b7e14c6ad09f7af28ab3b00c` |

Both fetched commit objects and remote branch heads were checked against these pins. Destination merge commits `8bcbe45` and `1c009e4` preserve original source histories, author metadata and attribution. No upstream OpenEPCIS, Trace-X or Industry Core Hub repository was merged. Source branches, worktrees, engine, fixtures and oracle are untouched. The engine and original foundation experiment trees match their pinned source commits; no duplicate evaluator exists.

The Phase 3 addition uses the in-repository original Python profile, SQLite ledger and bridge, extending the profile with provenance-only material allocation, bearing manufacture and shipment claims. The bridge calls the pinned actual v3 evaluator. UI changes retain the original RecallDataSource seam, fixture exporter and fixture snapshot. Two accidentally tracked UI Python bytecode files are removed from the destination only. Git attributes preserve deterministic LF inputs and explicitly preserve the engine's historical CRLF validation artifact byte-for-byte.

No license-blocked upstream Java source was copied. Runtime Python dependencies are `jsonschema`, `rfc8785`, `attrs`, `jsonschema-specifications`, `referencing`, `rpds-py` (MIT/Apache-2.0 family as recorded in the foundation evaluation), plus the now-explicit transitive pin `typing-extensions==4.16.0` (installed metadata: PSF-2.0). React/React DOM remain the UI's existing MIT runtime dependencies; npm's committed lockfile is retained. Preserve all applicable package notices in distribution. The repository's own overall project license has not been newly assigned by this integration.

The external GS1 checkout used for validation is `gs1/EPCIS` commit `6f71468231838e424bb5dfa836e006e8dc69615c`. It is not vendored or distributed. Schema SHA-256: `d5ca9b1cad2c403679d9b07fb768108142d73e1dd024198ed64774b56b62227b`; JSON-LD context SHA-256: `b5c7cc9367ab638ecb77feb0b9aea222a427d9740bf3dda1b183fc3d4390714f`. Validation tooling dependencies remain separate from runtime. Upstream licensing conclusions and unresolved rights questions remain in [the foundation evaluation](OPEN_SOURCE_FOUNDATION_EVALUATION.md).

No secrets, proprietary assets or factory datasets are included. All new supplier names, motors, bearing serials, lots, shipments and operator evidence are explicitly synthetic.
