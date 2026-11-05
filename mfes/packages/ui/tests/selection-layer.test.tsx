/**
 * The selection layer and the inspector's anatomy.
 *
 * The load-bearing properties: the layer is one tab stop with arrow-key movement (a page
 * of 200 elements must not be 200 tab stops), hover and keyboard focus read the same, a
 * click on an element does not also select the zone behind it, the size badge is in
 * millimetres, and handles are drawn for an object but not for a region the layout places.
 */
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import {
  InspectorEmpty,
  InspectorGroup,
  InspectorRow,
  Kbd,
} from '../src/components/Inspector';
import { PX_PER_MM } from '../src/lib/paper';
import { SelectionLayer, type SelectionTarget } from '../src/components/SelectionLayer';

const TARGETS: SelectionTarget[] = [
  { id: 'sec-header', kind: 'zone', label: 'Header', rect: { xMm: 10, yMm: 10, widthMm: 190, heightMm: 28 } },
  { id: 'el-title', kind: 'element', label: 'TAX INVOICE', rect: { xMm: 156, yMm: 10, widthMm: 44, heightMm: 7 } },
  { id: 'sec-items', kind: 'zone', label: 'Item table', rect: { xMm: 10, yMm: 90, widthMm: 190, heightMm: 106 } },
];

function setup(overrides: Partial<Parameters<typeof SelectionLayer>[0]> = {}) {
  const onSelect = vi.fn();
  const onHover = vi.fn();
  const onKeyCommand = vi.fn();
  const onTransform = vi.fn();
  const result = render(
    <SelectionLayer
      targets={TARGETS}
      selectedId={null}
      hoveredId={null}
      onSelect={onSelect}
      onHover={onHover}
      onKeyCommand={onKeyCommand}
      onTransform={onTransform}
      {...overrides}
    />,
  );
  return { ...result, onSelect, onHover, onKeyCommand, onTransform };
}

describe('SelectionLayer', () => {
  it('is one listbox with one option per target, not one tab stop per element', () => {
    setup();
    const layer = screen.getByRole('listbox', { name: 'Page elements' });
    expect(layer).toHaveAttribute('tabindex', '0');
    expect(within(layer).getAllByRole('option')).toHaveLength(3);
    // No option is independently tabbable; the arrows move the selection instead.
    for (const option of within(layer).getAllByRole('option')) {
      expect(option).not.toHaveAttribute('tabindex');
    }
  });

  it('positions every target in paper millimetres', () => {
    setup();
    expect(screen.getByRole('option', { name: 'TAX INVOICE' })).toHaveStyle({
      left: '156mm',
      top: '10mm',
      width: '44mm',
      height: '7mm',
    });
  });

  it('points assistive technology at the selection with aria-activedescendant', () => {
    setup({ selectedId: 'el-title' });
    expect(screen.getByRole('listbox')).toHaveAttribute('aria-activedescendant', 'target-el-title');
    expect(screen.getByRole('option', { name: 'TAX INVOICE' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
  });

  it('reports a hover and clears it when the pointer leaves the page', async () => {
    const { onHover } = setup();
    const user = userEvent.setup();
    await user.hover(screen.getByRole('option', { name: 'Header' }));
    expect(onHover).toHaveBeenLastCalledWith('sec-header');

    await user.pointer({ target: document.body });
    expect(onHover).toHaveBeenLastCalledWith(null);
  });

  it('renders hover and selection as distinct states a stylesheet can tell apart', () => {
    setup({ selectedId: 'el-title', hoveredId: 'sec-items' });
    expect(screen.getByRole('option', { name: 'TAX INVOICE' })).toHaveAttribute(
      'data-state',
      'selected',
    );
    expect(screen.getByRole('option', { name: 'Item table' })).toHaveAttribute(
      'data-state',
      'hovered',
    );
    expect(screen.getByRole('option', { name: 'Header' })).toHaveAttribute('data-state', 'idle');
  });

  it('selects on click without also selecting the zone underneath', async () => {
    const { onSelect } = setup();
    await userEvent.setup().click(screen.getByRole('option', { name: 'TAX INVOICE' }));
    // Exactly once: the element's handler stops the click, so the zone behind it — whose
    // box contains the element — never fires.
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith('el-title', { additive: false });
  });

  it('labels the hovered and selected target on the page', () => {
    const { container } = setup({ selectedId: 'sec-header' });
    expect(container.querySelector('.janso-canvas__label')).toHaveTextContent('Header');
  });

  it('shows the selected size in millimetres', () => {
    setup({ selectedId: 'el-title' });
    expect(screen.getByTestId('selection-size')).toHaveTextContent('44 × 7 mm');
  });

  it('draws eight handles on an element and none on a zone', () => {
    const { container } = setup({ selectedId: 'el-title' });
    expect(container.querySelectorAll('.janso-canvas__handle')).toHaveLength(8);

    const zone = setup({ selectedId: 'sec-header' });
    expect(zone.container.querySelectorAll('.janso-canvas__handle')).toHaveLength(0);
  });

  it('omits handles entirely when the caller says so', () => {
    const { container } = setup({ selectedId: 'el-title', handlesFor: 'none' });
    expect(container.querySelectorAll('.janso-canvas__handle')).toHaveLength(0);
  });

  it('draws no handles when no drag is possible, rather than grips that do nothing', () => {
    const { container } = render(
      <SelectionLayer
        targets={TARGETS}
        selectedId="el-title"
        hoveredId={null}
        onSelect={vi.fn()}
        onHover={vi.fn()}
      />,
    );
    expect(container.querySelectorAll('.janso-canvas__handle')).toHaveLength(0);
    expect(screen.getByRole('option', { name: 'TAX INVOICE' })).not.toHaveAttribute(
      'data-draggable',
    );
  });

  it('keeps handles out of the accessibility tree — the keyboard resizes, not the dots', () => {
    const { container } = setup({ selectedId: 'el-title' });
    for (const handle of container.querySelectorAll('.janso-canvas__handle')) {
      expect(handle).toHaveAttribute('aria-hidden', 'true');
    }
  });

  it('turns the arrow keys, Home, End and Escape into commands', async () => {
    const { onKeyCommand } = setup({ selectedId: 'sec-header' });
    const layer = screen.getByRole('listbox');
    layer.focus();
    const user = userEvent.setup();

    for (const [key, command] of [
      ['{ArrowDown}', 'next'],
      ['{ArrowUp}', 'previous'],
      ['{ArrowRight}', 'child'],
      ['{ArrowLeft}', 'parent'],
      ['{Home}', 'first'],
      ['{End}', 'last'],
      ['{Escape}', 'clear'],
    ] as const) {
      await user.keyboard(key);
      expect(onKeyCommand).toHaveBeenLastCalledWith(command, { additive: false });
    }
  });

  it('ignores keys it has no command for, leaving them to the page', async () => {
    const { onKeyCommand } = setup({ selectedId: 'sec-header' });
    screen.getByRole('listbox').focus();
    await userEvent.setup().keyboard('{Tab}a');
    expect(onKeyCommand).not.toHaveBeenCalled();
  });

  it('clears the selection when the click lands on bare paper', async () => {
    const { onSelect } = setup({ selectedId: 'el-title' });
    await userEvent.setup().click(screen.getByTestId('selection-layer'));
    expect(onSelect).toHaveBeenCalledWith(null);
    expect(screen.queryByTestId('marquee')).not.toBeInTheDocument();
  });

  it('clears the hover when the pointer leaves a target for bare paper', async () => {
    const { onHover } = setup();
    const user = userEvent.setup();
    const target = screen.getByRole('option', { name: 'Header' });
    await user.hover(target);
    expect(onHover).toHaveBeenLastCalledWith('sec-header');
    // Still inside the layer, so the container's own pointerleave never fires.
    await user.unhover(target);
    expect(onHover).toHaveBeenLastCalledWith(null);
  });

  it('renders nothing selectable for an empty page rather than failing', () => {
    render(
      <SelectionLayer targets={[]} selectedId={null} hoveredId={null} onSelect={vi.fn()} onHover={vi.fn()} />,
    );
    expect(screen.getByRole('listbox')).toBeEmptyDOMElement();
  });
});

/**
 * The gesture contract. The layer converts screen pixels into paper millimetres once and
 * reports a delta from where the pointer went down — it never applies anything itself,
 * because snapping, bounds and alignment belong to the layout model.
 */
describe('SelectionLayer — dragging', () => {
  /** jsdom implements no pointer capture, so the node has to supply it. */
  function capturable(node: HTMLElement): HTMLElement {
    node.setPointerCapture = vi.fn();
    node.hasPointerCapture = () => true;
    node.releasePointerCapture = vi.fn();
    return node;
  }

  function ring(): HTMLElement {
    return capturable(screen.getByRole('option', { name: 'TAX INVOICE' }));
  }

  it('reports a delta in millimetres, measured from where the pointer went down', async () => {
    const { onTransform } = setup({ selectedId: 'el-title' });
    const node = ring();
    const user = userEvent.setup();

    await user.pointer([
      { target: node, keys: '[MouseLeft>]', coords: { clientX: 100, clientY: 100 } },
      { target: node, coords: { clientX: 100 + PX_PER_MM * 10, clientY: 100 + PX_PER_MM * 4 } },
      // A second move still measures from the start, not from the previous event.
      { target: node, coords: { clientX: 100 + PX_PER_MM * 15, clientY: 100 + PX_PER_MM * 4 } },
    ]);

    expect(onTransform).toHaveBeenNthCalledWith(1, {
      id: 'el-title',
      handle: null,
      dxMm: 10,
      dyMm: 4,
      phase: 'start',
    });
    expect(onTransform).toHaveBeenLastCalledWith(
      expect.objectContaining({ dxMm: 15, dyMm: 4, phase: 'move' }),
    );
  });

  it('divides by the zoom, so a drag covers the same paper at any magnification', async () => {
    const { onTransform } = setup({ selectedId: 'el-title', zoom: 2 });
    const node = ring();
    await userEvent.setup().pointer([
      { target: node, keys: '[MouseLeft>]', coords: { clientX: 100, clientY: 100 } },
      { target: node, coords: { clientX: 100 + PX_PER_MM * 20, clientY: 100 } },
    ]);
    // Twice the pixels at twice the zoom is half the paper.
    expect(onTransform).toHaveBeenLastCalledWith(expect.objectContaining({ dxMm: 10 }));
  });

  it('names the handle being pulled, and only that handle', async () => {
    const { container, onTransform } = setup({ selectedId: 'el-title' });
    const handle = capturable(container.querySelector('[data-handle="nw"]') as HTMLElement);
    await userEvent.setup().pointer([
      { target: handle, keys: '[MouseLeft>]', coords: { clientX: 100, clientY: 100 } },
      { target: handle, coords: { clientX: 100 + PX_PER_MM * 5, clientY: 100 } },
    ]);
    expect(onTransform).toHaveBeenLastCalledWith(
      expect.objectContaining({ handle: 'nw', dxMm: 5 }),
    );
  });

  it('ends the gesture with a final event, so a caller can close its history entry', async () => {
    const { onTransform } = setup({ selectedId: 'el-title' });
    const node = ring();
    const user = userEvent.setup();
    await user.pointer([
      { target: node, keys: '[MouseLeft>]', coords: { clientX: 100, clientY: 100 } },
      { target: node, coords: { clientX: 100 + PX_PER_MM * 5, clientY: 100 } },
      { target: node, keys: '[/MouseLeft]' },
    ]);
    expect(onTransform).toHaveBeenLastCalledWith(expect.objectContaining({ phase: 'end' }));
  });

  it('reports nothing for a click with a pixel of jitter in it', async () => {
    const { onTransform, onSelect } = setup({ selectedId: 'el-title' });
    const node = ring();
    await userEvent.setup().pointer([
      { target: node, keys: '[MouseLeft>]', coords: { clientX: 100, clientY: 100 } },
      { target: node, coords: { clientX: 101, clientY: 100 } },
      { target: node, keys: '[/MouseLeft]' },
    ]);
    expect(onTransform).not.toHaveBeenCalled();
    // And it still reads as a click, which is how a steady hand selects a thing.
    expect(onSelect).toHaveBeenCalledWith('el-title', { additive: false });
  });

  it('drags only the selection: an idle target is not a handle for the one next to it', async () => {
    const { onTransform } = setup({ selectedId: 'el-title' });
    const other = capturable(screen.getByRole('option', { name: 'Header' }));
    await userEvent.setup().pointer([
      { target: other, keys: '[MouseLeft>]', coords: { clientX: 100, clientY: 100 } },
      { target: other, coords: { clientX: 100 + PX_PER_MM * 10, clientY: 100 } },
    ]);
    expect(onTransform).not.toHaveBeenCalled();
  });

  it('ignores a secondary button, which would otherwise strand the gesture', async () => {
    const { onTransform } = setup({ selectedId: 'el-title' });
    const node = ring();
    await userEvent.setup().pointer([
      { target: node, keys: '[MouseRight>]', coords: { clientX: 100, clientY: 100 } },
      { target: node, coords: { clientX: 100 + PX_PER_MM * 10, clientY: 100 } },
    ]);
    expect(onTransform).not.toHaveBeenCalled();
  });

  it('activates on double-click and on Enter — the two ways into an element', async () => {
    const onActivate = vi.fn();
    setup({ selectedId: 'el-title', onActivate });
    const user = userEvent.setup();

    await user.dblClick(ring());
    expect(onActivate).toHaveBeenLastCalledWith('el-title');

    screen.getByRole('listbox').focus();
    await user.keyboard('{Enter}');
    expect(onActivate).toHaveBeenCalledTimes(2);
  });

  it('leaves the arrows to the shell while alt is held, so a nudge is not a navigation', async () => {
    const { onKeyCommand } = setup({ selectedId: 'el-title' });
    screen.getByRole('listbox').focus();
    await userEvent.setup().keyboard('{Alt>}{ArrowRight}{/Alt}');
    expect(onKeyCommand).not.toHaveBeenCalled();
  });
});

/**
 * Selecting more than one thing. A listbox already has the vocabulary: `aria-selected`
 * marks every member and `aria-activedescendant` names the one the keyboard is on.
 */
describe('SelectionLayer — multiple selection', () => {
  const MANY: SelectionTarget[] = [
    ...TARGETS,
    {
      id: 'el-note',
      kind: 'element',
      label: 'GST — rule 46',
      rect: { xMm: 156, yMm: 20, widthMm: 44, heightMm: 4 },
    },
  ];

  function many(overrides: Partial<Parameters<typeof SelectionLayer>[0]> = {}) {
    const onSelect = vi.fn();
    const onMarquee = vi.fn();
    const result = render(
      <SelectionLayer
        targets={MANY}
        selectedId="el-note"
        selectedIds={['el-title', 'el-note']}
        hoveredId={null}
        onSelect={onSelect}
        onHover={vi.fn()}
        onTransform={vi.fn()}
        onMarquee={onMarquee}
        {...overrides}
      />,
    );
    return { ...result, onSelect, onMarquee };
  }

  it('says it is multi-selectable, and marks every member', () => {
    many();
    expect(screen.getByRole('listbox')).toHaveAttribute('aria-multiselectable', 'true');
    expect(screen.getByRole('option', { name: 'TAX INVOICE' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(screen.getByRole('option', { name: 'GST — rule 46' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(screen.getByRole('option', { name: 'Header' })).toHaveAttribute(
      'aria-selected',
      'false',
    );
  });

  it('names the active member, so it is clear which one the keyboard will act on', () => {
    many();
    expect(screen.getByRole('listbox')).toHaveAttribute(
      'aria-activedescendant',
      'target-el-note',
    );
    expect(screen.getByRole('option', { name: 'GST — rule 46' })).toHaveAttribute('data-active');
    expect(screen.getByRole('option', { name: 'TAX INVOICE' })).not.toHaveAttribute(
      'data-active',
    );
  });

  it('reports shift and ctrl as adding, and a plain click as replacing', async () => {
    const { onSelect } = many();
    const user = userEvent.setup();
    const header = screen.getByRole('option', { name: 'Header' });

    await user.click(header);
    expect(onSelect).toHaveBeenLastCalledWith('sec-header', { additive: false });

    await user.keyboard('{Shift>}');
    await user.click(header);
    await user.keyboard('{/Shift}');
    expect(onSelect).toHaveBeenLastCalledWith('sec-header', { additive: true });

    await user.keyboard('{Control>}');
    await user.click(header);
    await user.keyboard('{/Control}');
    expect(onSelect).toHaveBeenLastCalledWith('sec-header', { additive: true });
  });

  it('extends with shift and an arrow, the same as a list of files', async () => {
    const onKeyCommand = vi.fn();
    many({ onKeyCommand });
    screen.getByRole('listbox').focus();
    const user = userEvent.setup();

    await user.keyboard('{ArrowDown}');
    expect(onKeyCommand).toHaveBeenLastCalledWith('next', { additive: false });

    await user.keyboard('{Shift>}{ArrowDown}{/Shift}');
    expect(onKeyCommand).toHaveBeenLastCalledWith('next', { additive: true });
  });

  it('never extends on Escape — "add nothing" is not a thing anyone wants', async () => {
    const onKeyCommand = vi.fn();
    many({ onKeyCommand });
    screen.getByRole('listbox').focus();
    await userEvent.setup().keyboard('{Shift>}{Escape}{/Shift}');
    expect(onKeyCommand).toHaveBeenLastCalledWith('clear', { additive: false });
  });

  it('draws no handles and no size badge for a group', () => {
    const { container } = many();
    expect(container.querySelectorAll('.janso-canvas__handle')).toHaveLength(0);
    expect(screen.queryByTestId('selection-size')).not.toBeInTheDocument();
    // Still draggable: a group moves, it just does not scale.
    expect(screen.getByRole('option', { name: 'GST — rule 46' })).toHaveAttribute(
      'data-draggable',
    );
  });

  it('keeps the handles and the badge for a lone selection', () => {
    const { container } = many({ selectedIds: ['el-title'], selectedId: 'el-title' });
    expect(container.querySelectorAll('.janso-canvas__handle')).toHaveLength(8);
    expect(screen.getByTestId('selection-size')).toBeInTheDocument();
  });
});

describe('SelectionLayer — marquee', () => {
  /** jsdom measures nothing, so the layer's box has to be supplied. */
  function measured(node: HTMLElement, left = 50, top = 20): HTMLElement {
    node.setPointerCapture = vi.fn();
    node.hasPointerCapture = () => true;
    node.releasePointerCapture = vi.fn();
    node.getBoundingClientRect = () =>
      ({ left, top, right: left + 800, bottom: top + 1100, width: 800, height: 1100, x: left, y: top, toJSON: () => ({}) }) as DOMRect;
    return node;
  }

  function band(
    user: ReturnType<typeof userEvent.setup>,
    layer: HTMLElement,
    from: { x: number; y: number },
    to: { x: number; y: number },
    keys = '',
  ) {
    return user.pointer([
      ...(keys ? [{ keys: `{${keys}>}` } as never] : []),
      { target: layer, keys: '[MouseLeft>]', coords: { clientX: from.x, clientY: from.y } },
      { target: layer, coords: { clientX: to.x, clientY: to.y } },
      { target: layer, keys: '[/MouseLeft]' },
    ]);
  }

  it('reports the band it swept, in paper millimetres', async () => {
    const onMarquee = vi.fn();
    setup({ onMarquee });
    const layer = measured(screen.getByTestId('selection-layer'));
    const user = userEvent.setup();

    await band(user, layer, { x: 50 + PX_PER_MM * 10, y: 20 + PX_PER_MM * 5 }, {
      x: 50 + PX_PER_MM * 40,
      y: 20 + PX_PER_MM * 25,
    });
    expect(onMarquee).toHaveBeenCalledWith(
      { xMm: 10, yMm: 5, widthMm: 30, heightMm: 20 },
      { additive: false },
    );
  });

  it('normalises a band dragged up and to the left', async () => {
    const onMarquee = vi.fn();
    setup({ onMarquee });
    const layer = measured(screen.getByTestId('selection-layer'));
    await band(
      userEvent.setup(),
      layer,
      { x: 50 + PX_PER_MM * 40, y: 20 + PX_PER_MM * 25 },
      { x: 50 + PX_PER_MM * 10, y: 20 + PX_PER_MM * 5 },
    );
    expect(onMarquee).toHaveBeenCalledWith(
      { xMm: 10, yMm: 5, widthMm: 30, heightMm: 20 },
      expect.anything(),
    );
  });

  it('draws the band while the pointer is down and clears it on release', async () => {
    setup({ onMarquee: vi.fn() });
    const layer = measured(screen.getByTestId('selection-layer'));
    const user = userEvent.setup();

    await user.pointer([
      { target: layer, keys: '[MouseLeft>]', coords: { clientX: 50, clientY: 20 } },
      { target: layer, coords: { clientX: 50 + PX_PER_MM * 20, clientY: 20 + PX_PER_MM * 10 } },
    ]);
    expect(screen.getByTestId('marquee')).toHaveStyle({ width: '20mm', height: '10mm' });

    await user.pointer({ target: layer, keys: '[/MouseLeft]' });
    expect(screen.queryByTestId('marquee')).not.toBeInTheDocument();
  });

  it('reports nothing for a band smaller than a millimetre — that is a click', async () => {
    const onMarquee = vi.fn();
    setup({ onMarquee });
    const layer = measured(screen.getByTestId('selection-layer'));
    await band(userEvent.setup(), layer, { x: 60, y: 30 }, { x: 61, y: 30 });
    expect(onMarquee).not.toHaveBeenCalled();
  });

  it('adds to the selection when shift is held', async () => {
    const onMarquee = vi.fn();
    setup({ onMarquee });
    const layer = measured(screen.getByTestId('selection-layer'));
    const user = userEvent.setup();
    await user.keyboard('{Shift>}');
    await band(user, layer, { x: 50, y: 20 }, { x: 50 + PX_PER_MM * 30, y: 20 + PX_PER_MM * 30 });
    await user.keyboard('{/Shift}');
    expect(onMarquee).toHaveBeenCalledWith(expect.anything(), { additive: true });
  });

  it('does not start a band on a target — that pointerdown belongs to the drag', async () => {
    const onMarquee = vi.fn();
    const onTransform = vi.fn();
    setup({ selectedId: 'el-title', onMarquee, onTransform });
    measured(screen.getByTestId('selection-layer'));
    const target = screen.getByRole('option', { name: 'TAX INVOICE' });
    target.setPointerCapture = vi.fn();
    target.hasPointerCapture = () => true;
    target.releasePointerCapture = vi.fn();

    await userEvent.setup().pointer([
      { target, keys: '[MouseLeft>]', coords: { clientX: 400, clientY: 300 } },
      { target, coords: { clientX: 400 + PX_PER_MM * 10, clientY: 300 } },
      { target, keys: '[/MouseLeft]' },
    ]);
    expect(onMarquee).not.toHaveBeenCalled();
    expect(onTransform).toHaveBeenCalled();
  });

  it('offers no band at all when the caller has no use for one', async () => {
    setup({ selectedId: 'el-title' });
    const layer = measured(screen.getByTestId('selection-layer'));
    await band(userEvent.setup(), layer, { x: 50, y: 20 }, { x: 200, y: 200 });
    expect(screen.queryByTestId('marquee')).not.toBeInTheDocument();
    expect(screen.getByRole('listbox')).not.toHaveAttribute('aria-multiselectable');
  });
});

describe('Inspector anatomy', () => {
  it('titles a group as a heading under the editor’s h1', () => {
    render(
      <InspectorGroup title="Geometry" hint="Millimetres from the top-left.">
        <InspectorRow label="X">12 mm</InspectorRow>
      </InspectorGroup>,
    );
    expect(screen.getByRole('heading', { level: 2, name: 'Geometry' })).toBeInTheDocument();
    expect(screen.getByText('Millimetres from the top-left.')).toBeInTheDocument();
  });

  it('pairs a label with its value, and carries an optional hint', () => {
    render(
      <InspectorRow label="Width" hint="Of the printable area.">
        190 mm
      </InspectorRow>,
    );
    expect(screen.getByText('Width')).toHaveClass('janso-editor__row-label');
    expect(screen.getByText('190 mm')).toHaveClass('janso-editor__row-value');
    expect(screen.getByText('Of the printable area.')).toHaveClass('janso-editor__row-hint');
  });

  it('teaches the keyboard model in the empty state instead of apologising', () => {
    render(
      <InspectorEmpty>
        Nothing selected. Press <Kbd>↓</Kbd> to step through zones.
      </InspectorEmpty>,
    );
    expect(screen.getByText(/Nothing selected/)).toBeInTheDocument();
    // A key renders as a key, so it reads as one rather than as prose.
    expect(screen.getByText('↓').tagName).toBe('KBD');
  });
});
