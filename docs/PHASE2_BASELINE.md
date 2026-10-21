# Phase 2 baseline and contract gate

Pinned engine: `1620ed3a8c78d7ea41063107666d9482fd93dff9` (127 tests pass,
including v1/v2/v3 oracle, replay and safety mutation tests). Pinned foundation:
`bc68dc0ca54f4e35b7e14c6ad09f7af28ab3b00c` (21 checks pass independently).
Research changes were cherry-picked into a new branch based on the engine pin;
neither source branch nor the UI worktree is modified.

Gate: GO for a narrow integration without engine changes. No safety rule may be
disabled. New evaluations always use `Config.v3()`; replay uses the stored profile.

Contract differences and handling:

* EPCIS does not mandate motor slots, producer sequence, trusted verification,
  coverage sessions or work-order reconciliation. A versioned private trace
  profile supplies explicit native fields; incomplete records are rejected.
* Engine comparison assumes UTC `YYYY-MM-DDTHH:MM:SSZ`. Other timestamp forms
  are rejected in this profile, not rounded or silently normalized. Calendar
  validity and producer-recorded-at >= occurred-at are checked independently.
* Engine integrity checks are per motor, but real factory station sequences can
  span many motors. This slice requires explicitly motor-scoped producer streams
  and preserves IDs/sequences exactly. Global-station streams require another
  completeness contract; no local renumbering is permitted.
* Repository `recordTime` is separate from producer `recordedAt`. Both original
  EPCIS bytes and a local receipt timestamp are preserved.
* Source/actor permissions, capture sessions and coverage policy come from trusted
  caller configuration, not event-supplied assertions. A permitted handheld source
  is not promoted to a trusted verifier. The v3 evaluator decides independence.
* Structural contradictions (core fields vs trace, missing references, malformed
  sequence/hash) reject capture and persist a motor-level evaluation block.
  Coherent claims of conflicting physical operations (double install, ambiguous
  removal) remain immutable evidence and are held by the unchanged evaluator.
  Silently discarding such claims would hide risk.
* The native engine has no signature/hash input. The integration verifies an
  append-only evidence manifest before invoking it; hashes do not authenticate
  a physical observation. Source authorization here is a local caller capability,
  not a deployed identity/credential system.
* Explicit source watermarks must resolve complete prefixes, including a source
  with no retrieved rows. Never infer completeness from a component-only query.
* Use self-authored restricted-profile validation plus `jsonschema` (MIT) and
  `rfc8785` (Apache-2.0); no blocked upstream source, GS1 schema redistribution,
  Java runtime service, or full platform is necessary. Existing external GS1
  conformance checks remain a separate research gate.
