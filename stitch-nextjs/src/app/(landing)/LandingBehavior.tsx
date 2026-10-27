"use client";

import { useEffect } from "react";
import { initReveal } from "@/motion/reveal";

/**
 * Loads the landing page's original classic scripts in the original order (Three.js r125, then the page script)
 * so the exploded-gearbox scene, reveal-on-scroll, token tabs and audit filter run exactly as in the approved Stitch file.
 * The original page script was written for a document that is still loading: its gearbox scene starts immediately when `readyState` is not "loading", but the token
 * tabs, wire/solid mode buttons and reveal-on-scroll register `DOMContentLoaded` handlers. React hydrates after that event, so it is replayed once after the
 * scripts load. A window flag keeps the scene from starting twice (React strict-mode double effects); the landing's links leave via full page loads.
 */
export default function LandingBehavior() {
  useEffect(() => {
    const flags = window as unknown as { __pramaanLanding?: boolean };
    document.documentElement.classList.add("scroll-smooth");
    const stopReveal = initReveal([...document.querySelectorAll(".reveal-item")], { skipCritical: true });
    const cleanup = () => { stopReveal(); document.documentElement.classList.remove("scroll-smooth"); };
    if (flags.__pramaanLanding) return cleanup;
    flags.__pramaanLanding = true;
    const added: HTMLScriptElement[] = [];
    const load = (src: string) =>
      new Promise<void>((resolve, reject) => {
        const s = document.createElement("script");
        s.src = src;
        s.async = false;
        s.onload = () => resolve();
        s.onerror = () => reject(new Error(`failed to load ${src}`));
        document.body.appendChild(s);
        added.push(s);
      });
    (async () => {
      try {
        if (!(window as unknown as { THREE?: unknown }).THREE) await load("/landing/three.min.js");
        await load("/landing/landing-scene.js");
        document.dispatchEvent(new Event("DOMContentLoaded"));
      } catch (error) {
        console.error(error);
      }
    })();
    return cleanup;
  }, []);
  return null;
}
