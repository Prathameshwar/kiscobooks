import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { ID, OTHER, VARIANT, VERSION, WHEN, baseResponse, mountNotification, page, readPermissions, template, variant, version } from './notification-fixtures';
const { call } = vi.hoisted(() => ({ call: vi.fn() }));
vi.mock('../app/lib/notification-api', async original => ({ ...await original<object>(), notificationCall: call }));
vi.mock('../app/components/PlatformHistory', () => ({ PlatformHistory: () => <p>Administrative history</p> }));
beforeEach(() => { call.mockReset(); call.mockImplementation(baseResponse); });
it('links from the template catalogue to a durable detail route', async () => {
  await mountNotification(['templates']);
  expect(screen.getByRole('link', { name: 'staff-alert' })).toHaveAttribute('href', '/platform/notifications/templates/' + ID);
});
it('creates a registered template with typed variables and platform scope', async () => {
  await mountNotification(['templates']); fireEvent.click(screen.getByRole('button', { name: 'Add template' }));
  fireEvent.change(screen.getByLabelText('Template key'), { target: { value: 'new-alert' } });
  fireEvent.submit(screen.getByRole('form', { name: 'Add template' }));
  await waitFor(() => expect(call).toHaveBeenCalledWith('platform', 'templates', 'POST', expect.objectContaining({ key: 'new-alert', category: 'operational', company_id: template.company_id, variable_schema: expect.objectContaining({ properties: { name: { type: 'string', maxLength: 10000 } }, required: ['name'] }) }), undefined, expect.any(AbortSignal)));
});
it('rejects duplicate variable names before sending a create', async () => {
  await mountNotification(['templates']); fireEvent.click(screen.getByRole('button', { name: 'Add template' }));
  fireEvent.change(screen.getByLabelText('Template key'), { target: { value: 'new-alert' } });
  fireEvent.click(screen.getByRole('button', { name: 'Add variable' }));
  fireEvent.change(screen.getByLabelText('Variable 2 name'), { target: { value: 'name' } });
  fireEvent.submit(screen.getByRole('form', { name: 'Add template' }));
  expect(await screen.findByText(/Variable names must be unique/)).toBeVisible();
  expect(call.mock.calls.filter(args => args[2] === 'POST')).toHaveLength(0);
});
it('creates a channel/language variant beneath the selected template', async () => {
  await mountNotification(['templates', ID]); fireEvent.click(screen.getByRole('button', { name: 'Add channel and language' }));
  fireEvent.change(screen.getByLabelText('Channel'), { target: { value: 'sms' } });
  fireEvent.submit(screen.getByRole('form', { name: 'Add channel and language' }));
  await waitFor(() => expect(call).toHaveBeenCalledWith('platform', `templates/${ID}/variants`, 'POST', { channel: 'sms', locale: 'en' }, undefined, expect.any(AbortSignal)));
});
it.each(['email', 'sms', 'whatsapp'])('creates immutable %s content using declared variables', async channel => {
  call.mockImplementation(async (owner, path, method, body) => path === 'variants/' + VARIANT && (!method || method === 'GET') ? { ...variant, channel } : baseResponse(owner, path, method, body));
  await mountNotification(['templates', ID, 'variants', VARIANT]);
  fireEvent.click(screen.getByRole('button', { name: 'Add content version' }));
  fireEvent.change(screen.getByLabelText('Message text'), { target: { value: 'Hello {{name}}' } });
  if (channel === 'whatsapp') fireEvent.change(screen.getByLabelText('Body variables in provider order'), { target: { value: 'name' } });
  fireEvent.submit(screen.getByRole('form', { name: 'Add content version' }));
  await waitFor(() => expect(call).toHaveBeenCalledWith('platform', `variants/${VARIANT}/versions`, 'POST', expect.objectContaining({ body_text: 'Hello {{name}}', channel_payload: channel === 'whatsapp' ? { components: [{ type: 'body', parameters: [{ type: 'text', variable: 'name' }] }] } : null }), undefined, expect.any(AbortSignal)));
});
it('renders a sample preview as inert content', async () => {
  call.mockImplementation(async (owner, path, method, body) => path.endsWith('/preview') ? { subject: 'Preview', body: '<script>unsafe</script>', body_html: '<img src=x onerror=unsafe()>' } : baseResponse(owner, path, method, body));
  await mountNotification(['templates', ID, 'variants', VARIANT, 'versions', VERSION]);
  fireEvent.click(screen.getByRole('button', { name: 'Preview with sample variables' }));
  fireEvent.change(screen.getByLabelText('Sample name'), { target: { value: 'Ada' } });
  fireEvent.submit(screen.getByRole('form', { name: 'Preview template' }));
  const preview = await screen.findByRole('region', { name: 'Message preview' });
  expect(within(preview).getByText('<script>unsafe</script>')).toBeVisible(); expect(preview.querySelector('script,img')).toBeNull();
});
it('allows unused optional variables to be omitted from a preview without inventing values', async () => {
  call.mockImplementation(async (owner, path, method, body) => {
    if (path === 'templates/' + ID) return { ...template, variable_schema: { ...template.variable_schema, properties: { name: { type: 'string' }, count: { type: 'integer' }, approved: { type: 'boolean' } } } };
    if (path.endsWith('/preview')) return { subject: null, body: 'Hello Ada', body_html: null };
    return baseResponse(owner, path, method, body);
  });
  await mountNotification(['templates', ID, 'variants', VARIANT, 'versions', VERSION]);
  fireEvent.click(screen.getByRole('button', { name: 'Preview with sample variables' }));
  expect(screen.getByLabelText('Sample name')).toBeRequired();
  expect(screen.getByLabelText('Sample count')).not.toBeRequired();
  expect(screen.getByLabelText('Sample approved')).toHaveValue('');
  fireEvent.change(screen.getByLabelText('Sample name'), { target: { value: 'Ada' } });
  fireEvent.submit(screen.getByRole('form', { name: 'Preview template' }));
  await screen.findByRole('region', { name: 'Message preview' });
  expect(call).toHaveBeenCalledWith('platform', `template-versions/${VERSION}/preview`, 'POST', { variables: { name: 'Ada' } }, undefined, expect.any(AbortSignal));
});
it('keeps the exact activation window and key across a lost response', async () => {
  let writes = 0;
  call.mockImplementation(async (owner, path, method, body) => {
    if (path.endsWith('/activate')) { if (++writes === 1) return Promise.reject({ status: 503, message: 'Activation response lost' }); return { id: ID }; }
    return baseResponse(owner, path, method, body);
  });
  await mountNotification(['templates', ID, 'variants', VARIANT, 'versions', VERSION]);
  fireEvent.click(screen.getByRole('button', { name: 'Activate or schedule version' }));
  fireEvent.submit(screen.getByRole('form', { name: 'Activate version' })); await screen.findByText('Activation response lost');
  fireEvent.submit(screen.getByRole('form', { name: 'Activate version' }));
  await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Activate version' })).not.toBeInTheDocument());
  const attempts = call.mock.calls.filter(args => args[1].endsWith('/activate'));
  expect(attempts).toHaveLength(2); expect(attempts[0][3]).toEqual(attempts[1][3]); expect(attempts[0][4]).toBe(attempts[1][4]);
});
it('shows immutable versions without activation controls for readers', async () => {
  await mountNotification(['templates', ID, 'variants', VARIANT, 'versions', VERSION], { permissions: readPermissions });
  expect(screen.getByText('Hello {{name}}')).toBeVisible(); expect(screen.queryByRole('button', { name: 'Activate or schedule version' })).not.toBeInTheDocument();
});
it('reports a provider-approval sync in the card that holds the control', async () => {
  call.mockImplementation(async (owner, path, method, body) => {
    if (path === 'variants/' + VARIANT && (!method || method === 'GET')) return { ...variant, channel: 'whatsapp' };
    if (path.includes('/bindings?')) return page([{ id: OTHER, external_template_id: 'wa-1', approval_status: 'pending' }]);
    return baseResponse(owner, path, method, body);
  });
  await mountNotification(['templates', ID, 'variants', VARIANT, 'versions', VERSION]);
  const button = screen.getByRole('button', { name: 'Sync approval' });
  const card = button.closest<HTMLElement>('.janso-card')!;
  fireEvent.click(button);
  // The outcome belongs beside the control: reported from the version card above, a 409 from
  // this sync would sit on the far side of the binding table from the button that caused it.
  expect(await within(card).findByText('Approval sync queued.')).toBeVisible();
});
it('presents immutable content as a wrapped source panel rather than a bare pre', async () => {
  await mountNotification(['templates', ID, 'variants', VARIANT, 'versions', VERSION], { permissions: readPermissions });
  const body = screen.getByText('Hello {{name}}');
  expect(body).toHaveClass('janso-preview__text');
  expect(body.closest('figure')).toHaveClass('janso-preview');
  expect(within(body.closest('figure')!).getByText('Message text')).toBeVisible();
});
it('denies a mismatched variant before displaying its versions', async () => {
  call.mockImplementation(async (owner, path, method, body) => path === 'variants/' + VARIANT ? { ...variant, template_id: VERSION } : baseResponse(owner, path, method, body));
  await mountNotification(['templates', ID, 'variants', VARIANT]);
  expect(screen.getByText('This channel and language does not belong to the selected template.')).toBeVisible();
  expect(call.mock.calls.some(args => args[1].startsWith(`variants/${VARIANT}/versions`))).toBe(false);
});
