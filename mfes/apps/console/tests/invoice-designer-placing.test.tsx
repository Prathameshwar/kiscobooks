/**
 * Putting things on the page and getting out of the editor (2026-11-03).
 *
 * The owner could not tell how to place anything and found no way back. Under test: the
 * palette always has somewhere to put a click (the selected zone, else the first one);
 * plain objects — text, a line, a box, a signature — are added like fields; a dragged row
 * lands in the zone under the pointer, at that point; and Back is first in the toolbar,
 * asking before an unsaved layout is left behind. GST fixture geometry: the footer zone is
 * at 10, 244 mm, 190 × 43 mm.
 */
import { createEvent, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PX_PER_MM } from '@janso/ui';
import { DesignerShell } from '../app/(editor)/invoice-designer/DesignerShell';
import { DRAG_ELEMENT, DRAG_FIELD } from '../app/(editor)/invoice-designer/FieldPalette';
import { GalleryNav } from '../app/(editor)/invoice-designer/TemplateGallery';
import { ADDABLE_ELEMENTS, placeElement, placeField } from '../app/(editor)/invoice-designer/layout-edit';
import { SAMPLE_TEMPLATES } from '../app/(editor)/invoice-designer/sample-templates';

const user = () => userEvent.setup();
const GST = SAMPLE_TEMPLATES.find((template) => template.id === 'tpl-gst-a4')!;
const readout = () => screen.getByTestId('selection-readout').textContent ?? '';

function renderShell(initialTemplateId = 'tpl-gst-a4') {
  return render(<DesignerShell templates={SAMPLE_TEMPLATES} initialTemplateId={initialTemplateId} />);
}

/** A palette row let go over the page at a paper point; jsdom has no DragEvent or layout. */
function dropAt(type: string, value: string, xMm: number, yMm: number) {
  const paper = screen.getByTestId('design-canvas-paper');
  paper.getBoundingClientRect = () => ({ left: 0, top: 0, width: 210 * PX_PER_MM, height: 297 * PX_PER_MM }) as DOMRect;
  const dataTransfer = { types: [type], dropEffect: 'none', getData: (asked: string) => (asked === type ? value : '') };
  for (const create of [createEvent.dragOver, createEvent.drop]) {
    const event = create(paper, { dataTransfer });
    Object.defineProperties(event, { clientX: { value: xMm * PX_PER_MM }, clientY: { value: yMm * PX_PER_MM } });
    fireEvent(paper, event);
  }
}

/** The selected element's absolute position, from the status bar. */
function position(): [number, number] {
  const match = readout().match(/([\d.]+), ([\d.]+) mm ·/);
  return [Number(match?.[1]), Number(match?.[2])];
}

describe('adding to the page', () => {
  it('adds a field into the first zone when nothing is selected, and selects it', async () => {
    renderShell();
    expect(screen.getByTestId('palette-help')).toHaveTextContent('click it to add it into “Header”');
    await user().click(screen.getByRole('button', { name: 'Place Phone (company.phone)' }));
    expect(readout()).toMatch(/^Phone/);
  });

  it.each(Object.entries(ADDABLE_ELEMENTS))('adds a %s object into the selected zone', async (kind, spec) => {
    renderShell();
    const session = user();
    await session.click(within(screen.getByRole('tree', { name: 'Page structure' })).getByRole('treeitem', { name: /Footer/ }));
    await session.click(screen.getByRole('button', { name: `Add ${spec.label.toLowerCase()} to Footer` }));
    expect(readout()).toContain(`${spec.widthMm} × ${spec.heightMm} mm`);
    expect(screen.getByTestId('edit-count')).toHaveTextContent('1 change');
    // One undo takes it back off the page.
    await session.click(screen.getByRole('button', { name: 'Undo' }));
    expect(readout()).toBe('nothing');
    expect(screen.getByRole('button', { name: 'Redo' })).toBeEnabled();
    void kind;
  });

  it('drops a dragged field into the zone under the pointer, at that point', () => {
    renderShell();
    dropAt(DRAG_FIELD, 'company.phone', 60, 260);
    expect(readout()).toMatch(/^Phone/);
    const [x, y] = position();
    expect(x).toBeCloseTo(60, 0);
    expect(y).toBeCloseTo(260, 0);
  });

  it('drops a dragged object, and keeps it inside its zone', () => {
    renderShell();
    // A box 40 × 20 dropped 5mm above the footer's bottom edge is pulled back inside it.
    dropAt(DRAG_ELEMENT, 'SHAPE', 100, 282);
    const [, y] = position();
    expect(y + 20).toBeLessThanOrEqual(244 + 43 + 0.05);
    expect(readout()).toContain('40 × 20 mm');
  });

  it('ignores a drop it does not recognise', () => {
    renderShell();
    dropAt(DRAG_ELEMENT, 'SCRIPT', 60, 260);
    expect(readout()).toBe('nothing');
    expect(screen.getByTestId('edit-count')).toHaveTextContent('No changes');
  });

  it('adds nothing to a shipped template, which is read-only', () => {
    const shipped = { ...GST, id: 'tpl-shipped', isSystem: true };
    render(<DesignerShell templates={[shipped]} initialTemplateId="tpl-shipped" />);
    expect(screen.getByRole('button', { name: /Add text/ })).toBeDisabled();
    dropAt(DRAG_FIELD, 'company.phone', 60, 260);
    expect(readout()).toBe('nothing');
  });

  it('places at a point, clamped to the zone, as pure layout edits', () => {
    const footer = GST.layout.sections.find((section) => section.id === 'sec-footer')!;
    const field = placeField(GST.layout, footer.id, 'company.phone', { at: { xMm: 50, yMm: 16 } });
    const placed = field.layout.sections.find((section) => section.id === footer.id)!.elements.at(-1)!;
    expect([placed.xMm, placed.yMm, placed.bindingPath]).toEqual([50, 16, 'company.phone']);
    const box = placeElement(GST.layout, footer.id, 'SHAPE', { at: { xMm: 185, yMm: 40 } });
    const shape = box.layout.sections.find((section) => section.id === footer.id)!.elements.at(-1)!;
    expect([shape.type, shape.xMm + shape.widthMm, shape.yMm + shape.heightMm]).toEqual(['SHAPE', footer.widthMm, footer.heightMm]);
    expect(shape.style).toEqual({ borderWidthMm: 0.3, borderStyle: 'solid' });
    expect(placeElement(GST.layout, 'missing', 'TEXT').id).toBeNull();
  });
});

describe('the field list from the keyboard', () => {
  it('is one tab stop, with the arrows moving between fields', async () => {
    renderShell();
    const fields = screen.getAllByRole('button', { name: /^Place / });
    expect(fields.filter((field) => field.tabIndex === 0)).toHaveLength(1);
    fields[0]!.focus();
    await user().keyboard('{ArrowDown}');
    expect(document.activeElement).toBe(fields[1]);
    expect(fields[1]!.tabIndex).toBe(0);
    await user().keyboard('{End}');
    expect(document.activeElement).toBe(fields.at(-1));
  });
});

describe('leaving the designer', () => {
  const original = window.location;
  afterEach(() => {
    Object.defineProperty(window, 'location', { value: original, configurable: true });
  });

  it('offers Back first in the toolbar, to the print templates', () => {
    renderShell();
    const back = screen.getByRole('link', { name: '← Back to templates' });
    expect(back).toHaveAttribute('href', '/invoice-designer');
    expect(within(screen.getByRole('banner')).getAllByRole('link')[0]).toBe(back);
  });

  it('asks before leaving unsaved changes, and stays when told to', async () => {
    const assign = vi.fn();
    Object.defineProperty(window, 'location', { value: { ...original, assign }, configurable: true });
    renderShell();
    const session = user();
    await session.click(screen.getByRole('button', { name: 'Place Phone (company.phone)' }));
    await session.click(screen.getByRole('link', { name: '← Back to templates' }));
    const dialog = screen.getByRole('dialog', { name: 'Leave the designer?' });
    expect(dialog).toHaveTextContent('will be lost');
    await session.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('dialog', { name: 'Leave the designer?' })).toBeNull();
    expect(assign).not.toHaveBeenCalled();

    await session.click(screen.getByRole('link', { name: '← Back to templates' }));
    await session.click(screen.getByRole('button', { name: 'Leave without saving' }));
    expect(assign).toHaveBeenCalledWith('/invoice-designer');
  });

  it('warns the browser before a reload or close loses unsaved changes, and not before', async () => {
    renderShell();
    const quiet = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(quiet);
    expect(quiet.defaultPrevented).toBe(false);
    await user().click(screen.getByRole('button', { name: 'Place Phone (company.phone)' }));
    const warned = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(warned);
    expect(warned.defaultPrevented).toBe(true);
  });

  it('gives the gallery a way back into the console', () => {
    render(<GalleryNav />);
    expect(screen.getByRole('link', { name: '← Back to home' })).toHaveAttribute('href', '/');
    expect(screen.getByRole('link', { name: 'Voucher print' })).toHaveAttribute('href', '/documents/vouchers');
  });
});
