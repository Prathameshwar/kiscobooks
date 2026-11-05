import type { Session } from '../session';
import { companyPermission } from './company-permissions';
import { inventoryGroups, productStructureGroup } from './inventory-navigation';
import { accountingMasters, accountingDescriptions } from './accounting-masters';
import { accountingResource } from './accounting-configuration-resources';
import { taxConfigs } from './tax-masters';

export type CompanyMasterCard = { label: string; href: string; permission: string; description: string };
export type CompanyMasterGroup = { key: string; label: string; description: string; kind: 'catalog' | 'accounting' | 'tax'; items: CompanyMasterCard[] };
const manufacturingGroup: CompanyMasterGroup = { key: 'manufacturing', label: 'Manufacturing definitions', kind: 'catalog',
    description: 'Reusable operation specifications and immutable revisions.',
    items: [{ label: 'Manufacturing operations', href: '/masters/manufacturing-operations', permission: 'manufacturing_operation.read', description: 'Define operations and publish specifications with optional service references.' }, {label:'Manufacturing routes',href:'/masters/manufacturing-routes',permission:'manufacturing_route.read',description:'Arrange sequential steps with pinned operation revisions and exact time definitions.'}, { label: 'Bills of materials', href: '/masters/boms', permission: 'bom.read', description: 'Prepare single-level recipes, immutable publications and dated production applicability.' }],
  };

export const companyMasterGroups: CompanyMasterGroup[] = [
  { key: 'promotion-definitions', label: 'Sales promotion definitions', kind: 'catalog', description: 'Reviewed offer combinations and commercial definition history.', items: [{ label: 'Promotion stacking policies', href: '/masters/promotion-stack-policies', permission: 'promotion_stack_policy.read', description: 'Order offer groups and explicitly permit the combinations that may be applied.' }] },
  ...inventoryGroups.flatMap(group => {
    const section = { ...group, kind: 'catalog' as const, items: group.items.filter(item => item.href.startsWith('/masters/')) };
    return group.key === 'pricing' ? [section, manufacturingGroup] : [section];
  }),
  { key: 'stock-tracking', label: 'Stock and tracking', kind: 'accounting', description: 'Warehouse quantities and costs, physical tracking, controlled dates and history.', items: [
    { label: 'Stock', href: '/inventory/stock', permission: 'accounting.stock.read', description: 'Review warehouse balances, carrying values, movements and stock account configuration.' },
  ] },
  { key: 'accounting', label: 'Accounting', description: 'Chart of accounts, parties and dated financial policies.', kind: 'accounting',
    items: [{ label: 'Account and party openings', href: '/accounting/opening', permission: 'accounting.finance.read', description: 'Prepare, import and reconcile starting ledger balances and unpaid bills.' }, ...accountingMasters.map(resource => ({
      label: resource === 'accounts' ? 'Ledger accounts' : resource === 'parties' ? 'Parties / customers / suppliers' : resource === 'exchange-rates' ? 'Exchange rates' : accountingResource(resource)!.title,
      href: '/accounting/' + resource,
      permission: 'accounting.' + (resource === 'exchange-rates' ? 'finance' : accountingResource(resource)!.family) + '.read',
      description: accountingDescriptions[resource]!,
    }))] },
  { key: 'vouchers', label: 'Vouchers', description: 'How each kind of voucher is entered.', kind: 'accounting',
    items: [{ label: 'Voucher types', href: '/masters/voucher-types', permission: 'vouchers.read', description: 'Name versions of a kind of voucher — Retail sales, Export sales — and set the entry rules each one follows.' }] },
  { key: 'tax', label: 'Tax', description: 'Tax categories, classifications, rules and dated rates.', kind: 'tax',
    items: taxConfigs.map(config => ({ label: config.title, href: '/tax/' + config.key, permission: 'tax_rule.read', description: config.description })) },
];

/** Navigation never borrows stale, department-only or another company's authority. */
export function companyMastersFor(session: Session, advanced?: boolean | null): CompanyMasterGroup[] {
  if (!session.company.id) return [];
  return companyMasterGroups
    .map(group => productStructureGroup(group, advanced))
    .map(group => ({ ...group, items: group.items.filter(item => companyPermission(session, item.permission, session.company.id)) }))
    .filter(group => group.items.length);
}
export function companyMasterPath(path: string): boolean {
  const route = path.split('?')[0]!;
  return route === '/masters' || route === '/inventory' || route.startsWith('/inventory/')
    || route === '/products/custom-fields'
    || route === '/accounting' || route === '/accounting/suppliers' || route.startsWith('/accounting/suppliers/') || route === '/tax'
    || companyMasterGroups.some(group => group.items.some(item => route === item.href || route.startsWith(item.href + '/')));
}
