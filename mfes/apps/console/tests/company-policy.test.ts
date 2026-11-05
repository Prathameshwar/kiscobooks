/**
 * The company-context boundary: what the browser may ask for, and what it may never ask for.
 *
 * Deny-by-default is the whole contract (CLAUDE.md §5.1), so the denial table matters more
 * than the allow table: anything this list does not name must be refused before a token is
 * ever attached.
 */
import { expect, it } from 'vitest';
import { allowedCompanyRequest } from '../app/lib/company-request-policy';

const company = '01990000-0000-7000-8000-000000000001';
const year = '01990000-0000-7000-8000-000000000002';

it.each([
  ['identity', 'GET', '/v1/session'],
  ['identity', 'GET', '/v1/session?company_id=' + company],
  ['identity', 'POST', '/v1/companies'],
  ['vouchers', 'POST', '/v1/companies/' + company + '/voucher-type-defaults/bootstrap'],
  ['catalog', 'POST', '/v1/companies/' + company + '/warehouse-configuration/bootstrap'],
  ['catalog', 'POST', '/v1/companies/' + company + '/pricing/bootstrap'],
  ['catalog', 'GET', '/v1/companies/' + company + '/price-plans?purpose=SALE&currency=INR&price_level_id=' + company + '&limit=2'],
  ['catalog', 'POST', '/v1/companies/' + company + '/tax-defaults/bootstrap'],
  ['catalog', 'POST', '/v1/companies/' + company + '/unit-defaults/bootstrap'],
  ['catalog', 'GET', '/v1/companies/' + company + '/item-groups?code=DEFAULT&limit=1'],
  ['catalog', 'GET', '/v1/companies/' + company + '/product-types?code=DEFAULT&limit=1'],
  ['accounting', 'GET', '/v1/companies/' + company + '/finance/field-sets/fiscal-years'],
  ['accounting', 'GET', '/v1/companies/' + company + '/finance/field-sets/fiscal-periods'],
  ['accounting', 'GET', '/v1/companies/' + company + '/financial-setup/reconciliation-review'],
  ['accounting', 'POST', '/v1/companies/' + company + '/financial-setup/reconcile'],
  ['accounting', 'POST', '/v1/companies/' + company + '/accounting-setup/initialize'],
  ['identity', 'GET', '/v1/companies?limit=50&include_unlisted=true&status=active'],
  ['identity', 'PATCH', '/v1/companies/' + company],
  ['identity', 'GET', '/v1/session/companies?limit=50'],
  ['identity', 'GET', '/v1/session/companies?q=acme&limit=20&cursor=opaque'],
  ['identity', 'PATCH', '/v1/session/preferences'],
  ['identity', 'GET', '/v1/company-features'],
  ['identity', 'GET', '/v1/companies/' + company],
  ['identity', 'GET', '/v1/companies/' + company + '/display-config'],
  ['identity', 'GET', '/v1/companies/' + company + '/features'],
  ['identity', 'GET', '/v1/companies/' + company + '/setup-readiness'],
  ['identity', 'POST', '/v1/companies/' + company + '/features/batch_tracking/enable'],
  ['identity', 'POST', '/v1/companies/' + company + '/features/batch_tracking/disable'],
  ['identity', 'GET', '/v1/company-classifications'],
  ['identity', 'GET', '/v1/entities/identity.company/field-set'],
  ['identity', 'GET', '/v1/entities/identity.company/field-set?company_id=' + company],
  ['identity', 'GET', '/v1/reference/countries'],
  ['identity', 'GET', '/v1/reference/currencies'],
  ['identity', 'GET', '/v1/reference/countries/IN/states'],
  ['identity', 'GET', '/v1/reference/countries/IN/licence-types'],
  ['accounting', 'GET', '/v1/companies/' + company + '/financial-setup'],
  ['accounting', 'GET', '/v1/companies/' + company + '/fiscal-years/next-preview'],
  ['accounting', 'GET', '/v1/companies/' + company + '/fiscal-years/next-preview?source_year_id=' + year],
  ['accounting', 'POST', '/v1/companies/' + company + '/financial-setup/initialize'],
  ['accounting', 'GET', '/v1/companies/' + company + '/fiscal-years?limit=200&sort=start_date'],
  ['accounting', 'GET', '/v1/companies/' + company + '/fiscal-years/' + year],
  ['accounting', 'GET', '/v1/companies/' + company + '/fiscal-years/' + year + '/readiness'],
  ['accounting', 'POST', '/v1/companies/' + company + '/fiscal-years/generate'],
  ['accounting', 'GET', '/v1/companies/' + company + '/fiscal-periods?status=OPEN&fiscal_year_id=' + year],
  ['accounting', 'POST', '/v1/companies/' + company + '/fiscal-periods/' + year + '/transition'],
])('allows the company setup route %s %s %s', (service, method, path) => {
  expect(allowedCompanyRequest(service, method, path)).toBe(true);
});

it.each([
  // Another service, or none.
  ['accounting', 'POST', '/v1/companies/' + company + '/fiscal-years/' + year + '/readiness'],
  ['accounting', 'POST', '/v1/companies/' + company + '/fiscal-years/next-preview'],
  ['accounting', 'GET', '/v1/companies/' + company + '/fiscal-years/next-preview?source_year_id=invalid'],
  ['accounting', 'GET', '/v1/companies/' + company + '/fiscal-years/next-preview?source_year_id=' + year + '&source_year_id=' + year],
  ['accounting', 'GET', '/v1/companies/' + company + '/fiscal-years/next-preview?expand=private'],
  ['accounting', 'GET', '/v1/companies/' + company + '/fiscal-years/' + year + '/readiness?company_id=' + company],
  ['accounting', 'GET', '/v1/companies/' + company + '/fiscal-years?limit=1&limit=200'],
  ['catalog', 'GET', '/v1/companies/' + company + '/items'],
  ['catalog', 'GET', '/v1/companies/' + company + '/pricing/bootstrap'],
  ['catalog', 'GET', '/v1/companies/' + company + '/tax-defaults/bootstrap'],
  ['catalog', 'GET', '/v1/companies/' + company + '/unit-defaults/bootstrap'],
  ['catalog', 'POST', '/v1/companies/' + company + '/unit-defaults/bootstrap?override=1'],
  ['catalog', 'POST', '/v1/companies/' + company + '/unit-defaults/bootstrap/extra'],
  ['catalog', 'POST', '/v1/companies/' + company + '/tax-defaults/bootstrap?override=1'],
  ['catalog', 'POST', '/v1/companies/' + company + '/tax-defaults/bootstrap/extra'],
  ['catalog', 'POST', '/v1/companies/' + company + '/pricing/bootstrap?override=1'],
  ['catalog', 'POST', '/v1/companies/' + company + '/warehouse-configuration/defaults'],
  ['catalog', 'GET', '/v1/companies/' + company + '/item-groups?code=PRIVATE&limit=1'],
  ['catalog', 'GET', '/v1/companies/' + company + '/item-groups?code=GENERAL&limit=200'],
  ['catalog', 'GET', '/v1/companies/' + company + '/item-groups?code=GENERAL&limit=1&cursor=extra'],
  ['catalog', 'POST', '/v1/companies/' + company + '/item-groups?code=GENERAL'],
  ['vouchers', 'GET', '/v1/companies/' + company + '/vouchers'],
  ['vouchers', 'GET', '/v1/companies/' + company + '/voucher-type-defaults/bootstrap'],
  ['vouchers', 'POST', '/v1/companies/' + company + '/voucher-type-defaults/bootstrap?override=1'],
  ['vouchers', 'POST', '/v1/companies/' + company + '/voucher-type-defaults/bootstrap/extra'],
  ['vouchers', 'POST', '/v1/companies/' + company + '/voucher-types'],
  // Another origin dressed as a path.
  ['identity', 'GET', 'https://evil.invalid/v1/session'],
  ['identity', 'GET', '//evil.invalid/v1/session'],
  ['identity', 'GET', '/v1/companies/../../secret'],
  ['identity', 'GET', '/v1/companies/%2f..%2fsecret'],
  // Reads that are not ours to make.
  ['identity', 'GET', '/v1/users'],
  ['identity', 'GET', '/v1/companies/' + company + '/memberships'],
  ['identity', 'GET', '/internal/v1/gateway/authorize'],
  // Undeclared query keys, and a selection that is not an id.
  ['identity', 'GET', '/v1/session?company_id=not-a-uuid'],
  ['identity', 'GET', '/v1/session?company_id=' + company + '&impersonate=1'],
  ['identity', 'GET', '/v1/companies?email=private'],
  ['identity', 'POST', '/v1/companies?dry_run=1'],
  ['identity', 'GET', '/v1/companies/' + company + '?expand=secrets'],
  ['accounting', 'GET', '/v1/companies/' + company + '/fiscal-years?as_of=2026-04-01&alias=x'],
  // Writes the wizard has no business making.
  ['identity', 'DELETE', '/v1/companies/' + company],
  ['identity', 'POST', '/v1/companies/' + company + '/visibility'],
  ['accounting', 'POST', '/v1/companies/' + company + '/opening-batches'],
  ['accounting', 'POST', '/v1/companies/' + company + '/journals'],
  ['accounting', 'POST', '/v1/companies/' + company + '/fiscal-periods/' + year + '/close'],
  // Right route, wrong method.
  ['identity', 'POST', '/v1/session'],
  ['identity', 'GET', '/v1/companies/' + company + '/features/batch_tracking/enable'],
  ['accounting', 'GET', '/v1/companies/' + company + '/financial-setup/initialize'],
  ['accounting', 'POST', '/v1/companies/' + company + '/fiscal-years'],
])('refuses %s %s %s', (service, method, path) => {
  expect(allowedCompanyRequest(service, method, path)).toBe(false);
});
