'use client';

import { InspectorGroup } from '@janso/ui';

import { type LayoutWarning, summarise } from './layout-warnings';

/**
 * What is wrong with the page, in sentences, each pointing at the thing it is about.
 *
 * **Every row selects its subject.** A warning a designer cannot act on is a warning they
 * learn to scroll past, and "a zone is 4mm past the right edge" is unactionable until you
 * know which zone — on a page of seven, reading the name and then hunting for it is the
 * step where this panel stops being used. Pressing the row selects the offender, so the
 * canvas, the tree and the inspector all turn to it at once.
 *
 * Errors are listed before warnings, and within each, down the page, so the list reads in
 * the order someone would fix things.
 *
 * It renders nothing when there is nothing wrong. An empty panel saying "no problems" is a
 * permanent reminder of a check that is passing, which costs rail space on every template
 * that was always fine — the heading in the toolbar already says so.
 */

type WarningsPanelProps = {
  warnings: readonly LayoutWarning[];
  onSelect: (id: string) => void;
};

export function WarningsPanel({ warnings, onSelect }: WarningsPanelProps) {
  if (warnings.length === 0) return null;

  return (
    <InspectorGroup title="Problems" hint={summarise(warnings)}>
      <ul className="janso-editor__issues" data-testid="warnings">
        {warnings.map((warning) => (
          <li key={`${warning.code}-${warning.targetId}-${warning.message}`}>
            <button
              type="button"
              className="janso-editor__issue"
              data-severity={warning.severity}
              onClick={() => onSelect(warning.targetId)}
            >
              {/* The severity is in the accessible name, not only in the colour: this list
                * is read aloud as often as it is looked at. */}
              <span className="janso-editor__issue-kind">
                {warning.severity === 'error' ? 'Error' : 'Warning'}
              </span>
              <span className="janso-editor__issue-text">{warning.message}</span>
            </button>
          </li>
        ))}
      </ul>
    </InspectorGroup>
  );
}
