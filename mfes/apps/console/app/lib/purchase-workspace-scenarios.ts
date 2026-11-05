import { blankPurchaseLine, newPurchaseWorkspace, purchaseEvidenceSignature, purchaseExample, type PurchaseWorkspaceDraft } from './purchase-workspace';

export const PURCHASE_SCENARIOS = [
  { value: 'goods', label: 'Goods bill with an advance' },
  { value: 'receipt', label: 'Partial existing receipt' },
  { value: 'recipient', label: 'Service with recipient tax' },
  { value: 'untaxed', label: 'Untaxed account expense' },
  { value: 'tracking', label: 'Batch and serial tracking' },
  { value: 'mixed', label: 'Goods with a service line' },
  { value: 'bundle', label: '11 received / 10 billed' },
  { value: 'mismatch', label: 'Supplier total needs review' },
];
export function purchaseScenario(id: string, today: string): PurchaseWorkspaceDraft {
  if (id === 'goods') return purchaseExample(today);
  if (['mixed', 'bundle', 'mismatch', 'duplicate'].includes(id)) {
    const draft = purchaseExample(today);
    if (id === 'mixed') {
      draft.mode = 'MIXED';
      draft.lines.push({ ...blankPurchaseLine('p3', 'ACCOUNT'), subject: 'demo-maintenance', label: 'Repairs & maintenance', amount: '500' });
      draft.nextKey = 4;
    } else if (id === 'bundle') draft.lines[0] = { ...draft.lines[0]!, received: '11', billed: '10', quantityReason: 'Paid bundle: 11 received for 10 billed. No extra price discount inferred.' };
    else if (id === 'mismatch') draft.details.declaredTotal = '5800';
    if (draft.evidence) draft.evidence.signature = purchaseEvidenceSignature(draft);
    return draft;
  }
  const draft = newPurchaseWorkspace(today);
  Object.assign(draft, { supplier: 'demo-paper', payable: 'demo-trade', invoice: 'EXAMPLE-' + id.toUpperCase() });
  if (id === 'receipt') {
    draft.lines = [{ ...blankPurchaseLine('p1', 'ITEM'), subject: 'demo-notebook', label: 'A5 ruled notebooks · pack of 4', unit: 'pack', received: '6', billed: '6', rate: '100' }];
    draft.details.receiptIntent = 'REFERENCE';
    draft.details.receipts = [{ lineKey: 'p1', sourceId: 'demo-grn-notebooks', quantity: '6' }];
  } else if (id === 'tracking') {
    draft.lines = [
      { ...blankPurchaseLine('p1', 'ITEM'), subject: 'demo-batch-ink', label: 'Printer ink · tracked batch', unit: 'each', received: '2', billed: '2', rate: '100' },
      { ...blankPurchaseLine('p2', 'ITEM'), subject: 'demo-serial-device', label: 'Barcode scanner · tracked serial', unit: 'each', received: '2', billed: '2', rate: '1000' },
    ];
    draft.nextKey = 3;
  } else {
    draft.mode = 'ACCOUNTS';
    draft.lines = [{ ...blankPurchaseLine('p1', 'ACCOUNT'), subject: 'demo-maintenance', label: 'Repairs & maintenance', amount: id === 'untaxed' ? '4200' : '1000' }];
  }
  draft.evidence = { signature: purchaseEvidenceSignature(draft), reference: 'Synthetic ' + id + ' recipe',
    jurisdiction: 'Example jurisdiction', registration: 'Example registration', classification: id === 'recipient' ? 'Recipient-liability service · example' : 'Supplied example',
    components: id === 'untaxed' ? [] : id === 'recipient' ? [{ label: 'Recipient liability · supplied example', rate: '18', liability: 'RECIPIENT' }] : [{ label: 'Supplier tax · supplied example', rate: '18', liability: 'SUPPLIER' }] };
  return draft;
}
