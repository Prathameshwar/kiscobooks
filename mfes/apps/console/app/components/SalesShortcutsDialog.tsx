'use client';

import { Button, Modal } from '@janso/ui';

/**
 * Every key the bill answers to, in one place.
 *
 * The keyboard path is the fast one and an unadvertised shortcut is a shortcut nobody uses. The
 * add control names its own key and the grid's caption names the movement keys, but the whole set
 * is only learnable if it is written down somewhere a reader can open without leaving the bill —
 * `Ctrl+/` is where Google's and GitHub's products put it, so that is where a reader will try.
 */
const GROUPS: readonly { readonly title: string; readonly keys: readonly (readonly [string, string])[] }[] = [
  {
    title: 'Lines',
    keys: [
      ['Tab', 'Next cell; past the last cell of the last line, a new line'],
      ['Shift Tab', 'Previous cell — also reaches a line’s buttons'],
      ['Enter', 'Same column, next line'],
      ['Shift Enter', 'Same column, previous line'],
      ['Ctrl Enter', 'Add a line at the end'],
      ['Ctrl Shift Enter', 'Add a line below this one'],
      ['Alt Enter', 'Open the line’s detail'],
      ['Ctrl D', 'Duplicate the line, and move into the copy'],
      ['% / ₹', 'In a discount: make it a percentage, or an amount'],
      ['Alt ↑ / Alt ↓', 'Move the line'],
      ['Ctrl Backspace', 'Remove the line — from the start of a cell; elsewhere it deletes a word'],
      ['Esc', 'Put a figure back to what the bill holds'],
    ],
  },
  {
    title: 'The bill',
    keys: [
      ['Ctrl S', 'Save the draft'],
      ['Ctrl /', 'Show these keys'],
    ],
  },
];

export function SalesShortcutsDialog({ onClose }: { onClose: () => void }) {
  return (
    <Modal
      open
      title="Keyboard shortcuts"
      onClose={onClose}
      footer={<Button onClick={onClose}>Done</Button>}
    >
      {GROUPS.map((group) => (
        <section key={group.title} className="janso-entry__keys" aria-label={group.title}>
          <h3 className="janso-entry__keys-title">{group.title}</h3>
          {/* A description list: each key is a term and what it does is its definition, which is
            * how a screen reader announces the pair together. */}
          <dl className="janso-entry__keys-list">
            {group.keys.map(([key, does]) => (
              <div key={key} className="janso-entry__keys-row">
                <dt>
                  <kbd className="janso-command__kbd">{key}</kbd>
                </dt>
                <dd>{does}</dd>
              </div>
            ))}
          </dl>
        </section>
      ))}
    </Modal>
  );
}
