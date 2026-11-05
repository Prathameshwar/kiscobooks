import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import { useEditorDraft } from '../app/platform/useEditorDraft';
import { BEFORE_COMPANY_CHANGE, useUnsavedChanges } from '../app/lib/use-unsaved-changes';

const allowed = () => window.dispatchEvent(new Event(BEFORE_COMPANY_CHANGE, { cancelable: true }));
function Editor() {
  const editor = useEditorDraft('company-review', { name: '' });
  return <><input aria-label="Name" value={editor.draft.name} onChange={event => editor.change({ name: event.target.value })} /><button onClick={editor.saved}>Save</button></>;
}
it('blocks company changes while an existing draft is dirty and permits them after save or unmount', () => {
  const view = render(<Editor />);
  expect(allowed()).toBe(true);
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Unsaved' } });
  expect(allowed()).toBe(false);
  fireEvent.click(screen.getByRole('button', { name: 'Save' }));
  expect(allowed()).toBe(true);
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Another draft' } });
  expect(allowed()).toBe(false);
  view.unmount(); expect(allowed()).toBe(true);
});
it('retains native unload protection and follows the current dirty state', () => {
  function Guard({ dirty }: { dirty: boolean }) { useUnsavedChanges(() => dirty); return null; }
  const view = render(<Guard dirty />);
  expect(window.dispatchEvent(new Event('beforeunload', { cancelable: true }))).toBe(false);
  view.rerender(<Guard dirty={false} />);
  expect(allowed()).toBe(true);
  expect(window.dispatchEvent(new Event('beforeunload', { cancelable: true }))).toBe(true);
});
