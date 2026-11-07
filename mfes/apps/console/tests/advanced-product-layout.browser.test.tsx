import { reviewProductLayout } from './product-layout-review';
import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { AdvancedProductWizard } from '../app/components/AdvancedProductWizard';
import { masterRequest } from '../app/lib/catalog-master-api';
import { useProductMode } from '../app/components/ProductModeProvider';
import { COMPANY } from './product-classification-fixtures';

vi.mock('../app/lib/catalog-master-api', () => ({ masterRequest: vi.fn() }));
vi.mock('../app/components/ProductModeProvider', () => ({ useProductMode: vi.fn() }));
vi.mock('../app/components/ProductCatalogCustomFields', () => ({ ProductCatalogCustomFields: () => null }));
const mode = { company_id: COMPANY, row_version: 2, policy_generation: 4, product_family_sku_enabled: true };
const field = (key: string, label: string) => ({ key, label, source: 'native', visible: true, writable: true, conditional_access: false, required: true, order: 1 });
const options = { company_id: COMPANY, kind: 'GOODS', today: '2026-11-05', currency: 'INR', mode, default_group_id: null, selected_type: null, max_skus_per_draft: 64, defaults: { product_type_revision_id: null, configuration: { source_version: 9, options: { variants_mode: 'OPTIONAL' } } }, family_fields: { company_id: COMPANY, entity_type: 'catalog.product_family', source_version: 7, fields: [field('name', 'Profile name'), field('code', 'Profile code')] }, sku_fields: { company_id: COMPANY, entity_type: 'catalog.item', source_version: 8, fields: [] } };


it.runIf(process.env.QA_PRODUCT_CONFIG_BROWSER === '1')('keeps Profile creation within desktop and phone widths in all themes', async () => {
  vi.mocked(useProductMode).mockReturnValue({ company: COMPANY, data: mode, loading: false, failure: null, refresh: vi.fn() });
  vi.mocked(masterRequest).mockImplementation(async request => request.path.includes('/options?') ? options as never : [] as never);
  const view = render(<AdvancedProductWizard company={COMPANY} mode={mode} />);
  await screen.findByRole('textbox', { name: 'Profile name' });
  await reviewProductLayout(view.container, 'profile-create');
  view.unmount();

}, 120000);
import { AdvancedSkuStep } from '../app/components/AdvancedSkuStep';
import { AdvancedSetupStep } from '../app/components/AdvancedSetupStep';
import { AdvancedOpeningReviewStep } from '../app/components/AdvancedOpeningReviewStep';
import { newWork, type AdvancedOptions } from '../app/lib/advanced-product-draft';
import { entryDefaults } from './product-entry-fixtures';
import { fields } from './product-classification-fixtures';
it.runIf(process.env.QA_PRODUCT_CONFIG_BROWSER === '1').each(['skus','business','opening'])('reviews Profile creation %s step in all themes and widths', async scenario => {
  const defaults = entryDefaults(new URLSearchParams({as_of:'2026-11-07'}));
  const full = { ...options, gst_enabled:true, defaults, sku_fields:{...options.sku_fields,fields:fields('catalog.item','create')}, batch:{available:true,required:false,expiry_enabled:true,expiry_required:true,manufacture_date_required:true} } as unknown as AdvancedOptions;
  const work = newWork(); work.profile.name = 'Banjara goods Profile'; work.profile.code='BANJARA';work.skus[0]!.name='Product with a long supplier label for a physical warehouse unit';work.skus[0]!.sku='WAREHOUSE-1';
  vi.mocked(masterRequest).mockImplementation(async request=>request.path.includes('/authoring-defaults?')?{...defaults,price:{price_basis_quantity:'1',price_decimal_places:4}}as never:{items:[],page:{has_more:false}}as never);
  const common={company:COMPANY,work,options:full,errors:{},onChange:vi.fn(),disabled:false};
  const view=render(<div className="janso-page"><div className="product-wizard">{scenario==='skus'?<AdvancedSkuStep {...common}/>:scenario==='business'?<AdvancedSetupStep {...common}/>:<AdvancedOpeningReviewStep {...common} onEdit={vi.fn()}/>}</div></div>);
  await reviewProductLayout(view.container,'profile-create-'+scenario);view.unmount();
},120000);
