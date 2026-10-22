import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "../styles.css";
import "./investigation.css";
import { InvestigationApp } from "./InvestigationApp";
import { LiveInvestigationSource, PreviewInvestigationSource } from "./investigationSource";

// Explicit opt-in only. The default is the live backend; a failed backend never switches to preview data.
const params = new URLSearchParams(location.search);
const preview = params.get("mode") === "preview";
const stage = params.get("stage") ?? "before";
const stageLinks = [
  { id: "before", label: "Before the evidence update", href: "?mode=preview&stage=before#/" },
  { id: "after", label: "After the evidence update", href: "?mode=preview&stage=after#/" },
];

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <InvestigationApp source={preview ? new PreviewInvestigationSource(stage) : new LiveInvestigationSource()} stageLinks={preview ? stageLinks : undefined} />
  </StrictMode>,
);
