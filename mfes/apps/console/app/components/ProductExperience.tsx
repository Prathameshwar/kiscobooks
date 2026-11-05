'use client';
import type { ReactNode } from 'react';
import { Notice } from '@janso/ui';
import { useProductMode } from './ProductModeProvider';
import { SimpleProductDirectory } from './SimpleProductDirectory';
import type { ClassificationAccess } from '../lib/product-classification-resources';

export function ProductExperience({ company, access, initialQuery, canImport, children }: {
  company: string; access: ClassificationAccess; initialQuery: string; canImport: boolean; children: ReactNode;
}) {
  const mode = useProductMode();
  if (!mode || mode.company !== company) return <Notice tone="warning">Product setup could not be verified for this company.</Notice>;
  if (mode.failure) return <Notice tone="warning">Product setup could not be verified. <button type="button" className="janso-link" onClick={mode.refresh}>Retry</button></Notice>;
  if (mode.loading || !mode.data) return <p role="status">Checking product setup…</p>;
  if (mode.data.product_family_sku_enabled) return children;
  return <>
    <SimpleProductDirectory company={company} access={access} initialQuery={initialQuery} canImport={canImport} />
  </>;
}
