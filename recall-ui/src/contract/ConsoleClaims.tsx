import {createContext, useContext, useMemo, type ReactNode} from "react";
import type {GatedSnapshot} from "./gated";
import {consoleClaims} from "./views";
import type {RecordedClaim} from "./clearance";

const Context = createContext<{claims: ReturnType<typeof consoleClaims> | null; preview: boolean}>({claims:null, preview:false});
export function ConsoleClaimsProvider({view, preview, children}: {view: GatedSnapshot | null; preview:boolean; children:ReactNode}) {
 const claims=useMemo(()=>view ? consoleClaims(view) : null,[view]);
 return <Context.Provider value={{claims,preview}}>{children}</Context.Provider>;
}
export function useConsoleClaims(){return useContext(Context);}
export function useConsoleClaim(decisionId:string): RecordedClaim | undefined {return useConsoleClaims().claims?.byDecision.get(decisionId);}
