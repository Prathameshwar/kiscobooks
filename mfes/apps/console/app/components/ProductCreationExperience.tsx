'use client';
import { useRef } from 'react';
import type { ProductMode } from './ProductModeProvider';
import { ErrorState, Notice } from '@janso/ui';
import { useProductMode } from './ProductModeProvider';
import { SimpleProductCreate } from './SimpleProductCreate';
import { AdvancedProductWizard } from './AdvancedProductWizard';

export function ProductCreationExperience({ company, returnTo, advancedOnly = false }: { company: string; returnTo?: string; advancedOnly?: boolean }) {
  const mode = useProductMode();
  const entry = useRef<ProductMode | null>(null);
  if (!entry.current && mode?.company === company && mode.data && !mode.failure && !mode.loading) entry.current = mode.data;
  if (entry.current?.product_family_sku_enabled) return <AdvancedProductWizard company={company} returnTo={returnTo} mode={entry.current} />;
  if (!mode || mode.company !== company) return <ErrorState status={403} detail="Product setup could not be verified for this company." />;
  if (mode.failure) return <div className="janso-page"><Notice tone="warning">{mode.failure.status === 403 ? 'Product setup access is needed to choose the creation flow.' : 'Product setup could not be verified. Retry before creating a product.'}</Notice><button type="button" className="janso-btn janso-btn--secondary" onClick={mode.refresh}>Retry product setup</button></div>;
  if (mode.loading || !mode.data) return <p className="janso-page" role="status">Checking product setup…</p>;
  if (advancedOnly) return <ErrorState status={403} detail="Product Profiles require Advanced product mode. Review the company's product structure setting before creating a Profile." />;
  if (entry.current && (mode.data.product_family_sku_enabled !== entry.current.product_family_sku_enabled || mode.data.row_version !== entry.current.row_version)) return <Notice tone="warning">Product setup changed. Reload and review the creation flow before continuing.</Notice>;
  return <SimpleProductCreate company={company} returnTo={returnTo} />;
}
