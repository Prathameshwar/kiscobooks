import { fireEvent, render, screen } from '@testing-library/react';
import { useLayoutEffect, useState } from 'react';
import { expect, it } from 'vitest';
import { BEFORE_COMPANY_CHANGE, useUnsavedChanges } from '../app/lib/use-unsaved-changes';

function Editor({ requested }: { requested: boolean[] }) {
  const [value, setValue] = useState(''), [saved, setSaved] = useState('');
  const dirty = value !== saved;
  useUnsavedChanges(() => dirty);
  // A sibling/controller can request a context change as soon as a commit finishes.
  useLayoutEffect(() => {
    requested.push(window.dispatchEvent(new Event(BEFORE_COMPANY_CHANGE, { cancelable: true })));
  }, [dirty, requested]);
  return <><input aria-label="Name" value={value} onChange={event => setValue(event.target.value)} /><button onClick={() => setSaved(value)}>Save</button></>;
}

it('blocks a company change using the newly committed draft state', () => {
  const requested: boolean[] = []; render(<Editor requested={requested} />);
  fireEvent.change(screen.getByRole('textbox', { name: 'Name' }), { target: { value: 'Operations' } });
  expect(requested.at(-1)).toBe(false);
});

it('allows a company change as soon as the saved state commits', () => {
  const requested: boolean[] = []; render(<Editor requested={requested} />);
  fireEvent.change(screen.getByRole('textbox', { name: 'Name' }), { target: { value: 'Operations' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save' }));
  expect(requested.at(-1)).toBe(true);
});
