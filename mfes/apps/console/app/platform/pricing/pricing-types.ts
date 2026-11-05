import type { components } from '@janso/api-client/identity';
import { formatMoney, useDisplayConfig } from '@janso/ui';

export type Price = components['schemas']['PlatformPriceDetail'];
export type PriceItem = components['schemas']['PlatformPriceItem'];
export type PriceInput = components['schemas']['PlatformPriceInput'];
export type PricePage = components['schemas']['Page_PlatformPriceItem_'];
export const categories = [
  { value: 'platform', label: 'Platform subscription' }, { value: 'whatsapp', label: 'WhatsApp' },
  { value: 'sms', label: 'SMS' }, { value: 'email', label: 'Email' },
  { value: 'llm', label: 'AI model' }, { value: 'document', label: 'Document processing' },
];
export const units = { platform: 'none', whatsapp: 'messages', sms: 'segments', email: 'emails', llm: 'tokens', document: 'pages' } as const;
export type Draft = Record<'code' | 'name' | 'category' | 'description' | 'term_months' | 'monthly_fee' | 'unit_price' | 'output_unit_price' | 'tax_percent' | 'fx_inr_per_usd' | 'provider' | 'model' | 'is_active' | 'version', string>;
export const initial: Draft = { code: '', name: '', category: 'platform', description: '', term_months: '12', monthly_fee: '', unit_price: '0', output_unit_price: '0', tax_percent: '18', fx_inr_per_usd: '94.8228', provider: '', model: '', is_active: 'true', version: '0' };
export function draftFrom(price: Price): Draft {
  return Object.fromEntries(Object.keys(initial).map(key => [key, String(price[key as keyof Price] ?? '')])) as Draft;
}
export function usePricingMoney() {
  const config = useDisplayConfig();
  return (value: string, currency: string, precision = 2) => formatMoney(value, { ...config, currency }, { precision, display: 'code' });
}
