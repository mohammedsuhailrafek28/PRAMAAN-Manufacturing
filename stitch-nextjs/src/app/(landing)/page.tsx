import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { Metadata } from "next";
import LandingBehavior from "./LandingBehavior";

export const metadata: Metadata = {
  title: "PRAMAAN — Industrial Traceability & Digital Product Passport",
};

// Markup of the approved Stitch landing page (pramaan_landing_page_with_live_three.js_exploded_gearbox/code.html), unmodified except the final call to action,
// which now opens the dashboard. Static, trusted, repository-owned markup (no user input).
const markup = readFileSync(join(process.cwd(), "src/landing/landing.body.html"), "utf8");

export default function LandingPage() {
  return (
    <>
      <link rel="preconnect" href="https://fonts.googleapis.com" />
      <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
      <link
        rel="stylesheet"
        href="https://fonts.googleapis.com/css2?family=Unbounded:wght@400;500;600&family=Hanken+Grotesk:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap"
        precedence="default"
      />
      <link rel="stylesheet" href="/landing/landing.css" precedence="default" />
      <div
        className="landing-root bg-[#f5faff] font-sans text-brand-slate antialiased min-h-screen selection:bg-brand-cyan/20 selection:text-brand-graphite"
        dangerouslySetInnerHTML={{ __html: markup }}
      />
      <LandingBehavior />
    </>
  );
}
