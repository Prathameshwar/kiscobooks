export const pricingResources = [
  'sales-channels',
  'price-levels',
  'price-plans',
] as const;
export type PricingResource = (typeof pricingResources)[number];
export const isPricingResource = (
  resource: string,
): resource is PricingResource =>
  (pricingResources as readonly string[]).includes(resource);
export type PricingAccess = Record<PricingResource, boolean> & {
  purchaseRead: boolean;
  purchaseManage: boolean;
};
