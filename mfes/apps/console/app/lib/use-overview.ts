'use client';
import { useEffect, useRef, useState } from 'react';
import { requestFailure, type RequestFailure } from './service-call';
import { overviewPath, overviewRequest, verifyOverview, type Overview, type OverviewRange } from './company-overview';
import { anchorOf, periodRange, type Anchor, type PeriodKey } from './overview-periods';

type State = { data: Overview | null; pending: boolean; failure: RequestFailure | null };

/**
 * Reads the company overview for a period.
 *
 * Unlike `useServiceRead` this keeps the previous figures while the next period loads: changing
 * a period must not blank the page. The captions on the page are read from the *data*, never
 * from the selection, so what is displayed always states the range it actually covers.
 *
 * A preset other than the default needs the company's own "today" and year/coverage start, which
 * only a response carries (never the browser clock), so the first non-default request is
 * preceded by one default read.
 */
export function useOverview(company: string, yearId: string | undefined, period: PeriodKey) {
  const [state, setState] = useState<State>({ data: null, pending: true, failure: null });
  const [revision, setRevision] = useState(0);
  const anchorRef = useRef<{ scope: string; anchor: Anchor } | null>(null);
  const scope = company + ':' + (yearId ?? '');

  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;
    const read = async (range: OverviewRange | null) => {
      const value = await overviewRequest<Overview>({ path: overviewPath(company, yearId, range), signal });
      verifyOverview(company, yearId, range)(value);
      return value;
    };
    setState(previous => ({ ...previous, pending: true, failure: null }));
    (async () => {
      let anchor = anchorRef.current?.scope === scope ? anchorRef.current.anchor : null;
      if (period !== 'ytd' && !anchor) {
        anchor = anchorOf(await read(null));
        anchorRef.current = { scope, anchor };
      }
      const range = period === 'ytd' || !anchor ? null : periodRange(period, anchor);
      const data = await read(range && { from: range.from, to: range.to });
      if (signal.aborted) return;
      if (!range) anchorRef.current = { scope, anchor: anchorOf(data) };
      setState({ data, pending: false, failure: null });
    })().catch(error => {
      if (!signal.aborted) {
        const failure = requestFailure(error, 'company overview');
        setState(previous => ({ data: [401, 403, 404].includes(failure.status) ? null : previous.data, pending: false, failure }));
      }
    });
    return () => controller.abort();
  }, [company, yearId, period, revision, scope]);

  const current = state.data?.company_id === company && (!yearId || state.data.fiscal_year_id === yearId) ? state.data : null;
  return {
    data: current,
    anchor: anchorRef.current?.scope === scope ? anchorRef.current.anchor : null,
    loading: state.pending && !current,
    refreshing: state.pending && !!current,
    failure: state.failure,
    refresh: () => setRevision(value => value + 1),
  };
}
