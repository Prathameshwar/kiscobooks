'use client';
import type { MenuItem } from '@janso/ui';
import {
  accountingLink,
  accountingUUID,
} from './accounting-configuration-resources';
import {
  useCompanyActionFeatures,
  type CompanyActionFeatures,
} from './company-action-features';
export type PartyActionFeatures = CompanyActionFeatures;
const partyFeatureKeys = ['inventory', 'multi_price_levels', 'credit_limits'];
export const usePartyActionFeatures = (company: string, canRead: boolean) =>
  useCompanyActionFeatures(company, canRead, partyFeatureKeys);

/** Navigation only: native target pages retain their own scope and field checks. */
export function partyDirectoryActions(
  id: string,
  back: string,
  available: readonly string[],
  manageable: readonly string[],
  features: PartyActionFeatures,
  canManagePricing: boolean,
): MenuItem[] {
  if (!accountingUUID.test(id)) return [];
  const actions: MenuItem[] = [];
  if (available.includes('party-credit-policies')) {
    const restriction =
      features.restriction ??
      (!features.enabled?.includes('credit_limits')
        ? 'Enable credit limits in Company Config to use this action.'
        : undefined);
    actions.push({
      id: 'party-credit',
      label: manageable.includes('party-credit-policies')
        ? 'Manage credit limits'
        : 'View credit limits',
      ...(restriction
        ? { disabledReason: restriction }
        : {
            href: accountingLink(
              '/accounting/party-credit-policies?' +
                new URLSearchParams({ party_id: id }),
              back,
            ),
          }),
      separatorBefore: true,
    });
  }
  if (
    canManagePricing &&
    (!features.enabled ||
      (features.enabled.includes('inventory') &&
        features.enabled.includes('multi_price_levels')))
  )
    actions.push({
      id: 'party-pricing',
      label: 'Manage pricing',
      disabledReason:
        features.restriction ??
        'Party-specific pricing management is not available yet.',
      separatorBefore: !actions.length,
    });
  actions.push(
    {
      id: 'party-ledger',
      label: 'Check ledger',
      disabledReason: 'The party ledger screen is not available yet.',
      separatorBefore: true,
    },
    {
      id: 'party-pending-bills',
      label: 'Pending bills for adjustment',
      disabledReason:
        'The pending-bill adjustment screen is not available yet.',
    },
  );
  return actions;
}
