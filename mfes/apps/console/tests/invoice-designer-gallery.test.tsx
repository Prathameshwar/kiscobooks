/**
 * Phase 7: the gallery you arrive at, and the version history you leave behind.
 *
 * The distinction under test throughout: a template's *design* is what the editor shows,
 * and what it **prints** is a published version. Nothing is live because it is on screen.
 */
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent, { PointerEventsCheckLevel } from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { DesignerShell } from '../app/(editor)/invoice-designer/DesignerShell';
import { TemplateGallery } from '../app/(editor)/invoice-designer/TemplateGallery';
import type { DesignTemplate } from '../app/(editor)/invoice-designer/layout-model';
import {
  canPublish,
  nextVersionNumber,
  publicationOf,
  publish,
  snapshotOf,
  versionDate,
} from '../app/(editor)/invoice-designer/publication';
import { SAMPLE_TEMPLATES } from '../app/(editor)/invoice-designer/sample-templates';

const GST = SAMPLE_TEMPLATES.find((template) => template.id === 'tpl-gst-a4')!;
// Keep pointer eligibility checks, but cache them per target. Rechecking the
// large editor's ancestor styles on every typed character dominates jsdom time.
const user = () => userEvent.setup({ pointerEventsCheck: PointerEventsCheckLevel.EachTarget });

async function summary(session: ReturnType<typeof user>, text: string) {
  await session.click(screen.getByLabelText('What changed'));
  // Paste exercises the same editable field and validation in one input event;
  // repeated character input needlessly rerenders the entire preview in jsdom.
  await session.paste(text);
}

function renderShell(initialTemplateId = 'tpl-gst-a4') {
  return render(
    <DesignerShell templates={SAMPLE_TEMPLATES} initialTemplateId={initialTemplateId} />,
  );
}

const card = (name: string | RegExp) =>
  screen.getByRole('heading', { name, level: 2 }).closest('article') as HTMLElement;

describe('the template gallery', () => {
  it('shows a card per template, with its code and what it is for', () => {
    render(<TemplateGallery templates={SAMPLE_TEMPLATES} />);
    expect(screen.getAllByRole('article')).toHaveLength(4);

    const gst = card(/GST tax invoice/);
    expect(gst).toHaveTextContent('gst-tax-invoice-a4');
    expect(gst).toHaveTextContent('Rule 46 invoice');
  });

  it('says whether a template prints at all', () => {
    render(<TemplateGallery templates={SAMPLE_TEMPLATES} />);
    // Published: the live version and the date it went live.
    expect(card(/GST tax invoice/)).toHaveTextContent('Version 4 live since 18 Oct 2026');
    expect(within(card(/GST tax invoice/)).getByText('Live')).toBeInTheDocument();

    // Never published: a draft prints nothing, which is the thing to know before opening it.
    expect(card(/Compact invoice/)).toHaveTextContent('Never published');
    expect(within(card(/Compact invoice/)).getByText('Draft')).toBeInTheDocument();
  });

  it('marks a shipped template, which cannot be edited', () => {
    render(<TemplateGallery templates={SAMPLE_TEMPLATES} />);
    expect(within(card(/Retail receipt/)).getByText('Shipped')).toBeInTheDocument();
    // The action says what it does: you may look at a shipped design, not change it.
    expect(within(card(/Retail receipt/)).getByRole('link')).toHaveTextContent('Inspect');
    expect(within(card(/GST tax invoice/)).getByRole('link')).toHaveTextContent('Design');
  });

  it('links each card to its editor route', () => {
    render(<TemplateGallery templates={SAMPLE_TEMPLATES} />);
    expect(within(card(/Delivery challan/)).getByRole('link')).toHaveAttribute(
      'href',
      '/invoice-designer/tpl-challan-a4',
    );
  });

  it('draws the real document, scaled, and keeps it out of the accessibility tree', () => {
    const { container } = render(<TemplateGallery templates={SAMPLE_TEMPLATES} />);
    // "The one with the logo on the left" is how a template is found, so the card has to
    // be the invoice rather than a page icon.
    const thumb = within(card(/GST tax invoice/)).getByText('Nandini Trading Company');
    expect(thumb).toBeInTheDocument();

    // Decorative: a scaled-down 7pt address line is a shape, not something to read out.
    const frames = container.querySelectorAll('.janso-thumb');
    expect(frames).toHaveLength(4);
    for (const frame of frames) expect(frame).toHaveAttribute('aria-hidden', 'true');
  });

  it('scales by the longest edge, so a roll stays roll-shaped', () => {
    const { container } = render(<TemplateGallery templates={SAMPLE_TEMPLATES} />);
    const frames = [...container.querySelectorAll('.janso-thumb')] as HTMLElement[];
    const widths = frames.map((frame) => Number.parseFloat(frame.style.width));
    const heights = frames.map((frame) => Number.parseFloat(frame.style.height));

    // Every thumbnail fits the same 190px box on its longest edge.
    for (const [index, height] of heights.entries()) {
      expect(Math.max(widths[index]!, height)).toBeCloseTo(190, 0);
    }
    // Shape survives the shrink: the 80mm roll (80 × 200) is a far narrower rectangle
     // than A4 (210 × 297). A thumbnail stretched to fill a square box would be a lie
     // about the stock it prints on.
    const ratio = (frame: HTMLElement) =>
      Number.parseFloat(frame.style.width) / Number.parseFloat(frame.style.height);
    expect(ratio(frames[2]!)).toBeCloseTo(80 / 200, 2);
    expect(ratio(frames[0]!)).toBeCloseTo(210 / 297, 2);
    expect(Number.parseFloat(frames[2]!.style.width)).toBeLessThan(
      Number.parseFloat(frames[0]!.style.width),
    );
  });

  it('shows a broken template as broken, before anyone opens it', () => {
    const broken: DesignTemplate = {
      ...GST,
      id: 'tpl-broken',
      name: 'Broken invoice',
      // 14mm left on a 190mm-wide zone in a 190mm printable area: 4mm off the paper.
      layout: {
        ...GST.layout,
        sections: GST.layout.sections.map((section) =>
          section.id === 'sec-footer' ? { ...section, xMm: 14 } : section,
        ),
      },
    };
    render(<TemplateGallery templates={[broken]} />);
    expect(within(card(/Broken invoice/)).getByText('1 error')).toBeInTheDocument();
  });

  it('has something to say when there is nothing to show', () => {
    render(<TemplateGallery templates={[]} />);
    // The first screen a real tenant sees. "Nothing here" with no next step is the worst
    // screen in any product.
    expect(screen.getByText(/No templates yet/)).toBeInTheDocument();
    expect(screen.getByText(/can be copied to start one/)).toBeInTheDocument();
  });
});

describe('the publication model', () => {
  it('orders versions newest first, whatever order they arrived in', () => {
    expect(publicationOf(GST).versions.map((version) => version.versionNumber)).toEqual([
      4, 3, 2, 1,
    ]);
  });

  it('publishes one past the highest number, never a gap and never a reuse', () => {
    const before = publicationOf(GST);
    expect(nextVersionNumber(before)).toBe(5);

    const after = publish(before, GST, GST.layout, 'Moved the QR code', new Date('2026-10-26T09:00:00Z'));
    expect(after.versions[0]).toMatchObject({
      id: 'tpl-gst-a4-v5',
      versionNumber: 5,
      changeSummary: 'Moved the QR code',
      publishedAt: '2026-10-26T09:00:00.000Z',
    });
    expect(after.liveVersionId).toBe('tpl-gst-a4-v5');
    expect(after.status).toBe('PUBLISHED');
    expect(nextVersionNumber(after)).toBe(6);
  });

  it('keeps the published layout, and keeps it unchanged by later editing', () => {
    const published = publish(publicationOf(GST), GST, GST.layout, 'A note', new Date());
    // The snapshot is the layout object. Every edit function returns a new tree, so a
    // published version cannot be altered by editing — the immutability the service's
    // contract needs holds here for free because nothing mutates.
    expect(snapshotOf(published, 'tpl-gst-a4-v5')).toBe(GST.layout);
    expect(snapshotOf(published, 'ver-gst-4')).toBeNull();
  });

  it('refuses to publish a shipped template, errors, or nothing', () => {
    expect(canPublish({ isSystem: true }, [], true)).toMatchObject({
      ok: false,
      reason: expect.stringContaining('read-only'),
    });
    expect(canPublish({ isSystem: false }, [], false)).toMatchObject({
      ok: false,
      reason: expect.stringContaining('Nothing has changed'),
    });

    const error = {
      code: 'zone-outside-printable',
      severity: 'error',
      targetId: 'sec-footer',
      message: 'clipped',
    } as const;
    expect(canPublish({ isSystem: false }, [error], true)).toMatchObject({
      ok: false,
      reason: expect.stringContaining('prints wrong on every copy'),
    });

    const warning = { ...error, severity: 'warning' } as const;
    // A warning may be deliberate, so it is stated rather than blocking.
    expect(canPublish({ isSystem: false }, [warning], true)).toEqual({ ok: true });
  });

  it('formats a date without asking the client what it prefers', () => {
    expect(versionDate('2026-10-18T09:30:00Z')).toBe('18 Oct 2026');
    expect(versionDate('not a date')).toBe('not a date');
  });
});

describe('versions in the editor', () => {
  it('lists the history with the live version marked', () => {
    renderShell();
    const list = screen.getByRole('list', { name: 'Versions' });
    expect(within(list).getAllByRole('listitem')).toHaveLength(4);
    expect(list).toHaveTextContent('Added e-Way bill and IRN QR');
    expect(list).toHaveTextContent('published 18 Oct 2026');
    expect(within(list).getByText('Live')).toBeInTheDocument();
  });

  it('offers no restore for a version the service holds, and says why', () => {
    renderShell();
    expect(screen.queryByRole('button', { name: /Restore version/ })).not.toBeInTheDocument();
    // A greyed row that explains itself beats a button that quietly does nothing.
    expect(screen.getByRole('list', { name: 'Versions' })).toHaveTextContent(
      'Layout held by the design service',
    );
  });

  it('will not publish an unchanged template, and says so', () => {
    renderShell();
    expect(screen.getByRole('button', { name: 'Publish version 5' })).toBeDisabled();
    expect(screen.getByTestId('publish-state')).toHaveTextContent('Nothing has changed');
  });

  it('will not publish a shipped template', () => {
    renderShell('tpl-thermal-80');
    expect(screen.getByRole('button', { name: 'Publish version 3' })).toBeDisabled();
    expect(screen.getByTestId('publish-state')).toHaveTextContent('read-only');
  });

  it('will not publish a layout that prints wrong', async () => {
    const session = user();
    renderShell();
    const margin = screen.getByLabelText('right margin');
    await session.clear(margin);
    await session.type(margin, '20{Enter}');

    expect(screen.getByTestId('publish-state')).toHaveTextContent('errors first');
    expect(screen.getByRole('button', { name: /^Publish version/ })).toBeDisabled();
  });

  it('counts what publishing would carry', async () => {
    const session = user();
    renderShell();
    const grid = screen.getByLabelText('Grid step');
    await session.clear(grid);
    await session.type(grid, '20{Enter}');

    expect(screen.getByTestId('publish-state')).toHaveTextContent('1 change will go live');
    expect(screen.getByRole('button', { name: 'Publish version 5' })).toBeEnabled();
  });
});

describe('publishing', () => {
  /** Make one real edit, so publishing has something to carry. */
  async function withAnEdit(session: ReturnType<typeof userEvent.setup>) {
    const grid = screen.getByLabelText('Grid step');
    await session.clear(grid);
    await session.type(grid, '20{Enter}');
  }

  it('asks before it does anything, and says what it will do', async () => {
    const session = user();
    renderShell();
    await withAnEdit(session);
    await session.click(screen.getByRole('button', { name: 'Publish version 5' }));

    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveTextContent('Publish version 5?');
    expect(dialog).toHaveTextContent('becomes the live version immediately');
    expect(dialog).toHaveTextContent('Earlier versions are left as they are');
  });

  it('insists on a summary, keeping the dialog open', async () => {
    const session = user();
    renderShell();
    await withAnEdit(session);
    await session.click(screen.getByRole('button', { name: 'Publish version 5' }));
    await session.click(screen.getByRole('button', { name: 'Publish' }));

    // Still open, with the reason: a history of four identical entries is not a history.
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByRole('dialog')).toHaveTextContent('Say what changed');
    expect(screen.getByRole('list', { name: 'Versions' })).not.toHaveTextContent('Version 5');
  });

  it('publishes, makes it live, and says so in the title bar', async () => {
    const session = user();
    renderShell();
    await withAnEdit(session);
    await session.click(screen.getByRole('button', { name: 'Publish version 5' }));
    await summary(session, 'Coarser grid');
    await session.click(screen.getByRole('button', { name: 'Publish' }));

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    const list = screen.getByRole('list', { name: 'Versions' });
    expect(within(list).getAllByRole('listitem')).toHaveLength(5);
    expect(list).toHaveTextContent('Coarser grid');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Live · version 5');
  });

  it('is unpublishable again straight afterwards, and publishable after one more edit', async () => {
    const session = user();
    renderShell();
    await withAnEdit(session);
    await session.click(screen.getByRole('button', { name: 'Publish version 5' }));
    await summary(session, 'Coarser grid');
    await session.click(screen.getByRole('button', { name: 'Publish' }));

    expect(screen.getByTestId('publish-state')).toHaveTextContent('Nothing has changed');
    expect(screen.getByRole('button', { name: 'Publish version 6' })).toBeDisabled();

    const grid = screen.getByLabelText('Grid step');
    await session.clear(grid);
    await session.type(grid, '10{Enter}');
    expect(screen.getByRole('button', { name: 'Publish version 6' })).toBeEnabled();
  });

  it('knows an undo back to the published layout is not a change', async () => {
    const session = user();
    renderShell();
    await withAnEdit(session);
    await session.click(screen.getByRole('button', { name: 'Publish version 5' }));
    await summary(session, 'Coarser grid');
    await session.click(screen.getByRole('button', { name: 'Publish' }));

    // Edit, then take it back. Counting edits would leave this saying "1 change"; the
    // comparison is against the published layout itself, so it says the truth.
    const grid = screen.getByLabelText('Grid step');
    await session.clear(grid);
    await session.type(grid, '10{Enter}');
    expect(screen.getByRole('button', { name: 'Publish version 6' })).toBeEnabled();

    await session.click(screen.getByRole('button', { name: 'Undo' }));
    expect(screen.getByTestId('publish-state')).toHaveTextContent('Nothing has changed');
  });

  it('lists the warnings it is publishing with, at the last moment anyone reads them', async () => {
    const session = user();
    renderShell();
    // Overlap the meta zone into the header: a warning, not an error, so publishing is
    // still allowed and the dialog has to say what is being accepted.
    const zone = screen.getByRole('treeitem', { name: /Document details/ });
    await session.click(zone);
    const top = screen.getByLabelText('Y position');
    await session.clear(top);
    await session.type(top, '30{Enter}');

    await session.click(screen.getByRole('button', { name: 'Publish version 5' }));
    const warnings = screen.getByTestId('publish-warnings');
    expect(warnings).toHaveTextContent('Publishing with 1 warning');
    expect(warnings).toHaveTextContent('overlaps');
  });

  it('restores a version it published, as one undoable edit', async () => {
    const session = user();
    renderShell();
    await withAnEdit(session);
    await session.click(screen.getByRole('button', { name: 'Publish version 5' }));
    await summary(session, 'Coarser grid');
    await session.click(screen.getByRole('button', { name: 'Publish' }));

    // Move away from the published layout, then come back to it by version.
    const grid = screen.getByLabelText('Grid step');
    await session.clear(grid);
    await session.type(grid, '2{Enter}');
    expect(screen.getByLabelText('Grid step')).toHaveValue('2');

    await session.click(screen.getByRole('button', { name: 'Publish version 6' }));
    await summary(session, 'Finer grid');
    await session.click(screen.getByRole('button', { name: 'Publish' }));

    await session.click(
      screen.getByRole('button', { name: 'Restore version 5 into the editor' }),
    );
    /* `waitFor` on the last two assertions, not because the behaviour is asynchronous —
     * every edit here is a synchronous state update — but because this is the longest
     * interaction chain in the suite (two publish dialogs and four typed fields) and on a
     * loaded machine `userEvent` can still be flushing when the assertion runs. It failed
     * exactly once, in a 201-file run, and passed isolated every time. A test that needs
     * an idle machine is a test that fails in CI. */
    await waitFor(() => expect(screen.getByLabelText('Grid step')).toHaveValue('20'));

    await session.click(screen.getByRole('button', { name: 'Undo' }));
    await waitFor(() => expect(screen.getByLabelText('Grid step')).toHaveValue('2'));
  // Two publications, restore and undo are a deliberately longer interaction
  // scenario. Its assertions stay bounded; allow loaded CI to finish the chain.
  }, 10000);
});
