/**
 * Direct manipulation: history, dragging, resizing, guides, nudging and inline text.
 *
 * The load-bearing properties: a burst of keystrokes is one undo and a whole drag is one
 * more; a drag moves the same paper distance at any zoom; snapping, bounds and alignment
 * come from the layout model rather than the gesture; guides appear during a drag and never
 * linger; and every pointer gesture has a keyboard equivalent that is exact.
 *
 * Geometry is checked against the GST fixture, whose header zone sits at (10, 10) and is
 * 190 × 28mm. `el-company` starts at 44, 0, 96 × 7mm *within* that zone — so the inspector
 * reads 44 while the canvas target and the inline editor read the page position, 54.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { PX_PER_MM } from '@janso/ui';
import { DesignerShell } from '../app/(editor)/invoice-designer/DesignerShell';
import { SAMPLE_TEMPLATES } from '../app/(editor)/invoice-designer/sample-templates';
import {
  COALESCE_MS,
  HISTORY_LIMIT,
  canRedo,
  canUndo,
  createHistory,
  record,
  redo,
  redoLabel,
  undo,
  undoLabel,
} from '../app/(editor)/invoice-designer/history';

const COMPANY = 'Nandini Trading Company';

function renderShell(initialTemplateId = 'tpl-gst-a4') {
  return render(
    <DesignerShell templates={SAMPLE_TEMPLATES} initialTemplateId={initialTemplateId} />,
  );
}

/** A ring or grip, with the pointer-capture API jsdom does not implement. */
function capturable(node: HTMLElement): HTMLElement {
  node.setPointerCapture = vi.fn();
  node.hasPointerCapture = () => true;
  node.releasePointerCapture = vi.fn();
  return node;
}

function option(name: string): HTMLElement {
  return capturable(screen.getByRole('option', { name }));
}

async function select(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.click(option(name));
}

/** One pointer gesture: down, one move of `byPx`, up. */
async function drag(
  user: ReturnType<typeof userEvent.setup>,
  node: HTMLElement,
  byPx: { x: number; y: number },
) {
  capturable(node);
  await user.pointer([
    { target: node, keys: '[MouseLeft>]', coords: { clientX: 400, clientY: 300 } },
    { target: node, coords: { clientX: 400 + byPx.x, clientY: 300 + byPx.y } },
    { target: node, keys: '[/MouseLeft]' },
  ]);
}

const mm = (value: number) => value * PX_PER_MM;

describe('history', () => {
  it('records a state and steps back and forward through it', () => {
    let history = createHistory('a', 0);
    expect(canUndo(history)).toBe(false);

    history = record(history, 'b', 'move', 1000);
    history = record(history, 'c', 'resize', 5000);
    expect(history.present.state).toBe('c');

    history = undo(history);
    expect(history.present.state).toBe('b');
    expect(canRedo(history)).toBe(true);

    history = redo(history);
    expect(history.present.state).toBe('c');
  });

  it('collapses same-labelled edits inside the window into one entry', () => {
    let history = createHistory('', 0);
    // Typing "TAX" is three changes and one action.
    history = record(history, 'T', 'content:el-title', 1000);
    history = record(history, 'TA', 'content:el-title', 1100);
    history = record(history, 'TAX', 'content:el-title', 1200);
    expect(history.past).toHaveLength(1);

    history = undo(history);
    expect(history.present.state).toBe('');
  });

  it('starts a new entry once the window has passed', () => {
    let history = createHistory('', 0);
    history = record(history, 'a', 'content:x', 1000);
    history = record(history, 'ab', 'content:x', 1000 + COALESCE_MS + 1);
    expect(history.past).toHaveLength(2);
  });

  it('starts a new entry when the action changes', () => {
    let history = createHistory('a', 0);
    history = record(history, 'b', 'content:x', 1000);
    history = record(history, 'c', 'move:x', 1050);
    expect(history.past).toHaveLength(2);
  });

  it('keeps a discrete action out of the window, however fast it repeats', () => {
    let history = createHistory('a', 0);
    // Two presses of "Bring forward" 100ms apart are two actions. Coalescing is for
    // continuous input — a burst of keystrokes, a drag — and a button press is already
    // whole: collapse them and one undo drops the element back past where it started.
    history = record(history, 'b', 'stack:forward', 1000, { coalesce: false });
    history = record(history, 'c', 'stack:forward', 1100, { coalesce: false });
    expect(history.past).toHaveLength(2);

    history = undo(history);
    expect(history.present.state).toBe('b');
  });

  it('drops the redo branch once you edit after undoing', () => {
    let history = createHistory('a', 0);
    history = record(history, 'b', 'one', 1000);
    history = undo(history);
    expect(canRedo(history)).toBe(true);

    history = record(history, 'c', 'two', 2000);
    expect(canRedo(history)).toBe(false);
  });

  it('ignores a state that did not change', () => {
    const history = record(createHistory('a', 0), 'a', 'noop', 1000);
    expect(history.past).toHaveLength(0);
  });

  it('holds at the ends rather than failing', () => {
    const history = createHistory('a', 0);
    expect(undo(history)).toBe(history);
    expect(redo(history)).toBe(history);
  });

  it('keeps the stack bounded', () => {
    let history = createHistory(0, 0);
    for (let step = 1; step <= HISTORY_LIMIT + 20; step += 1) {
      history = record(history, step, `step-${step}`, step * 10_000);
    }
    expect(history.past).toHaveLength(HISTORY_LIMIT);
    // The oldest entries fell off the bottom, so the earliest reachable is not the first.
    expect(history.past[0]?.state).toBeGreaterThan(0);
  });

  it('names what undo and redo would do, for the toolbar', () => {
    let history = record(createHistory('a', 0), 'b', 'move:el-logo', 1000);
    expect(undoLabel(history)).toBe('move:el-logo');
    history = undo(history);
    expect(redoLabel(history)).toBe('move:el-logo');
    expect(undoLabel(history)).toBeNull();
  });
});

describe('undo in the editor', () => {
  it('starts with both buttons disabled and enables undo after a change', async () => {
    renderShell();
    const user = userEvent.setup();
    expect(screen.getByRole('button', { name: 'Undo' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Redo' })).toBeDisabled();

    const grid = screen.getByLabelText('Grid step');
    await user.clear(grid);
    await user.type(grid, '10{Enter}');
    expect(screen.getByRole('button', { name: 'Undo' })).toBeEnabled();
  });

  it('takes a change back and puts it forward again', async () => {
    renderShell();
    const user = userEvent.setup();
    const grid = screen.getByLabelText('Grid step');
    await user.clear(grid);
    await user.type(grid, '10{Enter}');
    expect(screen.getByTestId('design-canvas-grid')).toHaveStyle({ backgroundSize: '10mm 10mm' });

    await user.click(screen.getByRole('button', { name: 'Undo' }));
    expect(screen.getByTestId('design-canvas-grid')).toHaveStyle({ backgroundSize: '5mm 5mm' });

    await user.click(screen.getByRole('button', { name: 'Redo' }));
    expect(screen.getByTestId('design-canvas-grid')).toHaveStyle({ backgroundSize: '10mm 10mm' });
  });

  it('names the action it would take back', async () => {
    renderShell();
    const user = userEvent.setup();
    await user.click(screen.getByRole('radio', { name: 'Landscape' }));
    expect(screen.getByRole('button', { name: 'Undo' })).toHaveAttribute('title', 'Undo page');
  });

  it('undoes from the keyboard, the only way most people will', async () => {
    renderShell();
    const user = userEvent.setup();
    await user.click(screen.getByRole('radio', { name: 'Landscape' }));
    expect(screen.getByTestId('design-canvas-paper')).toHaveStyle({ width: '297mm' });

    await user.keyboard('{Control>}z{/Control}');
    expect(screen.getByTestId('design-canvas-paper')).toHaveStyle({ width: '210mm' });

    await user.keyboard('{Control>}{Shift>}z{/Shift}{/Control}');
    expect(screen.getByTestId('design-canvas-paper')).toHaveStyle({ width: '297mm' });

    // ctrl+Y is the other redo, and Windows users reach for it first.
    await user.keyboard('{Control>}z{/Control}');
    await user.keyboard('{Control>}y{/Control}');
    expect(screen.getByTestId('design-canvas-paper')).toHaveStyle({ width: '297mm' });
  });

  it('keeps each template’s history apart', async () => {
    renderShell();
    const user = userEvent.setup();
    const grid = screen.getByLabelText('Grid step');
    await user.clear(grid);
    await user.type(grid, '20{Enter}');

    await user.click(screen.getByRole('button', { name: /Compact invoice/ }));
    expect(screen.getByRole('button', { name: 'Undo' })).toBeDisabled();

    await user.click(screen.getByRole('button', { name: /GST tax invoice/ }));
    expect(screen.getByRole('button', { name: 'Undo' })).toBeEnabled();
  });

  it('collapses a typed heading into one undo', async () => {
    renderShell();
    const user = userEvent.setup();
    await select(user, 'TAX INVOICE');
    const text = screen.getByLabelText('Static text');
    await user.clear(text);
    await user.type(text, 'BILL');

    await user.click(screen.getByRole('button', { name: 'Undo' }));
    // One undo takes the whole burst back to where it started.
    expect(screen.getByLabelText('Static text')).toHaveValue('TAX INVOICE');
  });
});

describe('dragging on the canvas', () => {
  it('moves an element by the paper distance the pointer travelled', async () => {
    const { container } = renderShell();
    const user = userEvent.setup();
    await select(user, COMPANY);

    await drag(user, option(COMPANY), { x: mm(6), y: 0 });
    expect(screen.getByLabelText('X position')).toHaveValue('50');
    // The page itself moved, not just the number in the panel.
    expect(container.querySelector('[data-element="el-company"]')).toHaveStyle({ left: '50mm' });
  });

  it('moves the same paper distance at half zoom', async () => {
    renderShell();
    const user = userEvent.setup();
    await select(user, COMPANY);
    await user.click(screen.getByRole('button', { name: 'Zoom out' }));
    await user.click(screen.getByRole('button', { name: 'Zoom out' }));
    expect(screen.getByTestId('zoom-readout')).toHaveTextContent('50%');

    // Half the screen pixels for the same 6mm of paper.
    await drag(user, option(COMPANY), { x: mm(6) * 0.5, y: 0 });
    expect(screen.getByLabelText('X position')).toHaveValue('50');
  });

  it('snaps a dragged element to the grid', async () => {
    renderShell();
    const user = userEvent.setup();
    await select(user, COMPANY);

    // 44 + 8 = 52, which is not on the 5mm grid.
    await drag(user, option(COMPANY), { x: mm(8), y: 0 });
    expect(screen.getByLabelText('X position')).toHaveValue('50');
  });

  it('stops a dragged element at the edge of its zone, grid or no grid', async () => {
    renderShell();
    const user = userEvent.setup();
    await select(user, COMPANY);

    await drag(user, option(COMPANY), { x: mm(400), y: 0 });
    // The zone is 190mm and the element 96mm, so 94mm is as far right as it goes — the
    // edge wins over the grid, because an element hanging out of its zone prints wrong.
    expect(screen.getByLabelText('X position')).toHaveValue('94');
  });

  it('resizes from a west handle, moving the origin but not the far edge', async () => {
    const { container } = renderShell();
    const user = userEvent.setup();
    await select(user, COMPANY);

    const west = container.querySelector('[data-handle="w"]') as HTMLElement;
    await drag(user, west, { x: mm(-10), y: 0 });
    // Left edge out to 35; the right edge stayed at 140, so the element grew to 105.
    expect(screen.getByLabelText('X position')).toHaveValue('35');
    expect(screen.getByLabelText('Width')).toHaveValue('105');
  });

  it('resizes from the south-east corner without moving the origin', async () => {
    const { container } = renderShell();
    const user = userEvent.setup();
    await select(user, COMPANY);

    const corner = container.querySelector('[data-handle="se"]') as HTMLElement;
    await drag(user, corner, { x: mm(5), y: mm(5) });
    expect(screen.getByLabelText('X position')).toHaveValue('44');
    expect(screen.getByLabelText('Width')).toHaveValue('101');
    expect(screen.getByLabelText('Height')).toHaveValue('10');
  });

  it('is one undo for the whole drag, not one per pointer event', async () => {
    renderShell();
    const user = userEvent.setup();
    await select(user, COMPANY);

    const ring = option(COMPANY);
    await user.pointer([
      { target: ring, keys: '[MouseLeft>]', coords: { clientX: 400, clientY: 300 } },
      { target: ring, coords: { clientX: 400 + mm(4), clientY: 300 } },
      { target: ring, coords: { clientX: 400 + mm(10), clientY: 300 } },
      { target: ring, coords: { clientX: 400 + mm(16), clientY: 300 } },
      { target: ring, keys: '[/MouseLeft]' },
    ]);
    expect(screen.getByLabelText('X position')).not.toHaveValue('44');

    await user.click(screen.getByRole('button', { name: 'Undo' }));
    expect(screen.getByLabelText('X position')).toHaveValue('44');
  });

  it('measures every move from where the drag started, not from the last one', async () => {
    renderShell();
    const user = userEvent.setup();
    await select(user, COMPANY);

    const ring = option(COMPANY);
    await user.pointer([
      { target: ring, keys: '[MouseLeft>]', coords: { clientX: 400, clientY: 300 } },
      { target: ring, coords: { clientX: 400 + mm(20), clientY: 300 } },
      // Back to where it began: the element must come home, not drift by 20mm.
      { target: ring, coords: { clientX: 400, clientY: 300 } },
      { target: ring, keys: '[/MouseLeft]' },
    ]);
    expect(screen.getByLabelText('X position')).toHaveValue('44');
  });

  it('treats a click with a pixel of jitter as a click, not a move', async () => {
    renderShell();
    const user = userEvent.setup();
    await select(user, COMPANY);

    const ring = option(COMPANY);
    await user.pointer([
      { target: ring, keys: '[MouseLeft>]', coords: { clientX: 400, clientY: 300 } },
      { target: ring, coords: { clientX: 401, clientY: 300 } },
      { target: ring, keys: '[/MouseLeft]' },
    ]);
    expect(screen.getByTestId('edit-count')).toHaveTextContent('No changes');
  });

  it('does not offer to drag a zone, which the layout places', async () => {
    const { container } = renderShell();
    const user = userEvent.setup();
    await select(user, 'Header');

    expect(screen.getByRole('option', { name: 'Header' })).not.toHaveAttribute('data-draggable');
    expect(container.querySelector('[data-handle="se"]')).toBeNull();
  });

  it('offers no drag and no handles on a shipped template', async () => {
    const { container } = renderShell('tpl-thermal-80');
    const user = userEvent.setup();
    await select(user, 'NANDINI TRADING CO.');

    expect(screen.getByRole('option', { name: 'NANDINI TRADING CO.' })).not.toHaveAttribute(
      'data-draggable',
    );
    // Eight grips that do nothing when pulled would be worse than none.
    expect(container.querySelector('[data-handle="se"]')).toBeNull();
  });
});

describe('alignment guides', () => {
  it('draws a guide while dragging and clears it when the pointer lifts', async () => {
    renderShell();
    const user = userEvent.setup();
    await select(user, COMPANY);

    const ring = option(COMPANY);
    await user.pointer([
      { target: ring, keys: '[MouseLeft>]', coords: { clientX: 400, clientY: 300 } },
      { target: ring, coords: { clientX: 400 + mm(6), clientY: 300 } },
    ]);

    const layer = screen.getByTestId('guide-layer');
    // The element's right edge lands on the title's left edge, 156mm across the page.
    expect(layer.querySelector('[data-axis="x"][data-kind="edge"]')).toHaveStyle({
      left: '156mm',
    });
    expect(screen.getByTestId('guide-readout')).toHaveTextContent(/aligned on \d+ guides?/);

    await user.pointer({ target: ring, keys: '[/MouseLeft]' });
    expect(screen.queryByTestId('guide-layer')).not.toBeInTheDocument();
    expect(screen.queryByTestId('guide-readout')).not.toBeInTheDocument();
  });

  it('corrects a near miss onto the guide it found', async () => {
    renderShell();
    const user = userEvent.setup();
    // With the grid off, the only thing left to aim with is the alignment itself.
    await user.click(screen.getByLabelText('Snap to grid'));
    await select(user, COMPANY);

    // 0.6mm left of the address below it, which shares its left edge. Far enough to be a
    // drag rather than jitter, near enough for the guide to claim it.
    await drag(user, option(COMPANY), { x: mm(-0.6), y: 0 });
    expect(screen.getByLabelText('X position')).toHaveValue('44');
  });

  it('snaps a resized edge to the grid and leaves the handle in charge', async () => {
    const { container } = renderShell();
    const user = userEvent.setup();
    await select(user, COMPANY);

    const east = container.querySelector('[data-handle="e"]') as HTMLElement;
    await drag(user, east, { x: mm(3), y: 0 });
    // The dragged edge went to the next grid line at 145, so the width is 101 — and no
    // alignment pulled it anywhere, which would fight the handle being held.
    expect(screen.getByLabelText('Width')).toHaveValue('101');
    expect(screen.getByLabelText('X position')).toHaveValue('44');
  });
});

describe('nudging with the keyboard', () => {
  it('moves one exact millimetre with alt, off-grid if that is where it lands', async () => {
    renderShell();
    const user = userEvent.setup();
    await select(user, COMPANY);

    await user.keyboard('{Alt>}{ArrowRight}{/Alt}');
    expect(screen.getByLabelText('X position')).toHaveValue('45');

    // The point of a fine nudge: it keeps going rather than sticking to the grid line.
    await user.keyboard('{Alt>}{ArrowRight}{/Alt}');
    expect(screen.getByLabelText('X position')).toHaveValue('46');
  });

  it('moves a grid step with alt+shift, landing on the grid', async () => {
    renderShell();
    const user = userEvent.setup();
    await select(user, COMPANY);

    await user.keyboard('{Alt>}{ArrowRight}{/Alt}');
    await user.keyboard('{Alt>}{Shift>}{ArrowRight}{/Shift}{/Alt}');
    // 45 + 5 = 50, on the 5mm grid.
    expect(screen.getByLabelText('X position')).toHaveValue('50');
  });

  it('stops at the zone edge like a drag does', async () => {
    renderShell();
    const user = userEvent.setup();
    await select(user, COMPANY);

    for (let press = 0; press < 12; press += 1) {
      await user.keyboard('{Alt>}{Shift>}{ArrowRight}{/Shift}{/Alt}');
    }
    expect(screen.getByLabelText('X position')).toHaveValue('94');
  });

  it('resizes with alt+ctrl, from the bottom-right', async () => {
    renderShell();
    const user = userEvent.setup();
    await select(user, COMPANY);

    await user.keyboard('{Alt>}{Control>}{ArrowRight}{/Control}{/Alt}');
    expect(screen.getByLabelText('Width')).toHaveValue('97');
    expect(screen.getByLabelText('X position')).toHaveValue('44');

    await user.keyboard('{Alt>}{Control>}{ArrowDown}{/Control}{/Alt}');
    expect(screen.getByLabelText('Height')).toHaveValue('8');
  });

  it('leaves the plain arrows to move the selection, not the element', async () => {
    renderShell();
    const user = userEvent.setup();
    await select(user, COMPANY);
    screen.getByRole('listbox', { name: 'Page elements' }).focus();

    await user.keyboard('{ArrowUp}');
    // The selection stepped to the previous element; nothing on the page moved.
    expect(screen.getByTestId('selection-readout')).toHaveTextContent('image');
    expect(screen.getByTestId('edit-count')).toHaveTextContent('No changes');
  });

  it('reports the new position in the live region, so a nudge is audible', async () => {
    renderShell();
    const user = userEvent.setup();
    await select(user, COMPANY);

    await user.keyboard('{Alt>}{ArrowDown}{/Alt}');
    // Page coordinates: the header zone starts at (10, 10).
    expect(screen.getByTestId('selection-readout')).toHaveTextContent('54, 11 mm');
  });

  it('leaves the keyboard to a text field while one is focused', async () => {
    renderShell();
    const user = userEvent.setup();
    await select(user, 'TAX INVOICE');

    const text = screen.getByLabelText('Static text');
    await user.click(text);
    await user.keyboard('{Alt>}{ArrowRight}{/Alt}');
    // Nothing moved: the words under the caret matter more than the box around them.
    expect(screen.getByLabelText('X position')).toHaveValue('146');
    expect(screen.getByTestId('edit-count')).toHaveTextContent('No changes');
  });

  it('leaves ctrl+Z to a text field, where it means “untype that”', async () => {
    renderShell();
    const user = userEvent.setup();
    await user.click(screen.getByRole('radio', { name: 'Landscape' }));

    const grid = screen.getByLabelText('Grid step');
    await user.click(grid);
    await user.keyboard('{Control>}z{/Control}');
    // The page stayed landscape; the editor did not reach past the field for the shortcut.
    expect(screen.getByTestId('design-canvas-paper')).toHaveStyle({ width: '297mm' });
  });

  it('nudges nothing when nothing is selected', async () => {
    renderShell();
    await userEvent.setup().keyboard('{Alt>}{ArrowRight}{/Alt}');
    expect(screen.getByTestId('edit-count')).toHaveTextContent('No changes');
  });

  it('nudges nothing on a shipped template', async () => {
    renderShell('tpl-thermal-80');
    const user = userEvent.setup();
    await select(user, 'NANDINI TRADING CO.');

    await user.keyboard('{Alt>}{ArrowRight}{/Alt}');
    expect(screen.getByTestId('edit-count')).toHaveTextContent('No changes');
  });
});

describe('inline text editing', () => {
  it('opens on double-click and edits where the words print', async () => {
    const { container } = renderShell();
    const user = userEvent.setup();
    await select(user, 'TAX INVOICE');
    await user.dblClick(option('TAX INVOICE'));

    const editor = screen.getByTestId('inline-text-editor');
    expect(editor).toHaveFocus();
    expect(editor).toHaveAccessibleName('Text of TAX INVOICE');
    // Sized and placed exactly over the element, in page coordinates.
    expect(editor).toHaveStyle({ left: '156mm', top: '10mm', width: '44mm', height: '7mm' });

    await user.clear(editor);
    await user.type(editor, 'BILL OF SUPPLY');
    expect(container.querySelector('[data-element="el-title"]')).toHaveTextContent(
      'BILL OF SUPPLY',
    );
  });

  it('opens from the keyboard with Enter on the canvas', async () => {
    renderShell();
    const user = userEvent.setup();
    await select(user, 'TAX INVOICE');
    screen.getByRole('listbox', { name: 'Page elements' }).focus();

    await user.keyboard('{Enter}');
    expect(screen.getByTestId('inline-text-editor')).toBeInTheDocument();
  });

  it('collapses a burst of typing into one undo', async () => {
    renderShell();
    const user = userEvent.setup();
    await select(user, 'TAX INVOICE');
    await user.dblClick(option('TAX INVOICE'));
    await user.type(screen.getByTestId('inline-text-editor'), ' COPY');

    await user.click(screen.getByRole('button', { name: 'Undo' }));
    expect(screen.getByLabelText('Static text')).toHaveValue('TAX INVOICE');
  });

  it('closes on Escape, keeping the text it already changed', async () => {
    renderShell();
    const user = userEvent.setup();
    await select(user, 'TAX INVOICE');
    await user.dblClick(option('TAX INVOICE'));
    await user.type(screen.getByTestId('inline-text-editor'), ' COPY');
    await user.keyboard('{Escape}');

    expect(screen.queryByTestId('inline-text-editor')).not.toBeInTheDocument();
    // Escape leaves the field; undo is the way back, not a hidden revert.
    expect(screen.getByLabelText('Static text')).toHaveValue('TAX INVOICE COPY');
  });

  it('does not open over an element that carries no text', async () => {
    renderShell();
    const user = userEvent.setup();
    await select(user, 'item table');
    await user.dblClick(option('item table'));
    expect(screen.queryByTestId('inline-text-editor')).not.toBeInTheDocument();
  });

  it('keeps alt+arrow for the text field, not for the canvas', async () => {
    renderShell();
    const user = userEvent.setup();
    await select(user, 'TAX INVOICE');
    await user.dblClick(option('TAX INVOICE'));

    await user.keyboard('{Alt>}{ArrowLeft}{/Alt}');
    expect(screen.getByTestId('inline-text-editor')).toBeInTheDocument();
    // 146 within its zone — the element did not move under the caret.
    expect(screen.getByLabelText('X position')).toHaveValue('146');
  });

  it('closes when the selection moves on', async () => {
    renderShell();
    const user = userEvent.setup();
    await select(user, 'TAX INVOICE');
    await user.dblClick(option('TAX INVOICE'));
    expect(screen.getByTestId('inline-text-editor')).toBeInTheDocument();

    await user.click(option('GST — rule 46'));
    expect(screen.queryByTestId('inline-text-editor')).not.toBeInTheDocument();
  });

  it('closes when the template changes', async () => {
    renderShell();
    const user = userEvent.setup();
    await select(user, 'TAX INVOICE');
    await user.dblClick(option('TAX INVOICE'));

    await user.click(screen.getByRole('button', { name: /Delivery challan/ }));
    expect(screen.queryByTestId('inline-text-editor')).not.toBeInTheDocument();
  });

  it('offers no inline editor on a shipped template', async () => {
    renderShell('tpl-thermal-80');
    const user = userEvent.setup();
    await select(user, 'NANDINI TRADING CO.');
    await user.dblClick(option('NANDINI TRADING CO.'));
    expect(screen.queryByTestId('inline-text-editor')).not.toBeInTheDocument();
  });
});
