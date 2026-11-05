'use client';
import {
  ActionCard,
  BoxIcon,
  ErrorState,
  PageHeader,
  PageNavigation,
} from '@janso/ui';
import type { Session } from '../session';
import type { CompanyContext } from '../lib/company-context';
import {
  inventoryGroups,
  inventoryNavigationFor,
} from '../lib/inventory-navigation';
import { companyPermission } from '../lib/company-permissions';
import { masterLink } from '../lib/master-navigation';
import { NoCompany } from './NoCompany';
import { useProductMode } from './ProductModeProvider';

export function InventoryOverview({
  session,
  context,
  groupKey,
}: {
  session: Session;
  context: CompanyContext;
  groupKey?: string;
}) {
  const mode = useProductMode();
  const groups = inventoryNavigationFor(session, mode ? mode.data?.product_family_sku_enabled ?? null : undefined);
  const group = inventoryGroups.find((item) => item.key === groupKey);
  const visible = groups.find((item) => item.key === groupKey);
  const title = group?.label ?? 'Inventory masters';
  return (
    <div className="janso-page">
      <PageNavigation
        back={{
          href: group ? '/inventory' : '/',
          label: group ? 'inventory masters' : 'business overview',
        }}
        breadcrumbs={[
          { label: 'Business overview', href: '/' },
          ...(group
            ? [{ label: 'Inventory masters', href: '/inventory' }]
            : []),
          { label: title },
        ]}
      />
      <PageHeader
        title={title}
        lede={
          visible?.description ?? group?.description ??
          'Find the product, pricing and warehouse masters for the company currently open.'
        }
      />
      {!session.company.id ? (
        <NoCompany
          action="manage inventory for"
          context={context}
          canCreate={companyPermission(session, 'company.create')}
        />
      ) : (groupKey ? !visible : groups.length === 0) ? (
        <ErrorState status={403} />
      ) : (
        <div className="janso-action-card-grid">
          {visible
            ? visible.items.map((item) => (
                <ActionCard
                  key={item.href}
                  title={item.label}
                  icon={<BoxIcon />}
                  description={item.description}
                  actionLabel={'Open ' + item.label.toLowerCase()}
                  href={masterLink(item.href, visible.href)}
                />
              ))
            : groups.map((item) => (
                <ActionCard
                  key={item.href}
                  title={item.label}
                  icon={<BoxIcon />}
                  description={item.description}
                  actionLabel="Browse masters"
                  href={item.href}
                />
              ))}
        </div>
      )}
    </div>
  );
}
