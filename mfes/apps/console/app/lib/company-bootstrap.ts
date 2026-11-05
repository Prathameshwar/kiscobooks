import type { Session } from '../session';
import { organisationPermissions } from './session-authority';

/** Creation atomically grants Company Administrator on the new company only.
 * `creating` plans those post-create defaults; it grants no authority itself.
 */
export function companyBootstrapAccess(
  session: Pick<Session, 'grants'>,
  { creating = false }: { creating?: boolean } = {},
) {
  const permissions = organisationPermissions(session);
  const creator = creating && permissions.includes('company.create');
  const all = (...keys: string[]) =>
    keys.every((key) => permissions.includes(key));
  const finance =
    all('accounting.finance.read') &&
    ['accounting.finance.initialize', 'accounting.finance.manage'].some((key) =>
      permissions.includes(key),
    );
  return {
    chart:
      creator ||
      finance ||
      all('accounting.setup.read', 'accounting.setup.manage'),
    books: creator || (finance && all('period.read', 'period.manage')),
    warehouses: creator || all('warehouse.read', 'warehouse.manage'),
    pricing: creator || all('price_plan.read', 'price_plan.manage'),
    units: creator || all('unit.read', 'unit.manage'),
    packs: creator || all('pack_type.read', 'pack_type.manage'),
    tax: creator || all('tax_rule.read', 'tax_rule.manage', 'tax_rule.publish'),
    productGroup: creator || all('item_group.read', 'product_type.read'),
    vouchers: creator || all('vouchers.read', 'vouchers.type.manage'),
  };
}
