/**
 * Scroll-triggered fade-and-rise for noncritical blocks. Content is visible by default: the hidden state (`mo-rv`) is only ever added
 * from script, only to blocks that are still below the fold, and only when IntersectionObserver exists and reduced motion is not requested.
 * Blocks that hold safety or decision content are never touched (see `isCritical`). If the observer never reports, a timer reveals everything. Movement is a transform only, so nothing reflows.
 */
const CRITICAL = /recall|hold|caution|warning|awaiting|suspect|stale|fresh|withheld|not claimed|unresolved|ambiguous|checkpoint|anchor/i;
const STAGGER_MS = 70;
const MAX_STEPS = 3;
const FAILSAFE_MS = 1200;

export const isCritical = (el: Element): boolean => el.matches("[data-motion='critical']") || !!el.querySelector("[data-motion='critical']") || CRITICAL.test(el.textContent ?? "");

export function motionAllowed(): boolean {
  if (typeof window === "undefined" || !("IntersectionObserver" in window)) return false;
  return !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function initReveal(els: Element[], opts: { skipCritical?: boolean } = {}): () => void {
  if (!motionAllowed()) return () => {};
  const fold = window.innerHeight * 0.92;
  const targets = els.filter((el) => el.getBoundingClientRect().top > fold && !(opts.skipCritical && isCritical(el)));
  if (!targets.length) return () => {};
  targets.forEach((el) => el.classList.add("mo-rv"));
  let called = false;
  const io = new IntersectionObserver((entries) => {
    called = true;
    // blocks that enter together are staggered; one entering alone has no delay.
    entries.filter((e) => e.isIntersecting).forEach((e, i) => {
      (e.target as HTMLElement).style.setProperty("--mo-d", `${Math.min(i, MAX_STEPS) * STAGGER_MS}ms`);
      e.target.classList.add("mo-in");
      io.unobserve(e.target);
    });
  }, { threshold: 0.12, rootMargin: "0px 0px -40px 0px" });
  targets.forEach((el) => io.observe(el));
  // A reader who jumps past a block (End key, anchor link) never makes it intersect; release anything already above the viewport so nothing stays hidden.
  const released = new Set<Element>();
  const onScroll = () => { for (const el of targets) if (!released.has(el) && el.getBoundingClientRect().top < 0) { released.add(el); el.classList.add("mo-in"); io.unobserve(el); } };
  window.addEventListener("scroll", onScroll, { passive: true });
  // an observer reports every target once on creation; if it never does, show everything
  const t = window.setTimeout(() => { if (!called) targets.forEach((el) => el.classList.add("mo-in")); }, FAILSAFE_MS);
  return () => { window.removeEventListener("scroll", onScroll); io.disconnect(); window.clearTimeout(t); targets.forEach((el) => el.classList.add("mo-in")); };
}
