import { createContext, useContext } from "react";

/**
 * Console-only: which motors currently hold verified release clearance.
 * `null` (no provider) means the console is showing labelled fixture data, never a live ledger, so a recorded
 * action is shown as recorded. A live provider is built from the gate's CURRENT snapshot and answers per motor.
 */
export type ClearanceLookup = ((unitId: string | undefined) => boolean) | null;

const Ctx = createContext<ClearanceLookup>(null);
export const ClearanceProvider = Ctx.Provider;
export const useClearance = (): ClearanceLookup => useContext(Ctx);
