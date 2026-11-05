import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { PX_PER_MM, PaperThumbnail } from '../src';

/**
 * The arithmetic is the whole component: a page shrunk to a box, still to scale.
 */
describe('PaperThumbnail', () => {
  const frameOf = (container: HTMLElement) =>
    container.querySelector('.janso-thumb') as HTMLElement;
  const sheetOf = (container: HTMLElement) =>
    container.querySelector('.janso-thumb__sheet') as HTMLElement;

  it('fits the longest edge to the box and keeps the page shape', () => {
    const { container } = render(
      <PaperThumbnail page={{ widthMm: 210, heightMm: 297 }} boxPx={200}>
        <p>page</p>
      </PaperThumbnail>,
    );
    const frame = frameOf(container);
    // 297mm is the longest edge, so it becomes 200px and the width follows the ratio.
    expect(Number.parseFloat(frame.style.height)).toBeCloseTo(200, 1);
    expect(Number.parseFloat(frame.style.width)).toBeCloseTo((200 * 210) / 297, 1);
  });

  it('scales a roll by its own longest edge, so it stays narrow', () => {
    const { container } = render(
      <PaperThumbnail page={{ widthMm: 80, heightMm: 200 }} boxPx={200}>
        <p>receipt</p>
      </PaperThumbnail>,
    );
    const frame = frameOf(container);
    expect(Number.parseFloat(frame.style.height)).toBeCloseTo(200, 1);
    expect(Number.parseFloat(frame.style.width)).toBeCloseTo(80, 1);
  });

  it('handles a landscape page, where the longest edge is the width', () => {
    const { container } = render(
      <PaperThumbnail page={{ widthMm: 297, heightMm: 210 }} boxPx={100}>
        <p>landscape</p>
      </PaperThumbnail>,
    );
    expect(Number.parseFloat(frameOf(container).style.width)).toBeCloseTo(100, 1);
  });

  it('draws the sheet at full millimetre size and scales it down', () => {
    const { container } = render(
      <PaperThumbnail page={{ widthMm: 210, heightMm: 297 }} boxPx={200}>
        <p>page</p>
      </PaperThumbnail>,
    );
    const sheet = sheetOf(container);
    // Full size in mm: the document inside is laid out at print geometry, then the whole
    // thing is transformed. Re-deriving it smaller would be a second renderer.
    expect(sheet.style.width).toBe('210mm');
    expect(sheet.style.height).toBe('297mm');
    const expected = 200 / (297 * PX_PER_MM);
    expect(sheet.style.transform).toBe(`scale(${expected})`);
  });

  it('renders its children, which are the real document', () => {
    const { getByText } = render(
      <PaperThumbnail page={{ widthMm: 210, heightMm: 297 }} boxPx={120}>
        <p>Nandini Trading Company</p>
      </PaperThumbnail>,
    );
    expect(getByText('Nandini Trading Company')).toBeInTheDocument();
  });

  it('is decorative, so a screen reader is not read a shrunken invoice', () => {
    const { container } = render(
      <PaperThumbnail page={{ widthMm: 210, heightMm: 297 }} boxPx={120}>
        <p>page</p>
      </PaperThumbnail>,
    );
    expect(frameOf(container)).toHaveAttribute('aria-hidden', 'true');
  });

  it('survives a degenerate page rather than dividing by zero', () => {
    const { container } = render(
      <PaperThumbnail page={{ widthMm: 0, heightMm: 0 }} boxPx={100}>
        <p>empty</p>
      </PaperThumbnail>,
    );
    expect(frameOf(container).style.width).toBe('0px');
    expect(sheetOf(container).style.transform).toContain('scale(');
  });
});
