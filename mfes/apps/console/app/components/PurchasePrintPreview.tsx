'use client';

import { useEffect, useRef, useState } from 'react';
import { Button, Card, CardBody, Notice, PageHeader, PageNavigation } from '@janso/ui';
import {
  purchasePrintRequest, verifiedPurchasePdf,
  type LayoutPreview, type PurchasePrintJob, type SavedPurchasePrint,
} from '../lib/purchase-print';

/** A design version shown on a saved bill (plan R4): its identity, and the words the page names it by. */
export type LayoutPreviewView = LayoutPreview & { templateName: string; versionNumber: number };

/**
 * Separate from the entry editor: every action refers to one identified saved revision.
 *
 * With `layoutPreview` the same saved revision is printed once on a saved design version instead
 * of the layout it resolves to (published or not), and every page is marked as a layout preview.
 * The job, its polling, the token download and the PDF verification are exactly a print's; what
 * differs is the request body, the words on the page, and where Back leads — the designer.
 */
export function PurchasePrintPreview(input: SavedPurchasePrint & { layoutPreview?: LayoutPreviewView }) {
  const [job, setJob] = useState<PurchasePrintJob>();
  const [pdf, setPdf] = useState<string>();
  const [failure, setFailure] = useState('');
  const [busy, setBusy] = useState(false);
  const [waiting, setWaiting] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const key = useRef<string | undefined>(undefined);
  const currentJob = useRef<PurchasePrintJob | undefined>(undefined);
  /** What the creation key was made for: a different bill, revision or design version is a different job. */
  const keyScope = useRef<string | undefined>(undefined);
  const frame = useRef<HTMLIFrameElement>(null);
  const root = `/v1/companies/${input.company}`;
  const preview = input.layoutPreview;
  const templateId = preview?.templateId;
  const designVersionId = preview?.versionId;
  const purpose = preview ? 'layout-preview' : 'print';

  useEffect(() => {
    const scope = [input.voucherId, input.revisionId, input.version, templateId ?? '', designVersionId ?? ''].join(':');
    if (keyScope.current !== scope) { keyScope.current = scope; key.current = undefined; currentJob.current = undefined; }
    const controller = new AbortController();
    let objectUrl: string | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;
    async function check(value: PurchasePrintJob, count = 0): Promise<void> {
      if (stopped) return;
      currentJob.current = value;
      setJob(value);
      if (value.status === 'FAILED') {
        key.current = undefined; currentJob.current = undefined;
        throw new Error(value.failure_code === 'RENDER_TIMEOUT'
          ? 'This print took too long. Generate a new copy, or check a large custom layout.'
          : 'The PDF could not be generated. Retry, or ask your administrator to check Purchase printing.');
      }
      if (value.status === 'READY') {
        const download = await purchasePrintRequest(`${root}/voucher-print-jobs/${value.id}/download?token=${encodeURIComponent(value.download_token ?? '')}`, 'GET', controller.signal, undefined, undefined, purpose);
        const blob = await verifiedPurchasePdf(download, value);
        if (stopped) return;
        objectUrl = URL.createObjectURL(blob);
        setPdf(objectUrl); setBusy(false); return;
      }
      if (count >= 60) { setWaiting(true); setBusy(false); return; }
      timer = setTimeout(() => {
        void purchasePrintRequest(`${root}/voucher-print-jobs/${value.id}`, 'GET', controller.signal, undefined, undefined, purpose)
          .then(response => response.json()).then(next => check(next, count + 1)).catch(failed);
      }, Math.min(1000 + count * 100, 3000));
    }
    function failed(error: unknown) {
      if (!stopped) { setFailure(error instanceof Error ? error.message : 'Purchase printing is unavailable. Retry shortly.'); setBusy(false); }
    }
    async function start() {
      setFailure(''); setWaiting(false); setBusy(true); setPdf(undefined); setLoaded(false);
      if (currentJob.current) {
        const status = await purchasePrintRequest(`${root}/voucher-print-jobs/${currentJob.current.id}`, 'GET', controller.signal, undefined, undefined, purpose);
        await check(await status.json());
      } else {
        key.current ??= crypto.randomUUID();
        const result = await purchasePrintRequest(`${root}/vouchers/${input.voucherId}/print-jobs`, 'POST', controller.signal,
          { expected_version: input.version, revision_id: input.revisionId,
            ...(templateId && designVersionId ? { layout_preview: { template_id: templateId, version_id: designVersionId } } : {}) },
          key.current, purpose);
        await check(await result.json());
      }
    }
    void start().catch(failed);
    return () => { stopped = true; controller.abort(); clearTimeout(timer); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [root, input.voucherId, input.revisionId, input.version, templateId, designVersionId, purpose, attempt]);

  const named = preview ? `“${preview.templateName} version ${preview.versionNumber}”` : '';
  return <div className="janso-page">
    <PageNavigation back={preview
      ? { href: `/invoice-designer/${preview.templateId}`, label: 'designer' }
      : { href: `/vouchers/${input.voucherId}`, label: 'saved Purchase' }} />
    {preview
      ? <PageHeader title={`Layout preview of ${named}`} lede={`This saved Purchase bill printed on ${named} of the design, to check the layout. It is not the bill’s print: every page is marked “Layout preview · not for use”.`} />
      : <PageHeader title="Purchase print" lede="Review the PDF, then download it or open the print controls. This is your internal Purchase record." />}
    <Card><CardBody><div className="janso-flow">
      <p>Saved revision {job?.revision_number ?? '—'} · {job?.document_status ?? 'Preparing'}{job && ` · ${job.layout_name} / ${job.layout_version}`}</p>
      {busy && <p role="status">{job ? 'Preparing your Purchase PDF…' : 'Checking the saved Purchase and its print layout…'}</p>}
      {failure && <Notice tone="danger" live="assertive">{failure}</Notice>}
      {waiting && <Notice tone="info">Your print is still queued. You can check its progress again.</Notice>}
      <div className="janso-toolbar">
        {(failure || waiting) && <Button onClick={() => setAttempt(value => value + 1)} disabled={busy}>{waiting ? 'Check progress' : 'Retry print'}</Button>}
        {pdf && <>
          <Button disabled={!loaded} onClick={() => frame.current?.contentWindow?.print()}>Print PDF</Button>
          <a className="janso-btn janso-btn--ghost" href={pdf} download={preview ? `layout-preview-${input.voucherId}.pdf` : `purchase-${input.voucherId}.pdf`}>Download PDF</a>
          <a className="janso-btn janso-btn--ghost" href={pdf} target="_blank" rel="noopener noreferrer">Open PDF</a>
        </>}
      </div>
      {pdf && <iframe ref={frame} title={preview ? 'Layout preview PDF' : 'Purchase voucher PDF preview'} src={pdf} className="janso-purchase-pdf" onLoad={() => setLoaded(true)} />}
      <p className="janso-meta">{preview
        ? 'A layout preview checks the design only. Print the bill from the bill itself for a copy to keep or send.'
        : 'Draft, cancelled and reversed copies carry their status. The PDF does not confirm payment or replace the supplier’s tax invoice.'}</p>
    </div></CardBody></Card>
  </div>;
}
