/** Smooth movement to a section the person just asked for. Native scrolling only; instant when reduced motion is requested. Never delays content. */
export function reducedMotion(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function smoothTo(el: Element | null | undefined): void {
  if (!el) return;
  el.scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block: "start" });
  if (el instanceof HTMLElement) el.focus({ preventScroll: true });
}
