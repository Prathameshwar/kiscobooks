/**
 * Working on several elements at once, in the editor.
 *
 * The load-bearing properties: shift and ctrl add, clicking a member again removes it, a
 * marquee catches what it touches, a group drag keeps the arrangement, the panel offers
 * only what the selection can actually do, the per-element panel steps aside for a group,
 * every button is one undo, and a shipped template still refuses all of it.
 *
 * Geometry is the GST fixture. The header zone is at (10, 10) and 190 × 28mm; inside it
 * `el-company` is at 44, 0 (96 × 7) and `el-title` at 146, 0 (44 × 7) — so the inspector
 * reads zone-relative numbers while the canvas and the Arrange panel read page ones.
 */
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { PX_PER_MM } from '@janso/ui';
import { DesignerShell } from '../app/(editor)/invoice-designer/DesignerShell';
import {
  type DesignTemplate,
  SCHEMA_VERSION,
} from '../app/(editor)/invoice-designer/layout-model';
import { SAMPLE_TEMPLATES } from '../app/(editor)/invoice-designer/sample-templates';

const COMPANY = 'Nandini Trading Company';
const TITLE = 'TAX INVOICE';
const NOTE = 'GST — rule 46';

/**
 * Two elements sharing a baseline, alone on a page, with the grid off — the smallest page
 * that can tell a correct alignment from a self-alignment. Grid snapping is off on purpose:
 * this fixture is about where the aim comes from, not about where the grid is.
 */
const BASELINE_PAIR: DesignTemplate = {
  id: 'tpl-pair',
  code: 'PAIR',
  name: 'Baseline pair',
  status: 'DRAFT',
  isSystem: false,
  liveVersionId: null,
  versions: [],
  layout: {
    schemaVersion: SCHEMA_VERSION,
    page: {
      size: 'A4',
      orientation: 'PORTRAIT',
      margins: { top: 10, right: 10, bottom: 10, left: 10, unit: 'mm' },
      gridSnap: false,
      gridStepMm: 5,
    },
    theme: { primaryColor: '#1e40af', fontFamily: 'Inter, sans-serif', fontSizePt: 9 },
    print: { copies: ['ORIGINAL_FOR_RECIPIENT'], copyMarkPosition: 'top-right' },
    sections: [
      {
        id: 'sec-row',
        type: 'CUSTOM',
        title: 'Row',
        xMm: 10,
        yMm: 10,
        widthMm: 190,
        heightMm: 60,
        elements: [
          {
            id: 'el-left',
            type: 'TEXT',
            xMm: 0,
            yMm: 0,
            widthMm: 40,
            heightMm: 6,
            content: 'Left',
            style: {},
          },
          {
            id: 'el-right',
            type: 'TEXT',
            xMm: 60,
            yMm: 0,
            widthMm: 40,
            heightMm: 6,
            content: 'Right',
            style: {},
          },
        ],
      },
    ],
  },
};

function renderShell(initialTemplateId = 'tpl-gst-a4') {
  return render(
    <DesignerShell templates={SAMPLE_TEMPLATES} initialTemplateId={initialTemplateId} />,
  );
}

function capturable(node: HTMLElement): HTMLElement {
  node.setPointerCapture = vi.fn();
  node.hasPointerCapture = () => true;
  node.releasePointerCapture = vi.fn();
  return node;
}

function option(name: string): HTMLElement {
  return capturable(screen.getByRole('option', { name }));
}

const user = () => userEvent.setup();

/** Click, optionally holding a modifier for the whole click. */
async function click(
  session: ReturnType<typeof userEvent.setup>,
  name: string,
  modifier?: 'Shift' | 'Control',
) {
  if (!modifier) {
    await session.click(option(name));
    return;
  }
  await session.keyboard(`{${modifier}>}`);
  await session.click(option(name));
  await session.keyboard(`{/${modifier}}`);
}

const selectedNames = () =>
  screen
    .getAllByRole('option')
    .filter((node) => node.getAttribute('aria-selected') === 'true')
    .map((node) => node.getAttribute('aria-label'));

const mm = (value: number) => value * PX_PER_MM;

describe('building a selection', () => {
  it('adds with shift and with ctrl, and names the active member', async () => {
    renderShell();
    const session = user();
    await click(session, COMPANY);
    await click(session, TITLE, 'Shift');
    await click(session, NOTE, 'Control');

    expect(selectedNames()).toEqual([COMPANY, TITLE, NOTE]);
    expect(screen.getByRole('listbox', { name: 'Page elements' })).toHaveAttribute(
      'aria-activedescendant',
      'target-el-title-note',
    );
  });

  it('takes a member back out when it is clicked again', async () => {
    renderShell();
    const session = user();
    await click(session, COMPANY);
    await click(session, TITLE, 'Shift');
    await click(session, COMPANY, 'Shift');
    expect(selectedNames()).toEqual([TITLE]);
  });

  it('replaces the selection on a plain click', async () => {
    renderShell();
    const session = user();
    await click(session, COMPANY);
    await click(session, TITLE, 'Shift');
    await click(session, NOTE);
    expect(selectedNames()).toEqual([NOTE]);
  });

  it('reports the count in the status bar', async () => {
    renderShell();
    const session = user();
    await click(session, COMPANY);
    await click(session, TITLE, 'Shift');
    expect(screen.getByTestId('selection-readout')).toHaveTextContent(
      `2 elements · ${TITLE} active`,
    );
  });

  it('extends from the tree as well, so both views build one selection', async () => {
    renderShell();
    const session = user();
    const tree = screen.getByRole('tree', { name: 'Page structure' });
    expect(tree).toHaveAttribute('aria-multiselectable', 'true');

    await session.click(within(tree).getByRole('treeitem', { name: new RegExp(COMPANY) }));
    await session.keyboard('{Shift>}');
    await session.click(within(tree).getByRole('treeitem', { name: new RegExp(TITLE) }));
    await session.keyboard('{/Shift}');
    expect(selectedNames()).toEqual([COMPANY, TITLE]);
  });

  it('extends with shift and an arrow on the canvas', async () => {
    renderShell();
    const session = user();
    await click(session, COMPANY);
    screen.getByRole('listbox', { name: 'Page elements' }).focus();
    await session.keyboard('{Shift>}{ArrowDown}{/Shift}');
    // The arrow still chose the next sibling; shift kept what was already there.
    expect(selectedNames()).toEqual([COMPANY, 'company.address']);
  });

  it('selects every element in the active zone with ctrl+A', async () => {
    renderShell();
    const session = user();
    await click(session, COMPANY);
    await session.keyboard('{Control>}a{/Control}');
    // The header zone holds seven elements and no more.
    expect(selectedNames()).toHaveLength(7);
    expect(selectedNames()).toContain('image');
    expect(selectedNames()).not.toContain('Invoice no.');
  });

  it('clears the selection with a click on bare paper', async () => {
    renderShell();
    const session = user();
    await click(session, COMPANY);
    await click(session, TITLE, 'Shift');
    await session.click(screen.getByTestId('selection-layer'));
    expect(selectedNames()).toEqual([]);
  });
});

describe('marquee', () => {
  /** The layer measures nothing in jsdom, so its box has to be supplied. */
  function measuredLayer(): HTMLElement {
    const layer = capturable(screen.getByTestId('selection-layer'));
    layer.getBoundingClientRect = () =>
      ({
        left: 0,
        top: 0,
        right: 210 * PX_PER_MM,
        bottom: 297 * PX_PER_MM,
        width: 210 * PX_PER_MM,
        height: 297 * PX_PER_MM,
        x: 0,
        y: 0,
        toJSON: () => ({}),
      }) as DOMRect;
    return layer;
  }

  async function sweep(
    session: ReturnType<typeof userEvent.setup>,
    from: { xMm: number; yMm: number },
    to: { xMm: number; yMm: number },
    modifier?: 'Shift',
  ) {
    const layer = measuredLayer();
    if (modifier) await session.keyboard(`{${modifier}>}`);
    await session.pointer([
      { target: layer, keys: '[MouseLeft>]', coords: { clientX: mm(from.xMm), clientY: mm(from.yMm) } },
      { target: layer, coords: { clientX: mm(to.xMm), clientY: mm(to.yMm) } },
      { target: layer, keys: '[/MouseLeft]' },
    ]);
    if (modifier) await session.keyboard(`{/${modifier}}`);
  }

  it('catches the elements the band touches', async () => {
    renderShell();
    // 150 → 200mm across, 8 → 20mm down: the title and its note, not the company name.
    await sweep(user(), { xMm: 150, yMm: 8 }, { xMm: 200, yMm: 20 });
    expect(selectedNames()).toEqual([TITLE, NOTE]);
  });

  it('catches an element it only clips, not just ones it swallows', async () => {
    renderShell();
    // A 2mm sliver over the company name's left edge at 54mm.
    await sweep(user(), { xMm: 53, yMm: 11 }, { xMm: 55, yMm: 13 });
    expect(selectedNames()).toEqual([COMPANY]);
  });

  it('never catches a zone, which is not an object on the page', async () => {
    renderShell();
    await sweep(user(), { xMm: 0, yMm: 0 }, { xMm: 205, yMm: 40 });
    expect(selectedNames()).not.toContain('Header');
    expect(selectedNames().length).toBeGreaterThan(3);
  });

  it('adds to the selection when shift is held', async () => {
    renderShell();
    const session = user();
    await click(session, COMPANY);
    await sweep(session, { xMm: 150, yMm: 8 }, { xMm: 200, yMm: 20 }, 'Shift');
    expect(selectedNames()).toEqual([COMPANY, TITLE, NOTE]);
  });

  it('replaces the selection without a modifier', async () => {
    renderShell();
    const session = user();
    await click(session, COMPANY);
    await sweep(session, { xMm: 150, yMm: 8 }, { xMm: 200, yMm: 20 });
    expect(selectedNames()).toEqual([TITLE, NOTE]);
  });

  it('selects nothing when the band catches nothing', async () => {
    renderShell();
    const session = user();
    await click(session, COMPANY);
    // Between the meta and parties zones, where no element sits.
    await sweep(session, { xMm: 100, yMm: 56.5 }, { xMm: 120, yMm: 57.5 });
    expect(selectedNames()).toEqual([]);
  });
});

describe('moving a group', () => {
  async function dragBy(
    session: ReturnType<typeof userEvent.setup>,
    name: string,
    byMm: { x: number; y: number },
  ) {
    const node = option(name);
    await session.pointer([
      { target: node, keys: '[MouseLeft>]', coords: { clientX: 400, clientY: 300 } },
      { target: node, coords: { clientX: 400 + mm(byMm.x), clientY: 300 + mm(byMm.y) } },
      { target: node, keys: '[/MouseLeft]' },
    ]);
  }

  it('moves every member when one of them is dragged', async () => {
    const { container } = renderShell();
    const session = user();
    await click(session, COMPANY);
    await click(session, TITLE, 'Shift');

    // The title is the anchor; it has 0mm of room to its right, so drag left. 146 - 10 is
    // 136, which the 5mm grid takes to 135, and the company name follows by the same 11mm.
    await dragBy(session, TITLE, { x: -10, y: 0 });
    expect(container.querySelector('[data-element="el-title"]')).toHaveStyle({ left: '135mm' });
    expect(container.querySelector('[data-element="el-company"]')).toHaveStyle({ left: '33mm' });
  });

  it('stops the group when one member reaches its zone edge', async () => {
    const { container } = renderShell();
    const session = user();
    await click(session, COMPANY);
    await click(session, TITLE, 'Shift');

    await dragBy(session, TITLE, { x: -400, y: 0 });
    // The company name is at 44 and cannot pass 0, so the group travels 44mm and the 102mm
    // gap between the two survives the gesture.
    expect(container.querySelector('[data-element="el-company"]')).toHaveStyle({ left: '0mm' });
    expect(container.querySelector('[data-element="el-title"]')).toHaveStyle({ left: '102mm' });
  });

  it('is one undo for the whole group drag', async () => {
    const { container } = renderShell();
    const session = user();
    await click(session, COMPANY);
    await click(session, TITLE, 'Shift');
    await dragBy(session, TITLE, { x: -10, y: 0 });

    await session.click(screen.getByRole('button', { name: 'Undo' }));
    expect(container.querySelector('[data-element="el-title"]')).toHaveStyle({ left: '146mm' });
    expect(container.querySelector('[data-element="el-company"]')).toHaveStyle({ left: '44mm' });
  });

  it('nudges the group from the keyboard too', async () => {
    const { container } = renderShell();
    const session = user();
    await click(session, COMPANY);
    await click(session, TITLE, 'Shift');
    await session.keyboard('{Alt>}{ArrowLeft}{/Alt}');
    expect(container.querySelector('[data-element="el-title"]')).toHaveStyle({ left: '145mm' });
    expect(container.querySelector('[data-element="el-company"]')).toHaveStyle({ left: '43mm' });
  });

  it('refuses to resize a group, rather than resizing whichever one is active', async () => {
    renderShell();
    const session = user();
    await click(session, COMPANY);
    await click(session, TITLE, 'Shift');
    await session.keyboard('{Alt>}{Control>}{ArrowRight}{/Control}{/Alt}');
    expect(screen.getByTestId('edit-count')).toHaveTextContent('No changes');
  });

  /*
   * Aiming, for a group.
   *
   * A purpose-built page, because the four shipped fixtures cannot show this: every near
   * alignment on a real invoice has *unselected* neighbours sharing the same line, and
   * they offer the same correction, so the defect hides behind correct behaviour. Two
   * elements alone on a page isolate it — and two elements sharing a baseline is the
   * commonest arrangement on a document.
   */
  function pairShell() {
    return render(<DesignerShell templates={[BASELINE_PAIR]} initialTemplateId="tpl-pair" />);
  }

  it('does not aim the anchor at a member of its own group', async () => {
    const { container } = pairShell();
    const session = user();
    await click(session, 'Left');
    await click(session, 'Right', 'Shift');

    // Both tops sit at 0, so the anchor's own group-mate is 1mm away after a 1mm step —
    // inside the alignment tolerance. Aiming at something that travels with you is the
    // drag that never starts.
    await dragBy(session, 'Right', { x: 0, y: 1 });
    expect(container.querySelector('[data-element="el-right"]')).toHaveStyle({ top: '1mm' });
    expect(container.querySelector('[data-element="el-left"]')).toHaveStyle({ top: '1mm' });
  });

  it('draws no guide against an element that is moving with the group', async () => {
    pairShell();
    const session = user();
    await click(session, 'Left');
    await click(session, 'Right', 'Shift');

    const node = option('Right');
    // Mid-gesture: guides are drawn only while the pointer is down, so the assertion has
    // to happen between the move and the release.
    await session.pointer([
      { target: node, keys: '[MouseLeft>]', coords: { clientX: 400, clientY: 300 } },
      { target: node, coords: { clientX: 400, clientY: 300 + mm(1) } },
    ]);
    expect(screen.queryByTestId('guide-layer')).not.toBeInTheDocument();
    await session.pointer([{ target: node, keys: '[/MouseLeft]' }]);
  });
});

describe('the Arrange panel', () => {
  async function pick(names: readonly string[]) {
    const session = user();
    for (const [index, name] of names.entries()) {
      await click(session, name, index === 0 ? undefined : 'Shift');
    }
    return session;
  }

  it('is absent with nothing selected, and present for one element', async () => {
    renderShell();
    expect(screen.queryByRole('button', { name: 'Align left' })).not.toBeInTheDocument();

    await pick([COMPANY]);
    expect(screen.getByRole('button', { name: 'Align left' })).toBeInTheDocument();
    expect(screen.getByText(/One element · alignment is against its zone/)).toBeInTheDocument();
  });

  it('states the box around the selection, in page millimetres', async () => {
    await (async () => {
      renderShell();
      await pick([COMPANY, TITLE]);
    })();
    // Company left at page 54 to title right at page 200, and 10 to 17 down.
    expect(screen.getByTestId('arrange-bounds')).toHaveTextContent('54, 10 mm · 146 × 7 mm');
  });

  it('aligns a group on one edge', async () => {
    const { container } = renderShell();
    await pick([COMPANY, TITLE]);
    await user().click(screen.getByRole('button', { name: 'Align left' }));
    // Both to the group's left edge, page 54, which is 44 inside the header zone.
    expect(container.querySelector('[data-element="el-title"]')).toHaveStyle({ left: '44mm' });
    expect(container.querySelector('[data-element="el-company"]')).toHaveStyle({ left: '44mm' });
  });

  it('aligns a lone element against its zone instead of itself', async () => {
    const { container } = renderShell();
    await pick([COMPANY]);
    await user().click(screen.getByRole('button', { name: 'Align right' }));
    // The zone is 190mm and the element 96mm wide.
    expect(container.querySelector('[data-element="el-company"]')).toHaveStyle({ left: '94mm' });
  });

  it('offers distribute only once there are three', async () => {
    renderShell();
    await pick([COMPANY, TITLE]);
    expect(screen.getByRole('button', { name: 'Distribute across' })).toBeDisabled();
    expect(screen.getByText(/Needs 3/)).toBeInTheDocument();

    await pick([COMPANY, TITLE, NOTE]);
    expect(screen.getByRole('button', { name: 'Distribute across' })).toBeEnabled();
  });

  it('restacks the selection and says where it sits', async () => {
    renderShell();
    await pick(['image']);
    // The logo is first of seven in the header.
    expect(screen.getByText(/1 of 7 in this zone/)).toBeInTheDocument();

    await user().click(screen.getByRole('button', { name: 'Bring to front' }));
    expect(screen.getByText(/7 of 7 in this zone/)).toBeInTheDocument();
  });

  it('duplicates the selection and selects the copies', async () => {
    const { container } = renderShell();
    await pick([TITLE]);
    await user().click(screen.getByRole('button', { name: 'Duplicate element' }));

    const copy = container.querySelector('[data-element="el-title-copy"]');
    // The title is flush against the right edge of its zone, so the 2mm offset turns
    // inwards rather than being clamped back on top of its source.
    expect(copy).toHaveStyle({ left: '144mm', top: '2mm' });
    // The copy is what is selected, so the next drag moves it and not the original.
    expect(selectedNames()).toEqual([TITLE]);
    expect(screen.getByRole('listbox', { name: 'Page elements' })).toHaveAttribute(
      'aria-activedescendant',
      'target-el-title-copy',
    );
  });

  it('deletes the selection and leaves nothing selected', async () => {
    const { container } = renderShell();
    await pick([TITLE, NOTE]);
    await user().click(screen.getByRole('button', { name: 'Delete 2 elements' }));

    expect(container.querySelector('[data-element="el-title"]')).toBeNull();
    expect(container.querySelector('[data-element="el-title-note"]')).toBeNull();
    expect(selectedNames()).toEqual([]);
    expect(screen.getByTestId('selection-readout')).toHaveTextContent('nothing');
  });

  it('puts a deletion back with one undo', async () => {
    const { container } = renderShell();
    await pick([TITLE, NOTE]);
    const session = user();
    await session.click(screen.getByRole('button', { name: 'Delete 2 elements' }));
    await session.click(screen.getByRole('button', { name: 'Undo' }));

    expect(container.querySelector('[data-element="el-title"]')).toBeInTheDocument();
    expect(container.querySelector('[data-element="el-title-note"]')).toBeInTheDocument();
  });

  it('hides the per-element panel for a group — one font size for four is a lie', async () => {
    renderShell();
    await pick([COMPANY]);
    expect(screen.getByLabelText('X position')).toBeInTheDocument();

    await pick([COMPANY, TITLE]);
    expect(screen.queryByLabelText('X position')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Align left' })).toBeInTheDocument();
  });

  it('offers nothing but a read-only view on a shipped template', async () => {
    renderShell('tpl-thermal-80');
    await pick(['NANDINI TRADING CO.']);
    for (const name of ['Align left', 'Bring to front', 'Duplicate element', 'Delete element']) {
      expect(screen.getByRole('button', { name })).toBeDisabled();
    }
  });

  it('keeps the selection when a refused duplicate or delete does nothing', async () => {
    renderShell('tpl-thermal-80');
    const session = await pick(['NANDINI TRADING CO.']);
    // Read-only is enforced in the edit funnel, so the panel's second half — select the
    // copies, clear after a delete — must not run either.
    await session.keyboard('{Control>}d{/Control}');
    expect(selectedNames()).toEqual(['NANDINI TRADING CO.']);
    await session.keyboard('{Delete}');
    expect(selectedNames()).toEqual(['NANDINI TRADING CO.']);
  });

  it('keeps the selection when a restack has nowhere to go', async () => {
    renderShell();
    const session = await pick([TITLE]);
    const before = screen.getByTestId('edit-count').textContent;
    // el-title-note is the last element of its zone drawn after the title, so the title
    // can move forward; the note itself cannot.
    await click(session, NOTE);
    await session.click(screen.getByRole('button', { name: 'Bring to front' }));
    await session.click(screen.getByRole('button', { name: 'Bring to front' }));
    expect(selectedNames()).toEqual([NOTE]);
    expect(screen.getByTestId('edit-count').textContent).not.toBe(before);
  });

  it('marks the active member in the tree as well as on the canvas', async () => {
    renderShell();
    const session = user();
    await click(session, COMPANY);
    await click(session, TITLE, 'Shift');

    const tree = screen.getByRole('tree', { name: 'Page structure' });
    expect(within(tree).getByRole('treeitem', { name: new RegExp(TITLE) })).toHaveAttribute(
      'data-active',
    );
    expect(within(tree).getByRole('treeitem', { name: new RegExp(COMPANY) })).not.toHaveAttribute(
      'data-active',
    );
  });

  it('leaves ctrl and a bracket to a text field', async () => {
    renderShell();
    const session = user();
    await click(session, 'image');
    expect(screen.getByText(/1 of 7 in this zone/)).toBeInTheDocument();

    await click(session, TITLE);
    await session.click(screen.getByLabelText('Static text'));
    await session.keyboard('{Control>}]{/Control}');
    // Still fifth of seven: the field had the keyboard.
    expect(screen.getByText(/5 of 7 in this zone/)).toBeInTheDocument();
  });
});

describe('keyboard shortcuts for a selection', () => {
  it('duplicates with ctrl+D', async () => {
    const { container } = renderShell();
    const session = user();
    await click(session, TITLE);
    await session.keyboard('{Control>}d{/Control}');
    expect(container.querySelector('[data-element="el-title-copy"]')).toBeInTheDocument();
  });

  it('deletes with Delete and with Backspace', async () => {
    const { container } = renderShell();
    const session = user();
    await click(session, TITLE);
    await session.keyboard('{Delete}');
    expect(container.querySelector('[data-element="el-title"]')).toBeNull();

    await click(session, NOTE);
    await session.keyboard('{Backspace}');
    expect(container.querySelector('[data-element="el-title-note"]')).toBeNull();
  });

  it('leaves Backspace to a text field, where it means a character', async () => {
    renderShell();
    const session = user();
    await click(session, TITLE);
    const text = screen.getByLabelText('Static text');
    await session.click(text);
    await session.keyboard('{Backspace}');
    expect(screen.getByLabelText('Static text')).toHaveValue('TAX INVOIC');
  });

  it('is one undo per press, even when the presses come fast', async () => {
    renderShell();
    const session = user();
    await click(session, 'image');
    // Walking an element up a stack is a repeated press, and the repeats are quick. Each
    // one is its own step back.
    await session.keyboard('{Control>}]{/Control}');
    await session.keyboard('{Control>}]{/Control}');
    expect(screen.getByText(/3 of 7 in this zone/)).toBeInTheDocument();

    await session.click(screen.getByRole('button', { name: 'Undo' }));
    expect(screen.getByText(/2 of 7 in this zone/)).toBeInTheDocument();
  });

  it('takes back one duplicate at a time', async () => {
    const { container } = renderShell();
    const session = user();
    await click(session, TITLE);
    await session.keyboard('{Control>}d{/Control}');
    // The copy is what is selected, so the second press copies the copy.
    await session.keyboard('{Control>}d{/Control}');
    expect(container.querySelector('[data-element="el-title-copy-copy"]')).toBeInTheDocument();

    await session.click(screen.getByRole('button', { name: 'Undo' }));
    expect(container.querySelector('[data-element="el-title-copy-copy"]')).toBeNull();
    expect(container.querySelector('[data-element="el-title-copy"]')).toBeInTheDocument();
  });

  it('restacks with ctrl and the brackets', async () => {
    renderShell();
    const session = user();
    await click(session, 'image');
    await session.keyboard('{Control>}]{/Control}');
    expect(screen.getByText(/2 of 7 in this zone/)).toBeInTheDocument();

    await session.keyboard('{Control>}{Shift>}]{/Shift}{/Control}');
    expect(screen.getByText(/7 of 7 in this zone/)).toBeInTheDocument();

    await session.keyboard('{Control>}{Shift>}[[{/Shift}{/Control}');
    expect(screen.getByText(/1 of 7 in this zone/)).toBeInTheDocument();
  });

  it('does nothing on a shipped template', async () => {
    const { container } = renderShell('tpl-thermal-80');
    const session = user();
    await click(session, 'NANDINI TRADING CO.');
    await session.keyboard('{Control>}d{/Control}');
    await session.keyboard('{Delete}');

    expect(container.querySelector('[data-element="el-company"]')).toBeInTheDocument();
    expect(screen.getByTestId('edit-count')).toHaveTextContent('No changes');
  });
});
