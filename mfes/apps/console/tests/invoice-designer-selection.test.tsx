/**
 * Selection in the invoice designer: the model, the tree, the canvas and the inspector.
 *
 * The load-bearing properties: the keyboard model is a pure function over the layout (so
 * "next" cannot mean two different things in two views), the canvas and the tree are two
 * views of one selection, a selection cannot survive a template switch, and the inspector
 * states the selection's facts in the same millimetres as everything else.
 */
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { DesignerShell } from '../app/(editor)/invoice-designer/DesignerShell';
import { ElementTree } from '../app/(editor)/invoice-designer/ElementTree';
import { SelectionInspector } from '../app/(editor)/invoice-designer/SelectionInspector';
import {
  SAMPLE_TEMPLATES,
  templateById,
} from '../app/(editor)/invoice-designer/sample-templates';
import {
  elementLabel,
  elementsOf,
  navigate,
  targetById,
  targetsOf,
  zoneLabel,
} from '../app/(editor)/invoice-designer/selection';
import type { CanvasDefinition } from '../app/(editor)/invoice-designer/layout-model';

const GST = templateById('tpl-gst-a4')!;
const TARGETS = targetsOf(GST.layout);

/** Phase 2 asserts what the inspector *states*; the handlers it now needs do nothing. */
const NO_HANDLERS = {
  onPage: vi.fn(),
  onMargins: vi.fn(),
  onTheme: vi.fn(),
  onPrint: vi.fn(),
  onSection: vi.fn(),
  onElement: vi.fn(),
  onStyle: vi.fn(),
  onColumn: vi.fn(),
  onAddColumn: vi.fn(),
  onRemoveColumn: vi.fn(),
  onMoveColumn: vi.fn(),
  onDistribute: vi.fn(),
  onAddTotalsRow: vi.fn(),
  onRemoveTotalsRow: vi.fn(),
  onMoveTotalsRow: vi.fn(),
  onAddCopy: vi.fn(),
  onRemoveCopy: vi.fn(),
  onMoveCopy: vi.fn(),
};

function renderShell(initialTemplateId = GST.id) {
  return render(
    <DesignerShell templates={SAMPLE_TEMPLATES} initialTemplateId={initialTemplateId} />,
  );
}

describe('selection model', () => {
  it('lists every zone and element, zones first, each followed by its own elements', () => {
    const zones = TARGETS.filter((target) => target.kind === 'zone');
    expect(zones).toHaveLength(GST.layout.sections.length);
    expect(TARGETS[0]?.id).toBe('sec-header');
    expect(TARGETS[1]?.zoneId).toBe('sec-header');
    expect(TARGETS).toHaveLength(
      GST.layout.sections.length +
        GST.layout.sections.reduce((sum, section) => sum + section.elements.length, 0),
    );
  });

  it('gives an element its absolute position on the page, not its offset in a zone', () => {
    // `el-title` sits at 146mm inside a zone that starts at 10mm.
    const title = targetById(TARGETS, 'el-title')!;
    expect(title.rect).toMatchObject({ xMm: 156, yMm: 10, widthMm: 44, heightMm: 7 });
  });

  it('names a thing the way a designer thinks of it', () => {
    expect(zoneLabel(GST.layout.sections[1]!)).toBe('Document details');
    // No title, so the zone type, sentence-cased.
    expect(zoneLabel(GST.layout.sections[0]!)).toBe('Header');
    // A field is its binding; a label beats it; static text is its own first words.
    expect(targetById(TARGETS, 'el-company-address')!.label).toBe('company.address');
    expect(targetById(TARGETS, 'el-no')!.label).toBe('Invoice no.');
    expect(targetById(TARGETS, 'el-title')!.label).toBe('TAX INVOICE');
  });

  it('truncates a long static text instead of filling the rail with a paragraph', () => {
    const label = elementLabel({
      id: 'x',
      type: 'TEXT',
      xMm: 0,
      yMm: 0,
      widthMm: 10,
      heightMm: 4,
      content: 'We declare that this invoice shows the actual price of the goods described',
    });
    expect(label).toHaveLength(28);
    expect(label.endsWith('…')).toBe(true);
  });

  it('falls back to the element type when there is nothing else to call it', () => {
    expect(
      elementLabel({ id: 'x', type: 'ITEM_TABLE', xMm: 0, yMm: 0, widthMm: 1, heightMm: 1 }),
    ).toBe('item table');
  });

  describe('keyboard navigation', () => {
    it('enters the page at the first zone, whichever arrow was pressed', () => {
      expect(navigate(TARGETS, null, 'next')).toBe('sec-header');
      expect(navigate(TARGETS, null, 'previous')).toBe('sec-header');
      expect(navigate(TARGETS, null, 'child')).toBe('sec-header');
    });

    it('moves between sibling zones', () => {
      expect(navigate(TARGETS, 'sec-header', 'next')).toBe('sec-meta');
      expect(navigate(TARGETS, 'sec-meta', 'previous')).toBe('sec-header');
    });

    it('steps into a zone and back out again', () => {
      expect(navigate(TARGETS, 'sec-header', 'child')).toBe('el-logo');
      expect(navigate(TARGETS, 'el-logo', 'parent')).toBe('sec-header');
    });

    it('moves between siblings inside a zone, never out of it', () => {
      expect(navigate(TARGETS, 'el-logo', 'next')).toBe('el-company');
      // `el-header-rule` is the header's last element: Down holds rather than jumping to
      // the next zone's first element, which would feel like the page moved.
      expect(navigate(TARGETS, 'el-header-rule', 'next')).toBe('el-header-rule');
      expect(navigate(TARGETS, 'el-logo', 'previous')).toBe('el-logo');
    });

    it('holds at the ends of the zone list rather than wrapping', () => {
      expect(navigate(TARGETS, 'sec-header', 'previous')).toBe('sec-header');
      expect(navigate(TARGETS, 'sec-footer', 'next')).toBe('sec-footer');
    });

    it('sends Home and End to the ends of the current level', () => {
      expect(navigate(TARGETS, 'sec-items', 'first')).toBe('sec-header');
      expect(navigate(TARGETS, 'sec-items', 'last')).toBe('sec-footer');
      expect(navigate(TARGETS, 'el-company', 'first')).toBe('el-logo');
      expect(navigate(TARGETS, 'el-company', 'last')).toBe('el-header-rule');
    });

    it('treats a childless zone’s "enter" as a no-op, not as a lost selection', () => {
      const layout: CanvasDefinition = {
        ...GST.layout,
        sections: [
          { id: 'sec-empty', type: 'CUSTOM', xMm: 0, yMm: 0, widthMm: 10, heightMm: 10, elements: [] },
        ],
      };
      const targets = targetsOf(layout);
      expect(navigate(targets, 'sec-empty', 'child')).toBe('sec-empty');
    });

    it('clears the selection, and clears to nothing on an empty page', () => {
      expect(navigate(TARGETS, 'el-logo', 'clear')).toBeNull();
      expect(navigate([], null, 'next')).toBeNull();
    });
  });
});

describe('element tree', () => {
  function renderTree(selectedId: string | null = null) {
    const onSelect = vi.fn();
    const onHover = vi.fn();
    const view = render(
      <ElementTree
        layout={GST.layout}
        targets={TARGETS}
        selectedId={selectedId}
        onSelect={onSelect}
        onHover={onHover}
      />,
    );
    return { ...view, onSelect, onHover };
  }

  it('claims aria-expanded only where there is something to expand', () => {
    const layout: CanvasDefinition = {
      ...GST.layout,
      sections: [
        { id: 'sec-empty', type: 'CUSTOM', xMm: 0, yMm: 0, widthMm: 10, heightMm: 10, elements: [] },
      ],
    };
    render(
      <ElementTree
        layout={layout}
        targets={targetsOf(layout)}
        selectedId={null}
        onSelect={vi.fn()}
        onHover={vi.fn()}
      />,
    );
    expect(screen.getByRole('treeitem')).not.toHaveAttribute('aria-expanded');
  });

  it('clears the hover when focus leaves a node, not only when the pointer does', async () => {
    const { onHover } = renderTree('sec-header');
    const node = screen.getByRole('treeitem', { name: /Header/ });
    node.focus();
    expect(onHover).toHaveBeenLastCalledWith('sec-header');
    node.blur();
    expect(onHover).toHaveBeenLastCalledWith(null);
  });

  it('is a tree of zones with their elements nested under them', () => {
    renderTree();
    const tree = screen.getByRole('tree', { name: 'Page structure' });
    const zones = within(tree).getAllByRole('treeitem', { expanded: true });
    expect(zones).toHaveLength(GST.layout.sections.length);
    expect(zones[0]).toHaveAttribute('aria-level', '1');
    expect(within(tree).getByRole('treeitem', { name: /TAX INVOICE/ })).toHaveAttribute(
      'aria-level',
      '2',
    );
  });

  it('holds exactly one tab stop, on the selection', () => {
    renderTree('el-title');
    const tabbable = screen
      .getAllByRole('treeitem')
      .filter((node) => node.getAttribute('tabindex') === '0');
    expect(tabbable).toHaveLength(1);
    expect(tabbable[0]).toHaveAccessibleName(/TAX INVOICE/);
  });

  it('puts the tab stop on the first zone when nothing is selected yet', () => {
    renderTree(null);
    const tabbable = screen
      .getAllByRole('treeitem')
      .filter((node) => node.getAttribute('tabindex') === '0');
    expect(tabbable).toHaveLength(1);
    expect(tabbable[0]).toHaveAccessibleName(/Header/);
  });

  it('selects on click and on hover reports the thing under the pointer', async () => {
    const { onSelect, onHover } = renderTree();
    const user = userEvent.setup();
    await user.click(screen.getByRole('treeitem', { name: /Item table/ }));
    expect(onSelect).toHaveBeenCalledWith('sec-items', { additive: false });

    await user.hover(screen.getByRole('treeitem', { name: /TAX INVOICE/ }));
    expect(onHover).toHaveBeenLastCalledWith('el-title');
  });

  it('moves with the same arrow keys the canvas uses', async () => {
    const { onSelect } = renderTree('sec-header');
    screen.getByRole('treeitem', { name: /Header/ }).focus();
    const user = userEvent.setup();

    await user.keyboard('{ArrowDown}');
    expect(onSelect).toHaveBeenLastCalledWith('sec-meta', { additive: false });
    await user.keyboard('{ArrowRight}');
    expect(onSelect).toHaveBeenLastCalledWith('el-logo', { additive: false });
    await user.keyboard('{Escape}');
    expect(onSelect).toHaveBeenLastCalledWith(null, { additive: false });
  });
});

describe('selection in the shell', () => {
  it('selects from the canvas and says so in the status bar', async () => {
    renderShell();
    await userEvent.setup().click(screen.getByRole('option', { name: 'TAX INVOICE' }));
    // Position as well as size: the same readout announces a keyboard nudge, and "it
    // moved" is only audible if the numbers that moved are in it.
    expect(screen.getByTestId('selection-readout')).toHaveTextContent(
      'TAX INVOICE · 156, 10 mm · 44 × 7 mm',
    );
  });

  it('announces the selection politely, because the keyboard moves it', () => {
    renderShell();
    expect(screen.getByTestId('selection-readout')).toHaveAttribute('aria-live', 'polite');
  });

  it('keeps the canvas and the tree on the same selection', async () => {
    renderShell();
    await userEvent.setup().click(screen.getByRole('treeitem', { name: /Item table/ }));
    expect(screen.getByRole('option', { name: 'Item table' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(screen.getByRole('listbox', { name: 'Page elements' })).toHaveAttribute(
      'aria-activedescendant',
      'target-sec-items',
    );
  });

  it('walks the page from the canvas with the keyboard alone', async () => {
    renderShell();
    const user = userEvent.setup();
    screen.getByRole('listbox', { name: 'Page elements' }).focus();

    await user.keyboard('{ArrowDown}');
    expect(screen.getByTestId('selection-readout')).toHaveTextContent('Header');
    await user.keyboard('{ArrowRight}');
    expect(screen.getByTestId('selection-readout')).toHaveTextContent('image');
    await user.keyboard('{ArrowDown}');
    expect(screen.getByTestId('selection-readout')).toHaveTextContent('Nandini Trading Company');
    await user.keyboard('{Escape}');
    expect(screen.getByTestId('selection-readout')).toHaveTextContent('nothing');
  });

  it('keeps hover out of the live region, so one keyboard move speaks once', async () => {
    renderShell();
    await userEvent.setup().hover(screen.getByRole('option', { name: 'Item table' }));
    expect(screen.getByTestId('selection-readout')).toHaveTextContent('nothing');
    expect(screen.getByTestId('hover-readout')).toHaveTextContent('Item table (hovered)');
  });

  it('stops reporting a hover once something is selected', async () => {
    renderShell();
    const user = userEvent.setup();
    await user.click(screen.getByRole('option', { name: 'TAX INVOICE' }));
    await user.hover(screen.getByRole('option', { name: 'Item table' }));
    expect(screen.queryByTestId('hover-readout')).not.toBeInTheDocument();
  });

  it('clears the selection with a click on bare paper', async () => {
    renderShell();
    const user = userEvent.setup();
    await user.click(screen.getByRole('option', { name: 'TAX INVOICE' }));
    await user.click(screen.getByTestId('selection-layer'));
    expect(screen.getByTestId('selection-readout')).toHaveTextContent('nothing');
  });

  it('drops the selection when the template changes, because the ids do too', async () => {
    renderShell();
    const user = userEvent.setup();
    await user.click(screen.getByRole('option', { name: 'TAX INVOICE' }));
    expect(screen.getByTestId('selection-readout')).toHaveTextContent('TAX INVOICE');

    await user.click(screen.getByRole('button', { name: /Compact invoice/ }));
    expect(screen.getByTestId('selection-readout')).toHaveTextContent('nothing');
  });
});

describe('inspector', () => {
  it('offers the page controls and teaches the keyboard model when nothing is selected', () => {
    render(<SelectionInspector layout={GST.layout} selection={null} handlers={NO_HANDLERS} />);
    expect(screen.getByRole('heading', { name: 'Page' })).toBeInTheDocument();
    expect(screen.getByLabelText('Paper size')).toHaveValue('A4');
    for (const edge of ['top', 'right', 'bottom', 'left']) {
      expect(screen.getByLabelText(`${edge} margin`)).toHaveValue('10');
    }
    expect(screen.getByText(/Nothing selected/)).toBeInTheDocument();
    expect(screen.getByText('→')).toBeInTheDocument();
  });

  it('describes a selected element in millimetres', () => {
    render(
      <SelectionInspector
        layout={GST.layout}
        selection={targetById(TARGETS, 'el-title')}
        handlers={NO_HANDLERS}
      />,
    );
    // "TAX INVOICE" is both this element's name and its printed content, so each
    // assertion names the group it means.
    const identity = screen.getByRole('heading', { name: 'Element' }).parentElement!;
    expect(within(identity).getByText('TAX INVOICE')).toBeInTheDocument();
    expect(within(identity).getByText('text')).toBeInTheDocument();
    const content = screen.getByRole('heading', { name: 'Content' }).parentElement!;
    expect(within(content).getByText('TAX INVOICE')).toBeInTheDocument();
    // Geometry is editable now, so the value lives in the control rather than in text.
    expect(screen.getByLabelText('X position')).toHaveValue('146');
    expect(screen.getByLabelText('Width')).toHaveValue('44');
    // The absolute position on the page is still stated, because it is derived.
    expect(screen.getByRole('heading', { name: 'Geometry' }).parentElement).toHaveTextContent(
      '156, 10 mm',
    );
  });

  it('shows a binding with the value the sample document resolves', () => {
    render(
      <SelectionInspector
        layout={GST.layout}
        selection={targetById(TARGETS, 'el-no')}
        handlers={NO_HANDLERS}
      />,
    );
    expect(screen.getByRole('heading', { name: 'Binding' })).toBeInTheDocument();
    expect(screen.getByText('voucher.document_number')).toBeInTheDocument();
    expect(screen.getByText('NTC/25-26/001847')).toBeInTheDocument();
  });

  it('says when a binding cannot be resolved, rather than showing an empty value', () => {
    render(
      <SelectionInspector
        layout={GST.layout}
        selection={{
          id: 'x',
          kind: 'element',
          label: 'x',
          rect: { xMm: 0, yMm: 0, widthMm: 10, heightMm: 4 },
          zoneId: 'sec-header',
          section: GST.layout.sections[0]!,
          element: {
            id: 'x',
            type: 'FIELD_BINDING',
            xMm: 0,
            yMm: 0,
            widthMm: 10,
            heightMm: 4,
            bindingPath: 'voucher.nope',
          },
        }}
        handlers={NO_HANDLERS}
      />,
    );
    expect(screen.getByText(/cannot resolve this path/)).toBeInTheDocument();
  });

  it('summarises an item table’s columns and how much of its width they use', () => {
    render(
      <SelectionInspector
        layout={GST.layout}
        selection={targetById(TARGETS, 'el-items')}
        handlers={NO_HANDLERS}
      />,
    );
    expect(screen.getByRole('heading', { name: 'Columns' })).toBeInTheDocument();
    expect(screen.getByText(/190 of 190 mm used/)).toBeInTheDocument();
    // One toggle and one width per column, so a designer can see what the table spends.
    expect(screen.getByLabelText('Show HSN/SAC')).toBeInTheDocument();
    expect(screen.getByLabelText('HSN/SAC width')).toHaveValue('16');
  });

  it('lists the totals rows a totals block prints', () => {
    render(
      <SelectionInspector
        layout={GST.layout}
        selection={targetById(TARGETS, 'el-totals')}
        handlers={NO_HANDLERS}
      />,
    );
    expect(screen.getByRole('heading', { name: 'Totals rows' })).toBeInTheDocument();
    expect(screen.getByText('Amount in words')).toBeInTheDocument();
  });

  it('explains a zone’s placement mode, which decides whether it can be dragged', () => {
    render(
      <SelectionInspector
        layout={GST.layout}
        selection={targetById(TARGETS, 'sec-header')}
        handlers={NO_HANDLERS}
      />,
    );
    expect(screen.getByRole('heading', { name: 'Zone' })).toBeInTheDocument();
    // Placement is a switch now, not stated text: off means the zone lays itself out.
    expect(screen.getByRole('switch', { name: 'Free placement' })).toHaveAttribute(
      'aria-checked',
      'false',
    );
    expect(screen.getByText(/Turn this on to move them by hand/)).toBeInTheDocument();
  });
});
