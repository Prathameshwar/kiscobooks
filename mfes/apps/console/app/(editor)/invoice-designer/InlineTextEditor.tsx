'use client';

import { useEffect, useRef } from 'react';
import type { CanvasElement } from './layout-model';
import type { Target } from './selection';

/**
 * Editing an element's text where it prints.
 *
 * A textarea sized and styled exactly like the element it covers, so the words wrap where
 * they will wrap on paper. The inspector has the same field; this exists because reading a
 * heading in a side panel and reading it on the page are different acts, and a designer
 * fixing "TAX INVOCE" wants to be looking at the invoice.
 *
 * Plain text only, and committed as it is typed — the layout is in memory, and the history
 * coalesces a burst of keystrokes into one undo.
 */

type InlineTextEditorProps = {
  target: Target;
  element: CanvasElement;
  onChange: (value: string) => void;
  onClose: () => void;
};

export function InlineTextEditor({ target, element, onChange, onClose }: InlineTextEditorProps) {
  const box = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    const field = box.current;
    if (!field) return;
    field.focus();
    // The caret lands at the end: a designer double-clicks a heading to amend it far more
    // often than to retype it from nothing.
    field.setSelectionRange(field.value.length, field.value.length);
  }, []);

  const style = element.style ?? {};

  return (
    <textarea
      ref={box}
      className="janso-canvas__inline"
      aria-label={`Text of ${target.label}`}
      value={element.content ?? ''}
      style={{
        left: `${target.rect.xMm}mm`,
        top: `${target.rect.yMm}mm`,
        width: `${target.rect.widthMm}mm`,
        height: `${target.rect.heightMm}mm`,
        fontSize: style.fontSizePt ? `${style.fontSizePt}pt` : undefined,
        fontWeight: style.fontWeight === 'bold' ? 700 : undefined,
        textAlign: style.textAlign,
        textTransform: style.uppercase ? 'uppercase' : undefined,
      }}
      onChange={(event) => onChange(event.target.value)}
      onBlur={onClose}
      onKeyDown={(event) => {
        // Escape leaves the field; the text already changed, and undo is the way back.
        if (event.key === 'Escape') {
          event.preventDefault();
          onClose();
        }
        // Enter inserts a line break in a paragraph, so leaving is ctrl+Enter — the
        // convention everywhere a textarea is edited in place.
        if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
          event.preventDefault();
          onClose();
        }
        // The canvas owns the arrows for navigation; inside a text field they belong to
        // the caret.
        event.stopPropagation();
      }}
      data-testid="inline-text-editor"
    />
  );
}
