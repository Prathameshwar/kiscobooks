/**
 * Which service calls the sales bill page may make, and nothing else.
 *
 * Its own allowlist behind its own route (`app/api/sales-entry`), deny by default, rather than
 * one more branch of the product route's: a money document's surface should be readable in one
 * place, so a reviewer can see every call a sales bill can make without tracing twenty policies.
 *
 * Every path is company-scoped. The browser names the company, but the proxy attaches the
 * session's own token and every service resolves the actor's scope against the company again
 * (CLAUDE.md §5.2) — this list narrows what can be asked, it never grants anything.
 */

const ID = '[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}';
const COMPANY = '^/v1/companies/' + ID;

type Rule = { readonly service: string; readonly methods: readonly string[]; readonly route: RegExp };

const rule = (service: string, methods: readonly string[], route: string): Rule => ({
  service,
  methods,
  route: new RegExp(COMPANY + route + '$', 'i'),
});

const RULES: readonly Rule[] = [
  /* — the issuing company: its state and its GST registration, which the place of supply needs — */
  rule('identity', ['GET'], ''),
  rule('identity', ['GET'], '/tax-registrations'),
  /* — the bill type, its class and series, and what the policy resolves to — */
  rule('vouchers', ['GET'], '/voucher-types'),
  rule('vouchers', ['GET'], `/voucher-types/${ID}(?:/(?:field-set|effective-configuration))?`),
  rule('vouchers', ['GET'], '/(?:voucher-classes|voucher-series|voucher-capabilities)'),
  /* — the draft: create, read, edit, calculate, accept, submit, approve — */
  rule('vouchers', ['POST'], '/vouchers'),
  rule('vouchers', ['GET', 'PUT'], `/vouchers/${ID}`),
  rule('vouchers', ['GET'], `/vouchers/${ID}/(?:history|field-set)`),
  rule('vouchers', ['POST'], `/vouchers/${ID}/(?:invoice-preview|invoice-acceptance|submit|approve)`),
  /* — the customer: who, which receivable, where, and how much credit — */
  rule('accounting', ['GET'], `/(?:parties|accounts|party-addresses|open-items)(?:/${ID})?`),
  rule('accounting', ['GET'], '/(?:party-address-uses|party-credit-policies|party-tax-registrations)'),
  rule('accounting', ['GET'], `/open-items/${ID}/balance`),
  rule('accounting', ['GET'], '/subledger/ageing'),
  rule('accounting', ['POST'], '/credit/check'),
  /* — what is sold: items, units, price levels, prices, tax classification — */
  rule('catalog', ['GET'], `/(?:items|units|price-levels)`),
  rule('catalog', ['GET'], '/customer-pricing/effective'),
  // The unit a line is priced in: an item's unit bindings, and the revision in force.
  rule('catalog', ['GET'], `/items/${ID}/unit-bindings`),
  rule('catalog', ['GET'], `/item-unit-bindings/${ID}/revisions`),
  rule('catalog', ['GET'], '/tax-reference/hsn-sac'),
  rule('catalog', ['POST'], '/(?:prices/resolve|tax-configurations/resolve)'),
];

/** Whether the sales bill page may make this call. Anything not listed is refused. */
export function allowedSalesEntryRequest(service: string, method: string, path: string): boolean {
  // The same traversal and encoding refusals every console policy makes, before any matching:
  // a `..` or an encoded slash is how a listed prefix gets walked off its own route.
  if (path.includes('\\') || path.includes('..') || path.includes('#') || /%2f|%5c/i.test(path)) return false;
  const route = path.split('?')[0] ?? '';
  return RULES.some((entry) => entry.service === service && entry.methods.includes(method) && entry.route.test(route));
}
