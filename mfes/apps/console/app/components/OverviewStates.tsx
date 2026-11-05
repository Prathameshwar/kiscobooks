'use client';
import { asErrorStatus, Button, Card, CardBody, EmptyState, ErrorState, InfoIcon, Skeleton } from '@janso/ui';
import type { RequestFailure } from '../lib/service-call';

/** The shape of the finished page, so the figures arrive where the placeholders were. */
export function OverviewSkeleton() {
  const tile = (key: number) => <Card key={key}><CardBody><Skeleton lines={3} /></CardBody></Card>;
  return <div className="janso-flow" role="status" aria-label="Loading company overview">
    <div className="janso-stat-row" data-columns="4">{[0, 1, 2, 3].map(tile)}</div>
    <div className="janso-grid janso-grid--split">{[0, 1].map(key => <Card key={key}><CardBody><Skeleton lines={7} /></CardBody></Card>)}</div>
  </div>;
}

type Recovery = { onRetry: () => void; /** Offered when a non-default period failed, so the reader is never stranded on it. */ onDefault?: () => void };

function Actions({ onRetry, onDefault }: Recovery) {
  return <>
    <Button variant="ghost" onClick={onRetry}>Retry overview</Button>
    {onDefault && <Button variant="ghost" onClick={onDefault}>Show year to date</Button>}
  </>;
}

/**
 * Report preparation continues in the background; the reader can inspect company
 * readiness while polling waits for verified evidence.
 */
export function OverviewUnavailable({ detail, ...recovery }: { detail: string } & Recovery) {
  return <Card><CardBody>
    <EmptyState
      icon={<InfoIcon size={20} />}
      title="Preparing your figures"
      body="Your figures are prepared automatically from verified books. This page will update when they are ready."
      action={<div className="janso-form-actions">
        <a className="janso-btn janso-btn--primary" href="/settings/readiness">View company readiness</a>
        <Actions {...recovery} />
      </div>}
    />
    <p className="janso-meta janso-overview__detail">{detail}</p>
  </CardBody></Card>;
}

/** The 409s Reports raises when there is no current verified snapshot all name it; other conflicts (a reconciliation failure, say) are not cured by refreshing. */
const NEEDS_SOURCE = /\b(source|generation|snapshot)\b/i;

export function OverviewFailure({ failure, ...recovery }: { failure: RequestFailure } & Recovery) {
  if (failure.status === 409 && NEEDS_SOURCE.test(failure.message)) return <OverviewUnavailable detail={failure.message} {...recovery} />;
  return <ErrorState status={asErrorStatus(failure.status)} detail={failure.message} action={<Actions {...recovery} />} />;
}
