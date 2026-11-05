/**
 * The designer shell threading a real `company` down to the asset picker and the live
 * preview (plan P4, 2026-11-03) — as opposed to the fixture-only session every other
 * designer test renders, where there is nothing to pick from and the control stays off.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DesignerShell } from '../app/(editor)/invoice-designer/DesignerShell';
import { SAMPLE_TEMPLATES } from '../app/(editor)/invoice-designer/sample-templates';
import { designRequest } from '../app/lib/design-api';

vi.mock('../app/lib/design-api', async (original) => ({
  ...(await original<typeof import('../app/lib/design-api')>()),
  designRequest: vi.fn(),
}));

const company = '01990000-0000-7000-8000-000000000001';

async function select(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.click(screen.getByRole('option', { name }));
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(designRequest).mockResolvedValue({ items: [] });
});

describe('the asset picker, gated on a real company', () => {
  it('offers the saved-asset picker for an image once a company is open', async () => {
    render(<DesignerShell templates={SAMPLE_TEMPLATES} initialTemplateId="tpl-gst-a4" company={company} />);
    const user = userEvent.setup();
    await select(user, 'image');
    await waitFor(() => expect(screen.getByLabelText('Choose a saved asset')).toBeInTheDocument());
    expect(designRequest).toHaveBeenCalledWith(
      expect.objectContaining({ path: `/v1/companies/${company}/assets?limit=200&include_inactive=false` }),
    );
  });

  it('stays off in a company-less session, same as every other designer test', async () => {
    render(<DesignerShell templates={SAMPLE_TEMPLATES} initialTemplateId="tpl-gst-a4" />);
    const user = userEvent.setup();
    await select(user, 'image');
    expect(screen.queryByLabelText('Choose a saved asset')).not.toBeInTheDocument();
    expect(designRequest).not.toHaveBeenCalled();
  });
});
