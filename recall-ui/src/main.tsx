import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { FixtureSnapshotSource } from "./data/RecallDataSource";
import "./styles.css";

// Swap this one line to point the UI at a different RecallDataSource.
const source = new FixtureSnapshotSource();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App source={source} />
  </StrictMode>,
);
