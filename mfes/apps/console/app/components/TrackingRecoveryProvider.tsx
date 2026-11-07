'use client';
import { createContext, useContext, type ReactNode } from 'react';
const Context = createContext<string | undefined>(undefined);
export function TrackingRecoveryProvider({ scope, children }: { scope?: string; children: ReactNode }) {
  return <Context.Provider value={scope}>{children}</Context.Provider>;
}
export const useTrackingRecoveryScope = () => useContext(Context);
