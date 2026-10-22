import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "../styles.css";
import "./passport.css";
import { PassportApp } from "./PassportApp";
import { LivePassportSource, PreviewPassportSource } from "./passportSource";

// Explicit opt-in only. The default is the live backend; a failed backend never switches to preview data.
const source = new URLSearchParams(location.search).get("mode") === "preview" ? new PreviewPassportSource() : new LivePassportSource();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <PassportApp source={source} />
  </StrictMode>,
);
