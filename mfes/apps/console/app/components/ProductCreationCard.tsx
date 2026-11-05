'use client';
import { useProductMode } from './ProductModeProvider';

export function ProductCreationCard({ company, href, canCreate }: { company: string; href: string; canCreate: boolean }) {
  const mode = useProductMode();
  const verified = mode?.company === company && !mode.failure && !mode.loading ? mode.data : null;
  const advanced = verified?.product_family_sku_enabled === true;
  return <section className="product-create-card" aria-label="Create product">
    <div className="product-create-card__copy">
      <span className="product-create-card__eyebrow">PRODUCT CREATION</span>
      <h2>{verified ? (advanced ? 'New Product Profile + SKUs' : 'New product') : 'Product setup'}</h2>
      <p>{verified ? (advanced ? 'Define shared details once, then set up each SKU.' : 'Create one product with its units, prices and optional opening stock.') : mode?.failure ? (mode.failure.status === 403 ? 'Product setup access is needed to choose the creation flow.' : 'Product setup could not be verified. Retry before creating a product.') : 'Checking product setup…'}</p>
      {verified && <span className="product-create-card__meta">{advanced ? '4 guided steps · Drafts can be saved' : 'Guided product creation'}</span>}
    </div>
    {verified && canCreate ? <a className="janso-btn janso-btn--primary" href={href}>{advanced ? 'Create profile and SKUs' : 'Create product'}</a> : mode?.failure && mode.failure.status !== 403 ? <button type="button" className="janso-btn janso-btn--secondary" onClick={mode.refresh}>Retry</button> : !canCreate ? <span className="product-create-card__meta">View only · creation access required</span> : <span role="status" className="product-create-card__meta">Checking setup</span>}
  </section>;
}
