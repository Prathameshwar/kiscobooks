'use client';
import { useEffect, useRef, useState } from 'react';
import { Notice } from '@janso/ui';
import { overviewRequest } from '../lib/company-overview';
import { requestFailure } from '../lib/service-call';
import type { components } from '@janso/api-client/reports';

type Readiness = components['schemas']['SourceReadiness'];
const messages = {
  PREPARING: 'Preparing your figures automatically. You can leave this page and return later.',
  CURRENT: 'Figures are up to date with the latest checked books.',
  UPDATING: 'Updating your figures. The last verified figures remain available.',
  DELAYED: 'Report updates are delayed. Preparation will retry automatically.',
  NEEDS_ACTION: 'Report preparation needs an administrator to review company readiness.',
};
export function AutomaticReportStatus({ company, onGeneration }: { company: string; onGeneration: () => void }) {
  const [state, setState] = useState<Readiness | null>(null);
  const callback = useRef(onGeneration); callback.current = onGeneration;
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let generation: string | null = null;
    setState(null);
    async function poll() {
      try {
        const value = await overviewRequest<Readiness>({ path: `/v2/companies/${company}/source-readiness`, signal: controller.signal });
        if (controller.signal.aborted) return;
        if (value.company_id !== company || !Object.hasOwn(messages, value.state)) throw new Error('Invalid report readiness response');
        setState(value);
        if (value.generation_id && value.generation_id !== generation) {
          generation = value.generation_id; callback.current();
        }
      } catch (error) {
        if (controller.signal.aborted) return;
        if ([401, 403, 404].includes(requestFailure(error, 'report preparation').status)) return;
        setState(previous => previous ? { ...previous, state: 'DELAYED' } : null);
      }
      timer = setTimeout(poll, 5000);
    }
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [company]);
  if (!state || state.company_id !== company) return null;
  return <Notice tone={state.state === 'NEEDS_ACTION' || state.state === 'DELAYED' ? 'warning' : 'info'}>
    <span role="status">{messages[state.state]}</span>
    {state.business_state === 'OPENING_REQUIRED' && <p>Opening balances are not yet confirmed. These figures cover recorded activity only. <a href="/settings/readiness">Review opening balances</a>.</p>}
    {state.business_state === 'BOOKS_NOT_STARTED' && <p>Your books start in the future. Figures will become available when that date arrives.</p>}
    {state.business_state === 'YEAR_REQUIRED' && <p>The current financial year needs preparation. Historical figures remain available. <a href="/settings/readiness">Review financial years</a>.</p>}
    {state.state === 'NEEDS_ACTION' && <p><a href="/settings/readiness">Review company readiness</a></p>}
  </Notice>;
}
