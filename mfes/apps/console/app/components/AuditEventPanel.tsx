'use client';

import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { Button, Notice, Skeleton, useFormatters } from '@janso/ui';
import type { AuditDetailLoader, AuditEventDetail, AuditEventItem } from '../lib/audit-events';

/**
 * The panel under an expanded audit row — the event in full (docs/audit.md §4, §5).
 *
 * It fetches on mount, and it mounts only when a row is actually opened: `DataTable` calls
 * `renderDetail` for open rows alone, so a page of fifty events makes no detail request until
 * someone asks for one. `changes` and `context` are JSON columns a list must never return
 * (api-conventions §3), which is why this is a second request rather than a wider first one.
 *
 * Nothing here is editable, and there is no verb: an audit row is immutable by construction
 * (docs/audit.md §2.2). What it offers instead is the material an auditor actually needs — the
 * before/after values, the reason, the chain hashes to re-verify the row, and the ids to correlate
 * it with a request. Authorized Identity names are optional; the trail holds only ids (§5.2, CLAUDE.md §6.9).
 */
export function AuditEventPanel({
  event,
  load,
}: {
  event: AuditEventItem;
  load: AuditDetailLoader;
}) {
  const format = useFormatters();
  const [detail, setDetail] = useState<AuditEventDetail | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    load(event, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setDetail(result);
      })
      .catch((error: unknown) => {
        // An abandoned request is not a failure: the reader closed the row, which is the panel
        // unmounting. Only a real rejection becomes a state.
        if (controller.signal.aborted) return;
        if (error instanceof DOMException && error.name === 'AbortError') return;
        setFailed(true);
      });
    return () => controller.abort();
  }, [event, load, attempt]);

  const retry = useCallback(() => setAttempt((value) => value + 1), []);

  if (failed) {
    return (
      <Notice
        tone="danger"
        title="This event could not be read"
        action={
          <Button variant="ghost" onClick={retry}>
            Try again
          </Button>
        }
      >
        This request failed. Retry to retrieve the event.
      </Notice>
    );
  }

  if (!detail) {
    return (
      <div className="console-audit-detail" aria-busy="true">
        <p className="console-audit-detail__pending" role="status">
          Loading the full event…
        </p>
        <Skeleton lines={3} />
      </div>
    );
  }

  const changes = Object.entries(detail.changes ?? {});
  const context = Object.entries(detail.context ?? {});

  return (
    <div className="console-audit-detail">
      {detail.reason ? (
        <p className="console-audit-detail__reason">
          <span className="console-audit-detail__term">Reason</span> {detail.reason}
        </p>
      ) : null}

      {changes.length > 0 ? (
        <section className="console-audit-detail__block">
          <h4 className="console-audit-detail__heading">What changed</h4>
          {/*
           * A real table: this is a grid of field / before / after, and a screen reader user needs
           * the row and column association to read one line of it. Amounts are the strings the
           * trail stored — they are not re-formatted here, because the point of the panel is what
           * was written, not how it would read today.
           */}
          <table className="console-audit-changes">
            <thead>
              <tr>
                <th scope="col">Field</th>
                <th scope="col">Before</th>
                <th scope="col">After</th>
              </tr>
            </thead>
            <tbody>
              {changes.map(([field, change]) => (
                <tr key={field}>
                  <th scope="row">{field}</th>
                  <td>{change.changed || change.from_recorded === false ? 'Not recorded' : change.from ?? <span aria-hidden="true">—</span>}</td>
                  <td>{change.changed ? 'Changed (values withheld)' : change.to_recorded === false ? 'Not recorded' : change.to ?? <span aria-hidden="true">—</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      <section className="console-audit-detail__block">
        <h4 className="console-audit-detail__heading">Where it came from</h4>
        <dl className="console-audit-detail__facts">
          <Fact term="Recorded">
            {/*
             * The instant, then the elapsed time as prose. The table's own column shows the instant
             * because that is what an auditor cites; "2 hours ago" answers a different question, and
             * it is safe to render here because this panel only exists after a click — a relative
             * string rendered on the server and again on the client would disagree.
             */}
            {format.dateTime(detail.occurred_at)} · {format.relative(detail.occurred_at)}
          </Fact>
          <Fact term="Chain position">{String(detail.sequence)}</Fact>
          <Fact term="Actor">{detail.actor_name ? `${detail.actor_name} (${detail.actor_user_id})` : detail.actor_user_id ?? detail.actor_type ?? 'System'}</Fact>
          {detail.on_behalf_of_user_id ? (
            <Fact term="On behalf of">{detail.on_behalf_of_name ? `${detail.on_behalf_of_name} (${detail.on_behalf_of_user_id})` : detail.on_behalf_of_user_id}</Fact>
          ) : null}
          <Fact term="Service">{detail.source_service ?? 'Unknown'}</Fact>
          {detail.trace_id ? <Fact term="Trace">{detail.trace_id}</Fact> : null}
          {detail.request_id ? <Fact term="Request">{detail.request_id}</Fact> : null}
          <Fact term="Message">{detail.message_id}</Fact>
        </dl>
      </section>

      {context.length > 0 ? (
        <section className="console-audit-detail__block">
          <h4 className="console-audit-detail__heading">Context</h4>
          <dl className="console-audit-detail__facts">
            {context.map(([key, value]) => (
              <Fact key={key} term={key}>
                {value}
              </Fact>
            ))}
          </dl>
        </section>
      ) : null}

      <section className="console-audit-detail__block">
        <h4 className="console-audit-detail__heading">Proof</h4>
        <p>Hashes identify the stored evidence. Restricted fields may be omitted here, so this view cannot independently verify the full chain.</p>
        {/*
         * The hash chain is what makes the trail tamper-evident: each row hashes its predecessor,
         * so an altered or removed row breaks every hash after it (docs/audit.md §4.2). Shown in
         * full and selectable, because an external auditor re-computes them.
         */}
        <dl className="console-audit-detail__facts">
          <Fact term="Row hash">
            <code className="console-audit-hash">{detail.row_hash}</code>
          </Fact>
          <Fact term="Previous hash">
            {detail.prev_hash ? (
              <code className="console-audit-hash">{detail.prev_hash}</code>
            ) : (
              'First event in this chain'
            )}
          </Fact>
        </dl>
      </section>
    </div>
  );
}

function Fact({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className="console-audit-detail__fact">
      <dt className="console-audit-detail__term">{term}</dt>
      <dd className="console-audit-detail__value">{children}</dd>
    </div>
  );
}
