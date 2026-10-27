# Phase 3 visual design review

Date: 2026-10-21. Artifact: `recall-ui/src`. Reference UI: pinned commit `be20c17`.

Outcome: the scoped manufacturing workspace and ledger-backed genealogy/provenance extension preserve the incumbent Recall Investigation interface. The finish reviewer reported its single material genealogy clipping issue resolved after recapture; the reviewed genealogy capture shows contained node text and a fully visible shipment node. No further material visual issue was identified in the supplied evidence.

## Scope and authority

This is an ordinary extension of an operational interface, not a new visual system. The direction is one local Manufacturing PRAMAAN app with a durable SQLite ledger, actual v3 evaluation, explicit synthetic demo and fixture modes, safety holds, and clear evidence limits. `PRODUCT.md` is absent; the existing implementation and the task direction govern this handoff. No new brand, `DESIGN.md`, or `.impeccable/design.json` is introduced.

Review scope is visual only. Screenshots and UI copy demonstrate presentation, not backend correctness, physical-origin certification, release authorization, durability, or performance validation. No browser session, deployment, or runtime source modification was performed for this documentation handoff.

## Evidence checked

| Evidence | Visual observation |
| --- | --- |
| [Desktop live fleet](screenshots/phase3-live-fleet.png) | Existing dark header, provenance panel, collapsed capture workspace, notification callout, filters, fleet table, and separate finding/action/review chips remain legible. Synthetic/live-ledger labeling is prominent. |
| [Mobile capture](screenshots/phase3-mobile-capture.png) | Header wraps; workspace controls stack within fieldsets; fleet rows become labeled blocks. This capture includes a newly created sixth motor and therefore is a different application state from the five-motor desktop fleet capture. |
| [Desktop genealogy](screenshots/phase3-genealogy.png) | Supplier, component, motor, and shipment columns are visible. Long supplier/customer labels use ellipsis; source includes title text for their full values. Ledger-backed material claims and shipment evidence remain separate from decision chips. |
| [Desktop decision history](screenshots/phase3-history.png) | Version timeline retains superseded/current markers, evidence/action/review distinctions, and a visible warning when a prior exclusion is withdrawn. |

Source inspection covered `styles.css`, `App.tsx`, `ManufacturingWorkbench.tsx`, `ProvenanceBar.tsx`, and `GenealogyGraph.tsx`, with baseline diffs for styles, status chips, unit details, and decision history. The latter three have no changes against the pinned UI. The visual evidence is light theme; dark theme and mobile genealogy/history were not visually verified by this handoff.

## Incumbent system preserved

- Existing CSS variables retain the light gray canvas, white surfaces, dark text/header, blue links and focus accent, red affected state, amber unresolved/warning state, green evidence-backed exclusion, dark recall hold, and purple synthetic marker. The existing dark-mode variable overrides remain intact.
- System typography remains `15px/1.5 system-ui, "Segoe UI", Roboto, sans-serif`, with monospace evidence identifiers. The centered main container remains capped at 1200px with 16px padding.
- Existing bordered panels, compact tables, tabs, timeline, callouts, chips, and small control corners remain the component vocabulary. Finding, operational action, and review status are separate labeled components; release eligibility retains its dashed border and holds retain their strong contrast.
- The capture workspace reuses surface, border, text, and background tokens. Native details/summary and fieldsets keep the workflow grouped; 42px minimum controls and wrapping forms adapt to the existing 720px mobile breakpoint. Long evidence identifiers can wrap.
- Genealogy keeps the existing node/edge language and horizontal scrolling container. Removed/superseded records remain dashed; ledger-backed shipments and synthetic overlays receive distinct labeling. The graph explicitly states that records claim relationships and that slot reconciliation determines the decision.
- Provenance distinguishes live synthetic ledger data from synthetic fixture data and exposes the engine/profile, recall, policy, and source. Supporting event disclosures and notification obligations retain the existing disclosure/callout vocabulary.

## Correction and inherited observations

The visual correction scope was genealogy text containment: truncate long supplier, shipment, and customer labels with full text available in SVG titles, and keep the shipment column inside the graph canvas. The supplied recapture supports closure of the reported clipping issue. It does not establish keyboard, assistive-technology, or touch access to SVG title text; those need separate functional accessibility checks if required.

Inherited detector warnings at `recall-ui/src/styles.css` lines 40, 105, and 108 (the warning/side-tab styling findings reported during the prior review) are retained intentionally. They belong to the pinned interface and were not treated as permission to redesign its callout, tab, or panel conventions. Existing one-off values and native browser button rendering remain incumbent implementation characteristics rather than a newly normalized token system. No preexisting design drift was repaired as a side effect of this handoff.

No runtime changes are proposed by this document. The four supplied captures support the scoped visual acceptance above, with the stated theme and viewport coverage limits.
