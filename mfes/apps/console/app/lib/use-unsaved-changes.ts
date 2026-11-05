'use client';

import { useLayoutEffect } from 'react';

export const BEFORE_COMPANY_CHANGE = 'janso:before-company-change';

/** Check editors before changing HttpOnly context cookies: a cancelled reload is too late. */
export function useUnsavedChanges(isDirty: () => boolean) {
  // Update before paint: context changes must see the committed draft/save state.
  useLayoutEffect(() => {
    const blockChange = (event: Event) => { if (isDirty()) event.preventDefault(); };
    const warn = (event: BeforeUnloadEvent) => {
      if (isDirty()) { event.preventDefault(); event.returnValue = ''; }
    };
    window.addEventListener(BEFORE_COMPANY_CHANGE, blockChange);
    window.addEventListener('beforeunload', warn);
    return () => {
      window.removeEventListener(BEFORE_COMPANY_CHANGE, blockChange);
      window.removeEventListener('beforeunload', warn);
    };
  }, [isDirty]);
}
