import { beforeEach, expect, it, vi } from 'vitest';
import { readPublishedDesignVersion } from '../app/lib/design-templates';
import { designRequest } from '../app/lib/design-api';
import { layoutToWire } from '../app/lib/design-canvas';
import { SAMPLE_TEMPLATES } from '../app/(editor)/invoice-designer/sample-templates';

vi.mock('../app/lib/design-api', async original => ({ ...await original<typeof import('../app/lib/design-api')>(), designRequest: vi.fn() }));
const company = '01990000-0000-7000-8000-000000000001';
const template = '01990000-0000-7000-8000-000000000002';
const id = '01990000-0000-7000-8000-000000000003';
const paper = { paper_size: 'A4', page_orientation: 'PORTRAIT' };
const saved = { id, company_id: company, template_id: template, published_at: '2026-10-29T00:00:00Z',
  layout_definition: layoutToWire(SAMPLE_TEMPLATES[0]!.layout) };
beforeEach(() => vi.clearAllMocks());
it('reads only the selected published layout through the scoped template endpoint', async () => {
  vi.mocked(designRequest).mockResolvedValue(saved);
  const restored = await readPublishedDesignVersion(company, template, id, paper);
  expect(restored.schemaVersion).toBe('1.1.0');
  expect(designRequest).toHaveBeenCalledWith({ path: `/v1/companies/${company}/templates/${template}/versions/${id}` });
});
it.each([
  { company_id: '01990000-0000-7000-8000-000000000004' },
  { template_id: '01990000-0000-7000-8000-000000000004' },
  { published_at: null }, { layout_definition: { schema_version: '1.0.0' } },
])('refuses a foreign, unpublished or incompatible layout: %j', async invalid => {
  vi.mocked(designRequest).mockResolvedValue({ ...saved, ...invalid });
  await expect(readPublishedDesignVersion(company, template, id, paper)).rejects.toBeDefined();
});
