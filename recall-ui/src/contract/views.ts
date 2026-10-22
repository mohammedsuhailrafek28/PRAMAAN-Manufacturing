// The only way a page turns a branded view into projections. The projection cores are unchanged apart from
// carrying hold / clearance separately; they run over the view's internal snapshot, which only this module
// may unwrap (static test). A HistoricalView cannot reach a decision projection: the types refuse it, and
// the functions throw if a cast gets one through.
import { buildImpactGraph, lotChoices, type BuildOptions as ImpactOptions, type ImpactGraph, type Selection } from "../impact/projection";
import { buildInvestigation, type InvestigationView } from "../investigation/projection";
import { buildPassport, type PassportResult } from "../passport/projection";
import { assertGated, assertView, clearanceOf, isGated, isHistorical, isPreview, NotBranded, rawSnapshotOf, type GatedSnapshot, type HistoricalView, type PageView, type PreviewView } from "./gated";

export type ImpactMode = "current" | "preview" | "noncurrent";

/** `leaseOk` is the page's own lease/visibility state; current recall context needs both a GatedSnapshot and a live lease. */
export function projectPassport(view: PageView, unitId: string, o: { leaseOk: boolean; unavailableReason: string }): PassportResult {
  assertView(view);
  const current = isGated(view) && o.leaseOk;
  return buildPassport(rawSnapshotOf(view), unitId, {
    recallVerified: current,
    unavailableReason: o.unavailableReason,
    ...(isGated(view) ? { clearance: (u: string) => clearanceOf(view, u) } : {}),
    ...(isPreview(view) ? { previewRecorded: true } : {}),
  });
}

/** Investigation tasks are claims about the current decision: only a GatedSnapshot or an explicit preview may build them. */
export function projectInvestigation(view: GatedSnapshot | PreviewView): InvestigationView {
  assertView(view);
  if (isHistorical(view)) throw new NotBranded("a HistoricalView cannot build investigation tasks");
  return buildInvestigation(rawSnapshotOf(view), isGated(view) ? { clearance: (u) => clearanceOf(view, u) } : { previewRecorded: true });
}

export function projectImpact(view: PageView, selection: Selection, o: { mode: ImpactMode }): ImpactGraph {
  assertView(view);
  if (o.mode === "current") assertGated(view);
  if (o.mode === "preview" && !isPreview(view)) throw new NotBranded("preview mode needs a PreviewView");
  const opts: ImpactOptions = { recallStatusCurrent: o.mode !== "noncurrent" };
  if (o.mode === "current" && isGated(view)) opts.clearance = (u) => clearanceOf(view, u);
  if (o.mode === "preview") opts.previewRecorded = true;
  return buildImpactGraph(rawSnapshotOf(view), selection, opts);
}

export function lotChoicesOf(view: PageView): ReturnType<typeof lotChoices> {
  assertView(view);
  return lotChoices(rawSnapshotOf(view));
}

export type { GatedSnapshot, HistoricalView, PageView, PreviewView };
