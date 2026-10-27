# Frozen-source inventory change — Ask PRAMAAN local rule engine

Replaces the Gemini adapter with a local rule engine: removes `src/ask/llm.ts`; adds `src/ask/answer.ts`; re-pins `src/ask/{ground,handler}.ts`, `AskWidget.tsx`, `src/app/api/ask/route.ts`, `tests/ask.test.ts`, `tsconfig.asktest.json`. No evaluator, checkpoint, shipment-gate, identity-guard, ML-model or history-consistency file is changed; no check is weakened.

Final integration note: the assistant files were re-pinned from the integration worktree's own bytes (line-ending normalisation by git on cherry-pick); content is identical to feature/ps10-ask-local da8e3d8.
