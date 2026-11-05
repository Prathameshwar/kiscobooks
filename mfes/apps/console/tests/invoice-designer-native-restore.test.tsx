import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { DesignerShell, type DesignerPersistence } from '../app/(editor)/invoice-designer/DesignerShell';
import { SAMPLE_TEMPLATES } from '../app/(editor)/invoice-designer/sample-templates';

const original = SAMPLE_TEMPLATES.find(template => template.id === 'tpl-gst-a4')!;
const version = (id: string, versionNumber: number) => ({ id, versionNumber,
  createdAt: '2026-10-29T00:00:00Z', publishedAt: '2026-10-29T00:00:00Z', changeSummary: 'Saved native layout' });
const template = { ...original, liveVersionId: 'native-v2', versions: [version('native-v2', 2), version('native-v1', 1)] };
function persistence(loadVersion: () => Promise<typeof original.layout>): DesignerPersistence {
  return { saveDraft: vi.fn(), publish: vi.fn(), pending: false, failure: null, uncertain: false,
    reload: vi.fn(), loadVersion };
}
it('loads a native historical version and restores it as one undoable edit', async () => {
  const saved = structuredClone(original.layout);
  saved.page.gridStepMm = 20;
  const loadVersion = vi.fn().mockResolvedValue(saved);
  render(<DesignerShell templates={[template]} initialTemplateId={template.id} persistence={persistence(loadVersion)} />);
  const before = screen.getByLabelText('Grid step');
  const current = (before as HTMLInputElement).value;
  fireEvent.click(screen.getByRole('button', { name: 'Restore version 1 into the editor' }));
  await waitFor(() => expect(screen.getByLabelText('Grid step')).toHaveValue('20'));
  expect(loadVersion).toHaveBeenCalledWith('native-v1');
  fireEvent.click(screen.getByRole('button', { name: 'Undo' }));
  expect(screen.getByLabelText('Grid step')).toHaveValue(current);
});
it('preserves the current layout when native version loading fails', async () => {
  const loadVersion = vi.fn().mockRejectedValue(new Error('Version unavailable. Try again.'));
  render(<DesignerShell templates={[template]} initialTemplateId={template.id} persistence={persistence(loadVersion)} />);
  const current = (screen.getByLabelText('Grid step') as HTMLInputElement).value;
  fireEvent.click(screen.getByRole('button', { name: 'Restore version 1 into the editor' }));
  await screen.findByRole('alert');
  expect(screen.getByLabelText('Grid step')).toHaveValue(current);
  expect(screen.getByRole('button', { name: 'Undo' })).toBeDisabled();
});
it('blocks another restore and editing while the selected version loads', async () => {
  let complete!: (value: typeof original.layout) => void;
  const loadVersion = vi.fn(() => new Promise<typeof original.layout>(resolve => { complete = resolve; }));
  render(<DesignerShell templates={[template]} initialTemplateId={template.id} persistence={persistence(loadVersion)} />);
  const restore = screen.getByRole('button', { name: 'Restore version 1 into the editor' });
  const current = (screen.getByLabelText('Grid step') as HTMLInputElement).value;
  fireEvent.click(restore);
  expect(restore).toBeDisabled();
  expect(screen.getByLabelText('Grid step')).toBeDisabled();
  await userEvent.type(screen.getByLabelText('Grid step'), '9');
  expect(screen.getByLabelText('Grid step')).toHaveValue(current);
  await act(async () => complete(original.layout));
  expect(loadVersion).toHaveBeenCalledTimes(1);
});
