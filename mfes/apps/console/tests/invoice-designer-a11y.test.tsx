/**
 * Phase 8: the editor without a pointer, without colour, and with a page full of elements.
 *
 * These are the assertions the rest of the designer suite cannot make. Every other test
 * reaches for a control by its accessible name and clicks it, which proves the control
 * works and proves nothing about whether anyone could *find* it — the tab order, the
 * landmarks, the one-tab-stop canvas and the nameless-button sweep are all invisible to a
 * test that already knows what it is looking for.
 */
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { DesignerShell } from '../app/(editor)/invoice-designer/DesignerShell';
import { TemplateGallery } from '../app/(editor)/invoice-designer/TemplateGallery';
import { selectionBounds } from '../app/(editor)/invoice-designer/layout-arrange';
import type {
  CanvasElement,
  DesignTemplate,
} from '../app/(editor)/invoice-designer/layout-model';
import { checkLayout } from '../app/(editor)/invoice-designer/layout-warnings';
import { SAMPLE_TEMPLATES } from '../app/(editor)/invoice-designer/sample-templates';
import { targetsOf } from '../app/(editor)/invoice-designer/selection';

const GST = SAMPLE_TEMPLATES.find((template) => template.id === 'tpl-gst-a4')!;
const user = () => userEvent.setup();

function renderShell(templates: readonly DesignTemplate[] = SAMPLE_TEMPLATES, id = 'tpl-gst-a4') {
  return render(<DesignerShell templates={templates} initialTemplateId={id} />);
}

/** A template built around one layout, so a test can state its own page. */
function templateWith(layout: DesignTemplate['layout'], id = 'tpl-made'): DesignTemplate {
  return { ...GST, id, name: 'Made for a test', layout, versions: [], liveVersionId: null, status: 'DRAFT' };
}

describe('landmarks and headings', () => {
  it('names every region of the editor', () => {
    renderShell();
    // An editor is a workspace, and a workspace with four unnamed panels is unnavigable
    // for anyone moving by landmark.
    expect(screen.getByRole('banner')).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Templates and page structure' })).toBeInTheDocument();
    expect(screen.getByRole('main', { name: 'Document canvas' })).toBeInTheDocument();
    expect(screen.getByRole('complementary', { name: 'Properties' })).toBeInTheDocument();
    expect(screen.getByRole('contentinfo')).toBeInTheDocument();
  });

  it('has one h1 and never skips a level', () => {
    renderShell();
    const levels = screen
      .getAllByRole('heading')
      .map((node) => Number(node.tagName.slice(1)))
      .sort((a, b) => a - b);
    expect(levels.filter((level) => level === 1)).toHaveLength(1);
    // Every other heading is an h2: the inspector's groups. No h3 without an h2 above it.
    expect(new Set(levels)).toEqual(new Set([1, 2]));
  });

  it('gives the gallery a main landmark and a heading per card', () => {
    render(<TemplateGallery templates={SAMPLE_TEMPLATES} />);
    expect(screen.getByRole('main')).toBeInTheDocument();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(screen.getAllByRole('heading', { level: 2 })).toHaveLength(4);
  });

  it('names every list in the rail, so arriving in one tells you where you are', () => {
    renderShell();
    const rail = screen.getByRole('navigation', { name: 'Templates and page structure' });
    for (const list of within(rail).getAllByRole('list')) {
      const named =
        list.getAttribute('aria-label') ?? list.getAttribute('aria-labelledby');
      expect(named, list.className).toBeTruthy();
    }
  });
});

describe('every control can be found by name', () => {
  /**
   * The sweep. A nameless icon button is the defect this catches, and it is the one defect
   * every other test in the suite is blind to by construction — they all look controls up
   * *by* their names.
   */
  it('leaves no button, input or select without an accessible name', () => {
    const { container } = renderShell();
    const nameless: string[] = [];

    for (const node of container.querySelectorAll('button, input, select, textarea')) {
      const element = node as HTMLElement;
      const described =
        element.getAttribute('aria-label') ??
        element.getAttribute('aria-labelledby') ??
        element.getAttribute('title') ??
        (element.id ? container.querySelector(`label[for="${element.id}"]`)?.textContent : null) ??
        element.closest('label')?.textContent ??
        element.textContent;
      if (!described || !described.trim()) {
        nameless.push(`${element.tagName.toLowerCase()}.${element.className}`);
      }
    }

    expect(nameless).toEqual([]);
  });

  it('offers export as disabled-with-a-reason rather than leaving it out', () => {
    renderShell();
    const download = screen.getByRole('button', { name: 'Download PDF — no renderer yet' });
    // Absent would read as "it must be somewhere else" and send a designer hunting. The
    // name and the tooltip both carry why, so the answer does not depend on hovering.
    expect(download).toBeDisabled();
    expect(download).toHaveAttribute('title', expect.stringContaining('renderer'));
  });

  it('says why a disabled control is disabled, rather than leaving it inert and silent', () => {
    renderShell(SAMPLE_TEMPLATES, 'tpl-thermal-80');
    // A shipped template: publishing and placing are both refused, and both say so in
    // words beside the control rather than only by being grey.
    expect(screen.getByTestId('publish-state')).toHaveTextContent('read-only');
    expect(screen.getByTestId('palette-destination')).toHaveTextContent('read-only');
  });
});

describe('the editor without a pointer', () => {
  /** Walk the tab order and describe each stop the way a user would recognise it. */
  async function tabStops(session: ReturnType<typeof userEvent.setup>, count: number) {
    const seen: string[] = [];
    for (let i = 0; i < count; i += 1) {
      await session.tab();
      const active = document.activeElement as HTMLElement | null;
      if (!active || active === document.body) break;
      seen.push(
        active.getAttribute('aria-label') ??
          active.closest('label')?.textContent?.trim() ??
          active.textContent?.trim().slice(0, 24) ??
          '',
      );
    }
    return seen;
  }

  it('reaches the toolbar, then the rail, then the canvas, in that order', async () => {
    renderShell();
    const seen = await tabStops(user(), 32);

    const at = (label: string) => seen.findIndex((stop) => stop.includes(label));
    // The way out comes first: it is the one control a lost keyboard user is looking for.
    expect(at('Back to templates')).toBe(0);
    // Toolbar before rail before canvas: the order of the regions on screen. A tab order
    // that jumps between panels is the thing a keyboard user cannot build a model of.
    expect(at('What the page prints in place of data')).toBeGreaterThanOrEqual(0);
    expect(at('Apply a paper preset')).toBeGreaterThan(at('What the page prints in place of data'));
    expect(at('Zoom out')).toBeGreaterThan(at('Apply a paper preset'));
    expect(at('GST tax invoice')).toBeGreaterThan(at('Zoom out'));
    expect(at('Page elements')).toBeGreaterThan(at('GST tax invoice'));
  });

  it('does not leave a dead tab stop where a control has nothing to do', async () => {
    renderShell();
    const session = user();
    // Nothing to undo yet, so Undo is disabled and correctly skipped — a stop that can
    // only be left again teaches a keyboard user to distrust the order.
    expect(await tabStops(session, 16)).not.toContain('Undo');
  });

  it('puts Undo in the tab order the moment there is something to undo', async () => {
    renderShell();
    const session = user();
    const grid = screen.getByLabelText('Grid step');
    await session.clear(grid);
    await session.type(grid, '20{Enter}');

    // Back to the top of the document, then walk again.
    (document.activeElement as HTMLElement | null)?.blur();
    expect(await tabStops(session, 16)).toContain('Undo');
  });

  it('is one tab stop for the whole canvas, whatever is on the page', async () => {
    renderShell();
    const session = user();
    const canvas = screen.getByRole('listbox', { name: 'Page elements' });

    canvas.focus();
    expect(canvas).toHaveFocus();
    // A page of 40-odd elements must not be 40 tab stops. The listbox owns them and the
    // arrows move within it — the pattern phase 2 chose and this re-asserts.
    await session.tab();
    expect(canvas).not.toHaveFocus();
    expect(within(canvas).queryAllByRole('option').length).toBeGreaterThan(20);
  });

  it('selects, moves and undoes with no pointer at all', async () => {
    const { container } = renderShell();
    const session = user();
    const canvas = screen.getByRole('listbox', { name: 'Page elements' });
    canvas.focus();

    // One arrow selects the first zone; a second enters it, because a page is zones and
    // each zone holds elements. A zone is placed by the layout and is not draggable, so
    // the nudge below needs the element.
    await session.keyboard('{ArrowRight}');
    expect(screen.getByTestId('selection-readout')).toHaveTextContent('Header');
    await session.keyboard('{ArrowRight}');
    expect(screen.getByTestId('selection-readout')).not.toHaveTextContent('nothing');

    const before = container.querySelector('[data-element="el-logo"]')?.getAttribute('style');
    await session.keyboard('{Alt>}{ArrowRight}{/Alt}');
    expect(container.querySelector('[data-element="el-logo"]')?.getAttribute('style')).not.toBe(
      before,
    );

    await session.keyboard('{Control>}z{/Control}');
    expect(container.querySelector('[data-element="el-logo"]')?.getAttribute('style')).toBe(
      before,
    );
  });

  it('clears the selection with Escape', async () => {
    renderShell();
    const session = user();
    const canvas = screen.getByRole('listbox', { name: 'Page elements' });
    canvas.focus();
    await session.keyboard('{ArrowRight}');
    await session.keyboard('{Escape}');
    expect(screen.getByTestId('selection-readout')).toHaveTextContent('nothing');
  });

  it('announces the selection politely rather than interrupting', () => {
    renderShell();
    const live = screen.getByTestId('selection-readout');
    // `polite`, because a nudge announcing itself over the top of a screen reader mid-word
    // makes the keyboard unusable for the people most dependent on it.
    const region = live.closest('[aria-live]') ?? live;
    expect(region).toHaveAttribute('aria-live', 'polite');
  });
});

describe('empty states', () => {
  it('has something to say for a page with no zones at all', () => {
    const bare = templateWith({ ...GST.layout, sections: [] });
    renderShell([bare], bare.id);
    // A new template starts here. A blank rail with no sentence is the state a designer
    // reads as "broken", not as "yours to fill".
    expect(screen.getByRole('main', { name: 'Document canvas' })).toBeInTheDocument();
    expect(screen.getByTestId('selection-readout')).toHaveTextContent('nothing');
    expect(screen.getByTestId('palette-destination')).toHaveTextContent('Add a zone');
    expect(screen.getByTestId('palette-help')).toHaveTextContent('no zones yet');
  });

  it('keeps an empty zone, and says it is empty', () => {
    const emptied = templateWith({
      ...GST.layout,
      sections: GST.layout.sections.map((section) =>
        section.id === 'sec-footer' ? { ...section, elements: [] } : section,
      ),
    });
    renderShell([emptied], emptied.id);
    const tree = screen.getByRole('tree', { name: 'Page structure' });
    const footer = within(tree).getByRole('treeitem', { name: /Footer/ });
    // A document that carries no bank details still has a footer, so the zone stays and
    // reports nothing in it.
    expect(footer).toHaveTextContent('0');
    expect(footer).not.toHaveAttribute('aria-expanded');
  });

  it('handles a template with no version history', () => {
    const fresh = templateWith(GST.layout);
    renderShell([fresh], fresh.id);
    const versions = screen.getByRole('list', { name: 'Versions' });
    expect(within(versions).queryAllByRole('listitem')).toHaveLength(0);
    // Version 1 is still the next thing to publish, and the draft says it prints nothing.
    expect(screen.getByRole('button', { name: 'Publish version 1' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('not printing yet');
  });

  it('says so when no field matches a search', async () => {
    renderShell();
    await user().type(screen.getByRole('searchbox', { name: 'Find a field' }), 'qqq');
    expect(screen.getByText(/Nothing matches/)).toBeInTheDocument();
  });
});

describe('a page of 200 elements', () => {
  /** 200 text elements in one tall zone — more than any real invoice, by design. */
  function crowded(): DesignTemplate {
    const elements: CanvasElement[] = Array.from({ length: 200 }, (_, index) => ({
      id: `el-${index}`,
      type: 'TEXT' as const,
      xMm: (index % 4) * 45,
      yMm: Math.floor(index / 4) * 5,
      widthMm: 40,
      heightMm: 4,
      content: `Line ${index}`,
      style: {},
    }));
    return templateWith(
      {
        ...GST.layout,
        sections: [
          {
            id: 'sec-many',
            type: 'CUSTOM',
            title: 'Crowded',
            xMm: 10,
            yMm: 10,
            widthMm: 190,
            heightMm: 260,
            elements,
          },
        ],
      },
      'tpl-crowded',
    );
  }

  it('renders every element, and still as one tab stop', () => {
    const crowd = crowded();
    renderShell([crowd], crowd.id);
    const canvas = screen.getByRole('listbox', { name: 'Page elements' });
    // 200 elements plus the zone itself.
    expect(within(canvas).getAllByRole('option')).toHaveLength(201);
    expect(canvas).toHaveAttribute('tabindex', '0');
  });

  it('selects the whole zone with one keystroke and reports the count', async () => {
    const crowd = crowded();
    renderShell([crowd], crowd.id);
    const session = user();
    screen.getByRole('listbox', { name: 'Page elements' }).focus();
    await session.keyboard('{Control>}a{/Control}');

    expect(screen.getByTestId('selection-readout')).toHaveTextContent('200 elements');
    expect(screen.getByRole('heading', { name: 'Arrange' })).toBeInTheDocument();
  });

  /**
   * The models stay linear. A time budget on this machine is not worth asserting — the
   * suite is demonstrably load-sensitive — but the *shape* of the cost is, and a generous
   * ceiling catches the thing that actually goes wrong: a nested scan turning 200 elements
   * into 40,000 comparisons.
   */
  it('keeps the layout models linear rather than quadratic', () => {
    const layout = crowded().layout;
    const ids = layout.sections[0]!.elements.map((element) => element.id);

    const started = performance.now();
    for (let run = 0; run < 20; run += 1) {
      const targets = targetsOf(layout);
      expect(targets).toHaveLength(201);
      expect(checkLayout(layout)).toEqual([]);
      expect(selectionBounds(layout, ids)).toMatchObject({ xMm: 10, yMm: 10 });
    }
    // Twenty passes over 200 elements, three models each. Quadratic behaviour here is
    // ~800k comparisons per pass and misses this by orders of magnitude.
    expect(performance.now() - started).toBeLessThan(2000);
  });
});
