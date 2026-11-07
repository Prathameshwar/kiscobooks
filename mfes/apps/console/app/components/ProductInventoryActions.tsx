'use client';
import { useState, type MouseEventHandler } from 'react';
import { Menu, businessToday, useDisplayConfig, type MenuItem } from '@janso/ui';
import type { MasterRow } from '../lib/catalog-masters';
import type { ClassificationAccess } from '../lib/product-classification-resources';
import { useCompanyActionFeatures } from '../lib/company-action-features';
import { useProductEntryConfiguration } from '../lib/product-entry-policy';
import { usePublishedProductRevision } from '../lib/published-product-revision';

import { useServiceRead } from '../lib/service-resource';
import { masterRequest } from '../lib/catalog-master-api';

import type { components } from '@janso/api-client/catalog';

type ActivatedProfile = components['schemas']['ItemInventoryProfileListItem'];

const inventoryFeatures = ['inventory'];

/** Verify current company/product applicability only when its menu opens. */
export function useProductInventoryActions({
  company,
  row,
  family,
  access,
  items,
  requested,
}: {
  company: string;
  row: MasterRow;
  family: boolean;
  access: ClassificationAccess;
  items: MenuItem[];
  returnTo?: string;
  requested: boolean;
}) {
  const display = useDisplayConfig(),
    today = businessToday(display.timezone);
  const capabilities = useCompanyActionFeatures(
    company,
    requested &&
      !!access.companyConfiguration &&
      !(family && row.kind === 'SERVICE'),
    inventoryFeatures,
  );
  const inventoryEnabled = capabilities.features.enabled?.includes('inventory');
  const configuration = useProductEntryConfiguration(
    company,
    today,
    family ? { familyId: row.id, kind: row.kind } : { itemId: row.id },
    requested && !!inventoryEnabled && !!access.configuration,
  );
  const profileId = configuration.data?.profiles.inventory_template_revision_id;
  const activeSku = !family && row.status === 'ACTIVE';
  const activated = useServiceRead<{ items: ActivatedProfile[]; page: { has_more: boolean } }>(
    requested && activeSku && !!inventoryEnabled && !!access.inventoryProfiles && configuration.data?.kind === 'GOODS'
      ? `/v1/companies/${company}/item-inventory-profiles?item_id=${row.id}&limit=2` : undefined,
    masterRequest, value => {
      if (!Array.isArray(value.items) || value.items.length > 1 || value.page?.has_more !== false || value.items.some(entry => entry.item_id !== row.id)) throw { status: 502, message: 'The activated product inventory profile could not be verified.' };
    },
  );
  const profile = usePublishedProductRevision(
    company,
    'inventory-template-revisions',
    profileId,
    requested &&
      !!inventoryEnabled &&
      !!access.inventoryProfiles &&
      !activeSku &&
      configuration.data?.kind === 'GOODS',
  );
  const selectedProfile = activeSku ? activated.data?.items[0] : profile.data;
  const kind = family ? row.kind : configuration.data?.kind;
  const actions: MenuItem[] = [
    ...items,
    {
      id: 'product-ledger',
      label: 'Product ledger',
      separatorBefore: true,
      disabledReason: 'The product ledger screen is not available yet.',
    },
  ];
  if (kind !== 'SERVICE' && inventoryEnabled !== false) {
    const restriction = !access.companyConfiguration
      ? 'Company configuration read access is required to verify inventory availability.'
      : !access.configuration || !access.inventoryProfiles
        ? 'Product configuration and inventory profile read access are required.'
        : family && !['GOODS', 'SERVICE'].includes(String(kind))
          ? 'The product kind is protected. Inventory applicability cannot be verified.'
          : (capabilities.features.restriction ??
            (configuration.failure || (activeSku ? activated.failure : profile.failure)
              ? 'Inventory configuration is unavailable. Reopen this menu to try again.'
              : !configuration.data
                ? 'Checking product inventory configuration.'
                : activeSku && !activated.data
                  ? 'Checking the activated product inventory profile.'
                  : activeSku && !selectedProfile
                    ? 'This product has no activated stock profile.'
                : !activeSku && !profileId
                  ? 'No inventory profile is configured for this product.'
                  : !selectedProfile
                    ? 'Checking the published inventory profile.'
                    : typeof selectedProfile.lot_tracking !== 'boolean' ||
                        typeof selectedProfile.serial_tracking !== 'boolean'
                      ? 'Inventory tracking settings are protected or unavailable.'
                      : undefined));
    actions.push({
      id: 'product-stock',
      label: 'Manage stock',
      ...(!restriction && activeSku && access.stock ? { href: '/inventory/stock?item_id=' + row.id } : { disabledReason: restriction ?? (family ? 'Open a product / SKU to manage physical stock.' : !activeSku ? 'Activate this product before managing stock.' : 'Stock read access is required for this company.') }),
    });
    if (!family && activeSku) {
      for (const tracking of [{ kind: 'batches', label: 'Manage batches', enabled: selectedProfile?.lot_tracking, allowed: access.batches }, { kind: 'serials', label: 'Manage serials', enabled: selectedProfile?.serial_tracking, allowed: access.serials }]) {
        actions.push({ id: 'product-' + tracking.kind, label: tracking.label, ...(!restriction && tracking.enabled === true && tracking.allowed ? { href: '/inventory/' + tracking.kind + '?item_id=' + row.id } : { disabledReason: restriction ?? (!tracking.allowed ? 'Tracking read access is required for this company.' : 'This product does not use ' + tracking.kind + '.') }) });
      }
    }
    if (!family && !restriction && access.openingStock && activeSku)
      actions.push({ id: 'product-opening', label: 'Record opening stock', href: '/inventory/stock/opening?item_id=' + row.id });
    if (!family && !restriction && access.warehousePolicies && access.warehouses)
      actions.push({ id: 'product-warehouse-policy', label: 'Warehouse and replenishment policies', href: '/products/warehouse-policy?item_id=' + row.id });

  }
  return { actions, configuration: configuration.data, restriction: capabilities.features.restriction ??
    (configuration.failure || (activeSku ? activated.failure : profile.failure) ? 'Inventory configuration is unavailable. Refresh to try again.' : undefined), refresh: () => {
    capabilities.refresh(); configuration.refresh(); profile.refresh(); activated.refresh();
  } };
}

export function ProductInventoryActions(props: {
  company: string; row: MasterRow; family: boolean; access: ClassificationAccess;
  items: MenuItem[]; label?: string; triggerLabel?: string;
  onNavigate?: MouseEventHandler<HTMLAnchorElement>; returnTo?: string;
}) {
  const [requested, setRequested] = useState(false);
  const inventory = useProductInventoryActions({ ...props, requested });
  return (
    <Menu
      label={props.label ?? 'Actions for ' + String(props.row.name ?? props.row.code ?? 'Record')}
      triggerLabel={props.triggerLabel}
      onNavigate={props.onNavigate}
      items={inventory.actions}
      onSelect={() => {}}
      size="sm"
      onOpen={() => {
        setRequested(true);
        if (requested) {
          inventory.refresh();
        }
      }}
    />
  );
}
