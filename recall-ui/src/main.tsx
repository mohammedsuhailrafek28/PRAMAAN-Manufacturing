import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { FixtureSnapshotSource, BackendRecallDataSource } from "./data/RecallDataSource";
import "./styles.css";

// Swap this one line to point the UI at a different RecallDataSource.
const source = new URLSearchParams(location.search).get("mode") === "fixtures" ? new FixtureSnapshotSource() : new BackendRecallDataSource();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App source={source} />
  </StrictMode>,
);
