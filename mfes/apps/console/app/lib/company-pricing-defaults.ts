import { companyCall } from './company-api';
import { trackingId } from './stock-tracking-resources';

type Plan = {
  id: string; company_id?: string; price_level_id: string;
  purpose: string; currency: string; tax_basis: string;
};

/** Verify worker-provisioned definitions without impersonating a pricing author. */
export async function companyPricingDefaults(company: string, level: string, currency: string): Promise<Plan> {
  if (!trackingId.test(level) || !/^[A-Z]{3}$/.test(currency))
    throw { status: 502, message: 'The company pricing defaults could not be verified.' };
  const signal = AbortSignal.timeout(30_000);
  const params = new URLSearchParams({ purpose: 'SALE', currency, price_level_id: level, limit: '2' });
  for (let attempt = 0; attempt < 30; attempt++) {
    const result = await companyCall<{ items: Plan[] }>('catalog',
      `/v1/companies/${company}/price-plans?${params}`, { signal });
    if (!Array.isArray(result.items) || result.items.length > 1 || result.items.some((plan) =>
      !trackingId.test(plan.id) || (plan.company_id && plan.company_id !== company) ||
      plan.price_level_id !== level || plan.currency !== currency || plan.purpose !== 'SALE' ||
      !['EXCLUSIVE', 'INCLUSIVE'].includes(plan.tax_basis)))
      throw { status: 502, message: 'The company pricing defaults could not be verified.' };
    if (result.items[0]) return result.items[0];
    if (signal.aborted || attempt === 29)
      throw { status: 503, message: 'The default price plan is still being prepared. Retry the remaining steps.' };
    await new Promise<void>((resolve) => setTimeout(resolve, 1000));
  }
  throw { status: 503, message: 'The default price plan is still being prepared. Retry the remaining steps.' };
}
