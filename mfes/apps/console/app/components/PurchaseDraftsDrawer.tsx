'use client';

import { Button, Drawer, EmptyState, Notice, TextField, useFormatters } from '@janso/ui';
import { trackingId } from '../lib/stock-tracking-resources';

export type PurchaseDraftRow = { id: string; status: string; document_date?: string | null };

/**
 * Reopen a saved purchase draft. The list is the main way in; a pasted ID is kept for the person
 * who was handed one, but sits below it, because nobody should have to know a UUID to find a bill.
 */
export function PurchaseDraftsDrawer({ open, onClose, drafts, loaded, cursor, locked, failure, resume, onResume, onOpen, onMore, onRetry }: {
  open: boolean; onClose: () => void;
  drafts: readonly PurchaseDraftRow[]; loaded: boolean; cursor: string | null; locked: boolean;
  /** A failed read, shown here because the page's own notices sit behind the drawer's scrim. */
  failure: string;
  resume: string; onResume: (value: string) => void;
  onOpen: (id: string) => void; onMore: (cursor: string) => void; onRetry: () => void;
}) {
  const format = useFormatters();
  return <Drawer open={open} title="Saved purchase drafts" onClose={onClose} footer={<Button variant="ghost" onClick={onClose}>Close</Button>}>
    <div className="janso-flow">
      {failure ? <Notice tone="danger" title="Saved drafts could not be read"><p>{failure}</p><Button variant="ghost" disabled={locked} onClick={onRetry}>Try again</Button></Notice> : null}
      {!loaded ?<p role="status">Loading saved drafts…</p>
        : drafts.length ? <ul className="janso-purchase-drafts" aria-label="Saved purchase drafts">{drafts.map(row => <li key={row.id}>
          <Button variant="ghost" disabled={locked} aria-label={'Open draft ' + (row.document_date ? format.date(row.document_date) : 'without a date') + ', ' + row.id} onClick={() => onOpen(row.id)}>
            <span>{row.document_date ? format.date(row.document_date) : 'Saved draft'}</span>
            <span className="janso-purchase-drafts__id" aria-hidden="true">…{row.id.slice(-8)}</span>
          </Button></li>)}</ul>
        : failure ? null : <EmptyState title="No saved drafts" body="Drafts you save appear here, so you can come back to them." />}
      {cursor ? <Button variant="ghost" disabled={locked} onClick={() => onMore(cursor)}>More saved purchases</Button> : null}
      <div className="janso-purchase-open-by-id">
        <TextField label="Saved Purchase ID" value={resume} disabled={locked} onChange={event => onResume(event.target.value)} hint="Paste an ID you were given to open that purchase." />
        <Button variant="ghost" disabled={locked || !trackingId.test(resume)} onClick={() => onOpen(resume)}>Open saved purchase</Button>
      </div>
    </div>
  </Drawer>;
}
