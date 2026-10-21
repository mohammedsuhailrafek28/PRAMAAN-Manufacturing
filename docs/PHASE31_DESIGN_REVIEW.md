# Phase 3.1 visual design review

Date: 2026-10-21. Artifact: `recall-ui/src`.

Outcome: **ship for the scoped visual review**. The finish reviewer reported no material visual blockers in the six captures below. Phase 3.1 extends the incumbent operational interface with explicit recall positions, visible verification freshness and failure states, identifier wrapping, and a keyboard-focusable genealogy scroller.

## Scope and authority

This is an ordinary safety-remediation extension of Recall Investigation. `PRODUCT.md` is absent; the incumbent implementation and the task direction supply design authority. Existing operational hierarchy, semantic colors, and components remain authoritative. This handoff introduces no visual identity, root `DESIGN.md`, or design sidecar.

The documentation pass read the Impeccable document reference, the previous Phase 3 review, and current source in `styles.css` and `App.tsx`; targeted source searches covered recall-position controls and the genealogy region. It verified that the capture files exist. It did not open a browser, independently inspect the images, modify runtime code, run accessibility or backend tests, or deploy the application. Visual acceptance below is attributed to the finish reviewer rather than presented as a new browser verification.

## Captured scope

The finish reviewer inspected desktop at 1440px, backend-offline presentation at 1280px, and mobile at 390px. The supplied review covers these exact captures in `docs/phase31-screenshots`:

| Capture | Reviewed surface |
| --- | --- |
| [Live fleet](phase31-screenshots/phase3-live-fleet.png) | Desktop operational fleet, provenance, and live verification presentation. |
| [Mobile decision](phase31-screenshots/mobile-decision.png) | Narrow-screen unit decision and distinct finding/action/review presentation. |
| [Backend offline](phase31-screenshots/backend-offline.png) | Failure presentation when current backend evidence is unavailable. |
| [Mobile history](phase31-screenshots/mobile-history.png) | Narrow-screen decision history and long evidence identifiers. |
| [Mobile genealogy](phase31-screenshots/mobile-genealogy.png) | Narrow-screen genealogy container and graph presentation. |
| [Mobile capture](phase31-screenshots/phase3-mobile-capture.png) | Narrow-screen manufacturing capture workflow and recall-position controls. |

Other files in the screenshot directory are outside this six-capture acceptance record. Screenshots show particular UI states; they do not prove correctness of recall evaluation, backend durability, verification timing, release authorization, physical origin, or all responsive widths.

## Incumbent tokens and components preserved

- The existing light palette retains the gray canvas (`--bg: #f1f3f6`), white surfaces, dark text (`--text: #17202b`), dark header (`--head-bg: #1c2733`), blue link/focus accent (`--accent: #0a559c`), and muted border/text tokens. Existing dark-mode overrides remain in source; this handoff does not claim dark-theme visual verification.
- Semantic state families remain red for affected findings, amber for unresolved findings and warnings, green for evidence-backed exclusion, strongly contrasting recall holds, and purple synthetic markers. Finding, operational action, and review remain separate labeled chips. Release eligibility retains its dashed boundary; review-required retains its double boundary.
- Body typography remains `15px/1.5 system-ui, "Segoe UI", Roboto, sans-serif`; identifiers use `ui-monospace, Consolas, monospace`. The main column retains its 1200px maximum and 16px padding. Header and control groups wrap within the existing layout.
- Bordered panels, compact tables, tabs, callouts, timeline markers, native disclosure/fieldset controls, and small control corners remain the component vocabulary. Responsive tables continue to become labeled blocks at the existing 720px breakpoint. Workbench controls retain 42px minimum height and stack on mobile.
- The interface continues to use borders and surface contrast for structure. The selected tab retains its inset accent; this remediation does not replace the incumbent depth or shape language.

## Remediation presentation

Recall-position selection explicitly offers both DE and NDE as the conservative default, with DE-only and NDE-only choices labeled as explicit restrictions. It reuses the existing labeled select within the capture workspace.

Live mode exposes the successful local verification timestamp, five-second lease, and two-second refresh interval in a status message. Source gates current decision views on a valid lease and presents a prominent error panel when loading or validation fails. The error copy distinguishes earlier decisions as historical evidence rather than currently verified operational clearance. These are source-observed behaviors; the offline capture supports the visual failure presentation, not exhaustive timing or race-condition verification.

Long identifiers wrap through the existing monospace treatment and targeted containment rules: the main area and panels permit wrapping, panel tables use a fixed layout, and preformatted panel content wraps. Genealogy retains horizontal scrolling. Its region has a unit-specific accessible name, `tabIndex={0}`, and the existing three-pixel accent focus outline. Source establishes focusability and overflow styling; static captures do not establish successful keyboard scrolling, touch interaction, screen-reader announcements, or complete assistive-technology usability.

## Retained observations and limits

Inherited detector warnings at `recall-ui/src/styles.css` lines 41, 106, and 109 are retained as reported in this review cycle. The warning and side-tab/panel conventions belong to the incumbent interface and were not treated as authorization for redesign. Native button rendering and existing one-off values remain incumbent characteristics.

The finish review supports scoped visual shipment with no material blockers in the six listed captures. Cross-browser behavior, uncaptured states and widths, dark theme, keyboard interaction, and backend safety guarantees require their own evidence; none is certified by this documentation handoff. No runtime changes are proposed here.
