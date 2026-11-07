import type { components } from '@janso/api-client/catalog';
import { profileErrors, skuErrors, type AdvancedOptions, type AdvancedWork } from './advanced-product-draft';
import { businessErrors } from './advanced-product-business';
import { openingErrors } from './advanced-product-opening';

export function advancedProductErrors(work: AdvancedWork, options: AdvancedOptions, status?: components['schemas']['AdvancedDefinitionStatus'] | null, step?: number) {
  const errors = { ...(!step || step === 1 ? profileErrors(work, options) : {}), ...(!step || step === 2 ? skuErrors(work, options) : {}), ...(!step || step === 3 ? businessErrors(work, options) : {}), ...(!step || step === 4 ? openingErrors(work, options) : {}) };
  if (!status) return errors;
  // Submitted identity and confirmed owner work are immutable during recovery.
  // Remaining setup still uses the current rules; native checks remain authoritative.
  return Object.fromEntries(Object.entries(errors).filter(([path]) => {
    const match = /^(business\.|opening\.)?skus\.(\d+)\.(.*)$/.exec(path);
    if (match) {
      const index = Number(match[2]);
      const row = status.sku_progress?.[index];
      if (!row || row.item_id !== status.sku_ids[index]) return true;
      if (match[1] === 'business.') return !row.setup_done;
      if (match[1] === 'opening.') return (row.opening_state ?? 'NOT_REQUESTED') === 'NOT_REQUESTED';
      return !row.setup_done && /^(units|barcode)(\.|$)/.test(match[3]!);
    }
    const first = status.sku_progress?.[0];
    const setupSaved = first?.item_id === status.sku_ids[0] && first?.setup_done;
    return !setupSaved && /^(categories|manufacturer_id|manufacturer_site_id)(\.|$)/.test(path);
  }));
}
