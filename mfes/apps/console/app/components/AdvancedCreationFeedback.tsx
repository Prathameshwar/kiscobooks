'use client';

import { PreparationProgress } from '@janso/ui';
import type { components } from '@janso/api-client/catalog';

type Status = components['schemas']['AdvancedDefinitionStatus'];
type Sku = { sku: string; name?: string };
const openingText: Record<string, string> = { NOT_REQUESTED: 'Opening choice awaiting confirmation', SKIPPED: 'No opening stock requested', IN_PROGRESS: 'Stock posting in progress', POSTED: 'Opening stock posted' };

export function advancedReadinessMessage(blocker: components['schemas']['AdvancedReadinessBlocker'], skus: readonly Sku[]) {
  const index = blocker.path.match(/skus\.(\d+)/)?.[1];
  const sku = index === undefined ? '' : skus[Number(index)]?.sku || `SKU ${Number(index) + 1}`;
  const step = { profile: 'Step 1 · Product Profile', skus: 'Step 2 · SKUs and units', business: 'Step 3 · Business setup' }[blocker.step];
  const field = blocker.path.split('.').at(-1);
  const hints: Record<string, string> = {
    group_id: 'Choose the product group.', categories: 'Check the required product categories.',
    brand: 'Choose the required brand.', model: 'Enter the required model.', manufacturer: 'Check the manufacturer details.',
    attributes: 'Check the required attributes and variant choices.', units: 'Check the base unit and unit conversions.',
    tax: 'Check the tax classification and rate.', prices: 'Check the required selling prices, purchase reference and MRP.',
    inventory_profile: 'Check the stock tracking settings.',
  };
  return `${step}${sku ? ` · ${sku}` : ''}: ${hints[field ?? ''] ?? 'Review this setup before activation.'}`;
}

export function AdvancedCreationFeedback({ status, skus, busy = false, failed = false, message }: {
  status: Status | null;
  skus: readonly Sku[];
  busy?: boolean;
  failed?: boolean;
  message: string;
}) {
  const complete = status?.status === 'COMPLETE';
  const rows = skus.map((_, i) => status?.sku_progress?.[i]?.item_id === status?.sku_ids[i] ? status?.sku_progress?.[i] : undefined);
  const setupCount = rows.filter(row => row?.setup_done).length;
  const pricesDone = (row: typeof rows[number]) => !!row?.setup_done && Array.isArray(row.price_draft_ids) && Array.isArray(row.published_price_ids) && row.published_price_ids.length >= row.price_draft_ids.length;
  const all = (check: (row: typeof rows[number]) => boolean) => rows.length > 0 && rows.every(check);
  const phases = [
    { label: 'Profile and SKUs', done: !!status },
    { label: 'SKU setup', done: all(row => !!row?.setup_done) },
    { label: 'Prices', done: all(pricesDone) },
    { label: 'Activation', done: all(row => !!row?.activated) },
    { label: 'Opening stock', done: all(row => row?.opening_state === 'POSTED' || row?.opening_state === 'SKIPPED') },
    { label: 'Ready to use', done: !!complete },
  ];
  const current = phases.findIndex(phase => !phase.done);
  return <>
    <PreparationProgress variant="panel" label="Product creation progress" title={complete ? 'Product created successfully' : busy ? 'Creating your product and SKUs' : failed ? 'Creation needs attention' : 'Checking saved progress'}
      detail={complete ? 'Product Profile and all requested SKUs are complete.' : busy ? message : 'Read the message below, then choose Continue this creation to check progress and retry.'}
      active={busy && !complete} complete={complete} autoScroll={busy && !complete}
      steps={phases.map((phase, i) => ({ label: phase.label, state: complete || i < current ? 'done' : i === current ? 'current' : 'waiting' }))} />
    {status && <section className="product-wizard__sku-progress" aria-label="Individual SKU progress">
      <div><h3>Progress for each SKU</h3><p>{setupCount} of {skus.length} SKUs have setup saved.</p></div>
      <div className="product-wizard__sku-progress-grid">{skus.map((sku, i) => {
        const row = rows[i];
        return <section key={status.sku_ids[i] ?? i} className="product-wizard__sku-progress-card" role="region" aria-label={`${sku.sku || `SKU ${i + 1}`} status`}>
          <h4>{sku.sku || `SKU ${i + 1}`}</h4>{sku.name && <p>{sku.name}</p>}
          <dl><div><dt>Setup</dt><dd>{row?.setup_done ? 'Setup saved' : 'Setup awaiting confirmation'}</dd></div>
            <div><dt>Selling prices</dt><dd>{pricesDone(row) ? row?.price_draft_ids?.length ? 'Prices saved' : 'No selling prices to publish' : 'Prices awaiting confirmation'}</dd></div>
            <div><dt>Activation</dt><dd>{row?.activated ? 'Active' : 'Activation awaiting confirmation'}</dd></div>
            <div><dt>Opening stock</dt><dd>{openingText[row?.opening_state ?? 'NOT_REQUESTED'] ?? 'Checking opening status'}</dd></div></dl>
        </section>;
      })}</div>
    </section>}
  </>;
}
