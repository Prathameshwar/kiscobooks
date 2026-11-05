import { act, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { useState } from 'react';
import { useDraftNavigation } from '../app/lib/use-draft-navigation';
import { BEFORE_COMPANY_CHANGE } from '../app/lib/use-unsaved-changes';
import { goTo } from '../app/lib/navigate';
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn() }));
beforeEach(() => vi.clearAllMocks());
function Harness({ blocked = false, atRisk = true, onBlocked = vi.fn() }) {
  const [next, setNext] = useState<(() => void) | null>(null);
  useDraftNavigation({ atRisk, blocked, onBlocked, requestLeave: proceed => setNext(() => proceed) });
  return <><a href="/vouchers" onClick={event => event.preventDefault()}>Leave</a><a href="/bill.pdf" download onClick={event => event.preventDefault()}>Download</a>
    <a href="/vouchers" target="_blank" onClick={event => event.preventDefault()}>New tab</a>
    {next ? <button onClick={() => next()}>Confirm leave</button> : null}</>;
}
it('captures same-tab links, preserves the page until confirmation and releases the company guard on leave', async () => {
  render(<Harness />); const user = userEvent.setup();
  await user.click(screen.getByRole('link', { name: 'Leave' })); expect(goTo).not.toHaveBeenCalled();
  const blocked = new Event(BEFORE_COMPANY_CHANGE, { cancelable: true }); window.dispatchEvent(blocked); expect(blocked.defaultPrevented).toBe(true);
  await user.click(screen.getByRole('button', { name: 'Confirm leave' })); expect(goTo).toHaveBeenCalledWith(expect.stringMatching(/\/vouchers$/));
  const allowed = new Event(BEFORE_COMPANY_CHANGE, { cancelable: true }); window.dispatchEvent(allowed); expect(allowed.defaultPrevented).toBe(false);
});
it('does not offer discard while a command is blocked', async () => {
  const onBlocked = vi.fn(); render(<Harness blocked onBlocked={onBlocked} />);
  await userEvent.click(screen.getByRole('link', { name: 'Leave' }));
  expect(onBlocked).toHaveBeenCalledOnce(); expect(screen.queryByRole('button')).not.toBeInTheDocument(); expect(goTo).not.toHaveBeenCalled();
});
it('leaves clean pages, downloads, new tabs and modifier clicks alone', () => {
  const view = render(<Harness atRisk={false} />);
  fireEvent.click(screen.getByRole('link', { name: 'Leave' })); expect(screen.queryByRole('button')).not.toBeInTheDocument();
  view.rerender(<Harness />);
  fireEvent.click(screen.getByRole('link', { name: 'Download' })); fireEvent.click(screen.getByRole('link', { name: 'New tab' }));
  fireEvent.click(screen.getByRole('link', { name: 'Leave' }), { ctrlKey: true });
  expect(screen.queryByRole('button')).not.toBeInTheDocument(); expect(goTo).not.toHaveBeenCalled();
});
it('cancels supported history traversal and replays its original entry only after confirmation', async () => {
  const navigation = Object.assign(new EventTarget(), { traverseTo: vi.fn(() => ({ finished: Promise.resolve() })) });
  Object.defineProperty(window, 'navigation', { configurable: true, value: navigation });
  try {
    render(<Harness />);
    const event = Object.assign(new Event('navigate', { cancelable: true }), { navigationType: 'traverse', destination: { url: location.origin + '/previous', key: 'entry-before' } });
    act(() => navigation.dispatchEvent(event)); expect(event.defaultPrevented).toBe(true);
    expect(navigation.traverseTo).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: 'Confirm leave' }));
    expect(navigation.traverseTo).toHaveBeenCalledWith('entry-before');
  } finally { Object.defineProperty(window, 'navigation', { configurable: true, value: undefined }); }
});

function withNavigation(run: (navigation: EventTarget) => void) {
  const navigation = Object.assign(new EventTarget(), { traverseTo: vi.fn(() => ({ finished: Promise.resolve() })) });
  Object.defineProperty(window, 'navigation', { configurable: true, value: navigation });
  try { run(navigation); } finally { Object.defineProperty(window, 'navigation', { configurable: true, value: undefined }); }
}
const navigate = (type: string, path: string) => Object.assign(new Event('navigate', { cancelable: true }), { navigationType: type, destination: { url: location.origin + path } });
it('lets a page rewrite its own address, even while a command is pending: that is not leaving', () => {
  withNavigation(navigation => {
    const onBlocked = vi.fn(); render(<Harness blocked onBlocked={onBlocked} />);
    // The saved bill's id is put in the address with history.replaceState, which the browser reports as a "replace" navigation.
    const event = navigate('replace', location.pathname + '?voucher_id=abc');
    act(() => { navigation.dispatchEvent(event); });
    expect(event.defaultPrevented).toBe(false); expect(onBlocked).not.toHaveBeenCalled(); expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});
it('still guards a replace or a push that goes to another page', () => {
  withNavigation(navigation => {
    render(<Harness />);
    for (const [type, path] of [['replace', '/elsewhere'], ['push', '/elsewhere'], ['push', location.pathname + '?voucher_id=abc']] as const) {
      const event = navigate(type, path);
      act(() => { navigation.dispatchEvent(event); });
      expect(event.defaultPrevented, type + ' ' + path).toBe(true);
    }
  });
});
