import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "../styles.css";
import "./impact.css";
import { ImpactApp } from "./ImpactApp";
import { LiveImpactSource, PreviewImpactSource } from "./impactSource";

// Explicit opt-in only. The default is the live backend; a failed backend never switches to preview data.
const params = new URLSearchParams(location.search);
const preview = params.get("mode") === "preview";
const dataset = params.get("dataset") ?? "de";
const links = [
  { id: "de", label: "Recall scope: DE position", href: "?mode=preview&dataset=de#/" },
  { id: "nde", label: "Recall scope: NDE position", href: "?mode=preview&dataset=nde#/" },
  { id: "large", label: "Large stress data (authored)", href: "?mode=preview&dataset=large#/" },
];

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ImpactApp source={preview ? new PreviewImpactSource(dataset) : new LiveImpactSource()} datasetLinks={preview ? links : undefined} />
  </StrictMode>,
);
