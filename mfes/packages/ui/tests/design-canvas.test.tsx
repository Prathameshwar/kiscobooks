/**
 * The design canvas, its rulers and its zoom control.
 *
 * The load-bearing properties: the page is declared in millimetres so what is on screen
 * is what prints; zoom is one transform and never rewrites a child's geometry; the cursor
 * position is reported as a number the editor can put in text, not only drawn as a mark;
 * and the whole instrument is reachable without a pointer.
 */
import { createEvent, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { CanvasRuler } from '../src/components/CanvasRuler';
import { DesignCanvas } from '../src/components/DesignCanvas';
import { ZoomControl } from '../src/components/ZoomControl';
import { PX_PER_MM } from '../src/lib/paper';

function paperOf(): HTMLElement {
  return screen.getByTestId('design-canvas-paper');
}

describe('DesignCanvas', () => {
  it('declares the page in millimetres, the unit the layout and the printer share', () => {
    render(<DesignCanvas paper={{ size: 'A4' }} label="Tax invoice, A4 portrait" />);
    expect(paperOf()).toHaveStyle({ width: '210mm', height: '297mm' });
  });

  it('names the page for assistive technology', () => {
    render(<DesignCanvas paper={{ size: 'A4' }} label="Tax invoice, A4 portrait" />);
    expect(screen.getByRole('group', { name: 'Tax invoice, A4 portrait' })).toBeInTheDocument();
  });

  it('rotates with the orientation', () => {
    render(
      <DesignCanvas paper={{ size: 'A4', orientation: 'LANDSCAPE' }} label="Landscape invoice" />,
    );
    expect(paperOf()).toHaveStyle({ width: '297mm', height: '210mm' });
  });

  it('applies zoom once, as a scale on the page, leaving children in millimetres', () => {
    const { container } = render(
      <DesignCanvas paper={{ size: 'A4' }} zoom={1.5} label="A4">
        <div className="janso-doc__el" data-testid="child" style={{ left: '12mm', top: '20mm' }} />
      </DesignCanvas>,
    );
    const page = container.querySelector('.janso-canvas__page') as HTMLElement;
    expect(page.style.getPropertyValue('--janso-zoom')).toBe('1.5');
    // The child keeps its own geometry: zoom is not baked into any coordinate.
    expect(screen.getByTestId('child')).toHaveStyle({ left: '12mm', top: '20mm' });
  });

  it('draws the printable area from the margins', () => {
    render(
      <DesignCanvas
        paper={{ size: 'A4' }}
        margins={{ top: 12, right: 8, bottom: 15, left: 20 }}
        label="A4"
      />,
    );
    expect(screen.getByTestId('design-canvas-margins')).toHaveStyle({
      left: '20mm',
      top: '12mm',
      width: '182mm',
      height: '270mm',
    });
  });

  it('draws the layout grid at the requested step, and omits it when asked', () => {
    const { rerender } = render(
      <DesignCanvas paper={{ size: 'A4' }} gridStepMm={5} label="A4" />,
    );
    expect(screen.getByTestId('design-canvas-grid')).toHaveStyle({ backgroundSize: '5mm 5mm' });

    rerender(<DesignCanvas paper={{ size: 'A4' }} gridStepMm={0} label="A4" />);
    expect(screen.queryByTestId('design-canvas-grid')).not.toBeInTheDocument();
  });

  it('reports the pointer position in paper millimetres, and null once it leaves', async () => {
    const onCursorChange = vi.fn();
    render(
      <DesignCanvas paper={{ size: 'A4' }} zoom={1} onCursorChange={onCursorChange} label="A4" />,
    );
    const paper = paperOf();
    // jsdom has no layout, so the page box is stated explicitly.
    paper.getBoundingClientRect = () =>
      ({ left: 100, top: 50, width: 210 * PX_PER_MM, height: 297 * PX_PER_MM }) as DOMRect;

    const user = userEvent.setup();
    await user.pointer({
      target: paper,
      coords: { clientX: 100 + 20 * PX_PER_MM, clientY: 50 + 30 * PX_PER_MM },
    });
    const reported = onCursorChange.mock.calls.at(-1)?.[0];
    expect(reported.xMm).toBeCloseTo(20, 3);
    expect(reported.yMm).toBeCloseTo(30, 3);

    onCursorChange.mockClear();
    await user.pointer({ target: document.body });
    expect(onCursorChange).toHaveBeenCalledWith(null);
  });

  it('takes a drop of an accepted palette type at its point in paper millimetres', () => {
    const onDrop = vi.fn();
    render(<DesignCanvas paper={{ size: 'A4' }} zoom={2} dropTypes={['application/x-test']} onDrop={onDrop} label="A4" />);
    const paper = paperOf();
    paper.getBoundingClientRect = () =>
      ({ left: 100, top: 50, width: 420 * PX_PER_MM, height: 594 * PX_PER_MM }) as DOMRect;
    const dataTransfer = { types: ['application/x-test'], dropEffect: 'none', getData: () => 'x' };
    // jsdom has no DragEvent, so the pointer position is set on the event by hand.
    const drag = (create: typeof createEvent.drop) => {
      const event = create(paper, { dataTransfer });
      Object.defineProperties(event, {
        clientX: { value: 100 + 2 * 40 * PX_PER_MM },
        clientY: { value: 50 + 2 * 25 * PX_PER_MM },
      });
      return event;
    };
    // Accepting is what lets the browser drop at all: an unhandled dragover refuses it.
    expect(fireEvent(paper, drag(createEvent.dragOver))).toBe(false);
    fireEvent(paper, drag(createEvent.drop));
    const [point, data] = onDrop.mock.calls[0]!;
    expect(point.xMm).toBeCloseTo(40, 3);
    expect(point.yMm).toBeCloseTo(25, 3);
    expect(data.getData()).toBe('x');
  });

  it('refuses anything that is not its own palette type, such as a dragged file', () => {
    const onDrop = vi.fn();
    render(<DesignCanvas paper={{ size: 'A4' }} dropTypes={['application/x-test']} onDrop={onDrop} label="A4" />);
    const at = { clientX: 10, clientY: 10, dataTransfer: { types: ['Files'], getData: () => '' } };
    expect(fireEvent.dragOver(paperOf(), at)).toBe(true);
    fireEvent.drop(paperOf(), at);
    expect(onDrop).not.toHaveBeenCalled();
  });

  it('reports null for a pointer over the air beside the page, not a negative coordinate', async () => {
    const onCursorChange = vi.fn();
    render(<DesignCanvas paper={{ size: 'A4' }} onCursorChange={onCursorChange} label="A4" />);
    const paper = paperOf();
    paper.getBoundingClientRect = () =>
      ({ left: 100, top: 50, width: 210 * PX_PER_MM, height: 297 * PX_PER_MM }) as DOMRect;

    await userEvent.setup().pointer({ target: paper, coords: { clientX: 40, clientY: 10 } });
    expect(onCursorChange).toHaveBeenLastCalledWith(null);
  });

  it('shows rulers by default and drops them for a plain preview', () => {
    const { container, rerender } = render(<DesignCanvas paper={{ size: 'A4' }} label="A4" />);
    expect(container.querySelectorAll('.janso-canvas__ruler')).toHaveLength(2);
    expect(container.querySelector('.janso-canvas--plain')).toBeNull();

    rerender(<DesignCanvas paper={{ size: 'A4' }} rulers={false} label="A4" />);
    expect(container.querySelectorAll('.janso-canvas__ruler')).toHaveLength(0);
    expect(container.querySelector('.janso-canvas--plain')).not.toBeNull();
  });

  it('carries a chip about the page, counter-scaled so it stays readable at any zoom', () => {
    const { container } = render(
      <DesignCanvas paper={{ size: 'A4' }} zoom={0.5} chip="A4 · Original" label="A4" />,
    );
    const chip = container.querySelector('.janso-canvas__chip') as HTMLElement;
    expect(chip).toHaveTextContent('A4 · Original');
  });
});

describe('CanvasRuler', () => {
  it('is decoration: the position it shows is also text in the status bar', () => {
    const { container } = render(<CanvasRuler axis="horizontal" lengthMm={50} zoom={1} />);
    expect(container.firstElementChild).toHaveAttribute('aria-hidden', 'true');
  });

  it('draws a tick every 5mm and a numeral every 10mm', () => {
    const { container } = render(<CanvasRuler axis="horizontal" lengthMm={40} zoom={1} />);
    expect(container.querySelectorAll('.janso-canvas__tick')).toHaveLength(9);
    expect(container.querySelectorAll('.janso-canvas__numeral')).toHaveLength(5);
  });

  it('places the cursor marker at the zoomed pixel offset of its millimetre position', () => {
    render(<CanvasRuler axis="horizontal" lengthMm={100} zoom={2} cursorMm={10} offsetPx={8} />);
    const marker = screen.getByTestId('ruler-marker-horizontal');
    expect(marker).toHaveStyle({ left: `${8 + 10 * 2 * PX_PER_MM}px` });
  });

  it('shows no marker when the pointer is off the page', () => {
    render(<CanvasRuler axis="vertical" lengthMm={100} zoom={1} cursorMm={null} />);
    expect(screen.queryByTestId('ruler-marker-vertical')).not.toBeInTheDocument();
  });
});

describe('ZoomControl', () => {
  it('steps through the presets and announces the value', async () => {
    const onChange = vi.fn();
    render(<ZoomControl zoom={1} onChange={onChange} />);
    const value = screen.getByText('100%');
    expect(value).toHaveAttribute('aria-live', 'polite');

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Zoom in' }));
    expect(onChange).toHaveBeenLastCalledWith(1.25);
    await user.click(screen.getByRole('button', { name: 'Zoom out' }));
    expect(onChange).toHaveBeenLastCalledWith(0.75);
  });

  it('disables the step that would leave the range', () => {
    const { rerender } = render(<ZoomControl zoom={0.25} onChange={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Zoom out' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Zoom in' })).toBeEnabled();

    rerender(<ZoomControl zoom={2} onChange={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Zoom in' })).toBeDisabled();
  });

  it('offers Fit only when the viewport has been measured', async () => {
    const onFit = vi.fn();
    const { rerender } = render(<ZoomControl zoom={1} onChange={vi.fn()} />);
    expect(screen.queryByRole('button', { name: 'Fit' })).not.toBeInTheDocument();

    rerender(<ZoomControl zoom={1} onChange={vi.fn()} onFit={onFit} />);
    await userEvent.setup().click(screen.getByRole('button', { name: 'Fit' }));
    expect(onFit).toHaveBeenCalledOnce();
  });

  it('is a named group, so a screen reader hears what the two buttons control', () => {
    render(<ZoomControl zoom={1} onChange={vi.fn()} />);
    expect(screen.getByRole('group', { name: 'Canvas zoom' })).toBeInTheDocument();
  });
});

describe('continuous stock', () => {
  it('draws a roll as long as its content, while the paper stays the stock it is', () => {
    const { getByTestId } = render(
      <DesignCanvas
        paper={{ size: 'THERMAL_80MM' }}
        drawnHeightMm={317}
        label="Receipt, 80mm roll"
      />,
    );
    // 80mm wide — the stock's fixed width — and 317mm of it in front of you.
    expect(getByTestId('design-canvas-paper')).toHaveStyle({
      width: '80mm',
      height: '317mm',
    });
  });

  it('uses the nominal length when no override is given', () => {
    const { getByTestId } = render(
      <DesignCanvas paper={{ size: 'THERMAL_80MM' }} label="Receipt, 80mm roll" />,
    );
    expect(getByTestId('design-canvas-paper')).toHaveStyle({ height: '200mm' });
  });
});
