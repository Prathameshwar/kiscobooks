'use client';

import type { components } from '@janso/api-client/catalog';
import { PreparationProgress } from '@janso/ui';

type Job = Pick<components['schemas']['SimpleCreationStatus'], 'status' | 'step' | 'code' | 'opening_posted' | 'last_error'>;
const prices = ['NUMERIC', 'MRP', 'PUBLISH'];
const trackingSteps = ['BATCH', 'BATCH_PRICES', 'SERIAL'];
const stockSteps = ['OPENING', 'SOURCE', 'VOUCHER', 'SUBMIT', 'ISSUE', 'POST', 'FINALIZE'];

export function SimpleProductProgress({ job, busy = false, failed = false, editing = false, pricing = true, tracking = false, opening = false, waitingForStock = false, waitingForPricing = false }: {
  job?: Job | null;
  busy?: boolean;
  failed?: boolean;
  editing?: boolean;
  pricing?: boolean;
  tracking?: boolean;
  opening?: boolean;
  waitingForStock?: boolean;
  waitingForPricing?: boolean;
}) {
  const complete = job?.status === 'COMPLETE';
  const step = complete ? 'COMPLETE' : job?.step ?? 'CREATE';
  const known = ['CREATE', 'ACTIVATE', 'COMPLETE', ...prices, ...trackingSteps, ...stockSteps].includes(step);
  // Native steps are the next work to perform, not completed receipts.
  const stages = [
    { label: 'Product details', steps: ['CREATE'] },
    ...(pricing || prices.includes(step) ? [{ label: 'Prices', steps: prices }] : []),
    { label: 'Activation', steps: ['ACTIVATE'] },
    ...(tracking || trackingSteps.includes(step) ? [{ label: 'Batches and serials', steps: trackingSteps }] : []),
    ...(opening || job?.opening_posted || stockSteps.includes(step) ? [{ label: 'Opening stock', steps: stockSteps }] : []),
    { label: 'Ready to use', steps: ['COMPLETE'] },
  ];
  const index = stages.findIndex(stage => stage.steps.includes(step));
  let title = 'Creating your product';
  if (waitingForStock) title = 'Waiting for stock confirmation';
  if (waitingForPricing) title = 'Refreshing product prices';
  if (!busy) title = failed ? 'Creation needs attention' : 'Creation is saved';
  if (editing && !busy) title = 'Correct your product details';
  if (complete) title = 'Product created successfully';
  let detail = 'Saving product details…';
  if (prices.includes(step)) detail = 'Saving product prices…';
  if (step === 'ACTIVATE') detail = 'Activating the product…';
  if (trackingSteps.includes(step)) detail = 'Preparing batch and serial details…';
  if (step === 'OPENING') detail = 'Calculating opening stock…';
  if (step === 'SOURCE') detail = 'Verifying product details for opening stock…';
  if (stockSteps.includes(step) && !['OPENING', 'SOURCE'].includes(step)) detail = 'Posting and verifying opening stock…';
  if (!known) detail = 'Checking the latest saved creation progress…';
  if (waitingForStock) detail = 'Waiting for the current stock posting to finish; product setup will resume automatically…';
  if (waitingForPricing) detail = 'Refreshing the price preview after a source change; product setup will resume automatically…';
  if (!busy) detail = editing ? 'Update the details below, then choose Save corrected product.' : `${job?.last_error ? job.last_error + ' ' : ''}Choose Continue creation below to check progress and resume.`;
  if (complete) detail = `Product ${job.code} is active and ready.${job.opening_posted ? ' Opening stock has been posted.' : ''}`;
  return <PreparationProgress label="Product creation progress" variant="panel" title={title} detail={detail} active={busy && !complete} complete={complete} autoScroll={busy && !complete}
    steps={known ? stages.map((stage, i) => ({ label: stage.label, state: complete || i < index ? 'done' : i === index ? 'current' : 'waiting' })) : [{ label: 'Confirming progress', state: 'current' }]} />;
}
