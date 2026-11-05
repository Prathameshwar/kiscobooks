/**
 * `WizardLayout`, `FieldGrid`, `ReviewList` and the `Stepper` states they drive.
 *
 * The layout's contract is the three things a hand-composed wizard gets wrong: the form owns
 * submission (so Enter works), the heading takes focus when the step changes (so the change is
 * announced), and a visited-but-incomplete step is distinguishable from a finished one.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it, vi } from 'vitest';

import { FieldGrid, ReviewList, WizardLayout } from '../src/components/WizardLayout';
import { Stepper } from '../src/components/Stepper';
import { TextField } from '../src/components/TextField';

const SETUP_CSS = readFileSync(join(__dirname, '..', 'src', 'styles', 'setup.css'), 'utf8');

const STEPS = ['Business', 'Location and tax', 'Money and calendar'];

it('supports stacked summaries in narrow panels without adding edit controls', () => {
  const { container } = render(<ReviewList stacked items={[{ label: 'Saved name', value: 'A long product name that should use the full panel width' }]} />);
  expect(container.querySelector('dl')).toHaveClass('janso-setup__review--stacked');
  expect(screen.getByText('A long product name that should use the full panel width', { selector: 'dd' })).toBeVisible();
  expect(screen.queryByRole('button')).not.toBeInTheDocument();
});

function renderWizard(props: Partial<React.ComponentProps<typeof WizardLayout>> = {}) {
  const onSubmit = props.onSubmit ?? vi.fn((event) => event.preventDefault());
  const view = render(
    <WizardLayout
      brand={<span>JANSO</span>}
      headerEnd={<button type="button">Theme</button>}
      steps={STEPS}
      current={0}
      title="Business"
      subtitle="Tell us who issues the documents."
      progress="Step 1 of 3"
      actions={<button type="submit">Next</button>}
      {...props}
      onSubmit={onSubmit}
    >
      <TextField label="Legal name" />
    </WizardLayout>,
  );
  return { ...view, onSubmit };
}

describe('WizardLayout', () => {
  it('lays out the masthead, stepper, titled content and action bar', () => {
    const { container } = renderWizard();

    expect(container.querySelector('.janso-setup__header')).toHaveTextContent('JANSO');
    expect(screen.getByRole('navigation', { name: 'Setup progress' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'Business' })).toBeInTheDocument();
    expect(screen.getByText('Step 1 of 3')).toHaveClass('janso-setup__progress');
    expect(screen.getByText('Tell us who issues the documents.')).toHaveClass('janso-setup__subtitle');
    expect(container.querySelector('.janso-setup__actions--sticky')).toHaveTextContent('Next');
  });

  it('owns the form, so the step submits from the keyboard as well as the button', async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderWizard();

    await user.click(screen.getByRole('textbox', { name: 'Legal name' }));
    await user.keyboard('{Enter}');
    expect(onSubmit).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(onSubmit).toHaveBeenCalledTimes(2);
  });

  it('owns validation rather than leaving it to the browser’s bubbles', async () => {
    const user = userEvent.setup();
    const { container, onSubmit } = renderWizard({ children: <TextField label="Legal name" required /> });

    expect(container.querySelector('form')).toHaveAttribute('novalidate');
    // The step is submitted even with its required field empty: the caller decides what to say.
    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(onSubmit).toHaveBeenCalled();
  });

  it('leaves focus alone on arrival — there is nothing yet to announce', () => {
    renderWizard();
    expect(screen.getByRole('heading', { level: 1 })).not.toHaveFocus();
  });

  it('moves focus to the heading when the step changes', () => {
    const { rerender } = renderWizard();
    rerender(
      <WizardLayout
        brand={<span>JANSO</span>}
        steps={STEPS}
        current={1}
        title="Location and tax"
        actions={<button type="submit">Next</button>}
        onSubmit={vi.fn()}
      >
        <TextField label="Country" />
      </WizardLayout>,
    );

    expect(screen.getByRole('heading', { level: 1, name: 'Location and tax' })).toHaveFocus();
  });

  it('renders a notice above the card rather than inside it', () => {
    const { container } = renderWizard({ notice: <p role="alert">This code is already taken.</p> });

    const notice = screen.getByRole('alert');
    expect(notice).toBeInTheDocument();
    expect(container.querySelector('.janso-card')).not.toContainElement(notice);
  });

  it('pins the action bar to the paper so a long step cannot hide its own Next', () => {
    expect(SETUP_CSS).toMatch(/\.janso-setup__actions--sticky\s*\{[^}]*position: sticky/);
    expect(SETUP_CSS).toMatch(/\.janso-setup__actions--sticky\s*\{[^}]*background: var\(--janso-paper\)/);
  });
});

describe('FieldGrid and ReviewList', () => {
  it('stacks step content on the shared gap grid', () => {
    const { container } = render(
      <FieldGrid>
        <TextField label="One" />
        <TextField label="Two" />
      </FieldGrid>,
    );
    expect(container.querySelector('.janso-setup__fields')).toBeInTheDocument();
    expect(container.querySelector('fieldset')).not.toBeInTheDocument();
    expect(SETUP_CSS).toMatch(/\.janso-setup__fields\s*\{[^}]*display: grid/);
  });

  it('becomes a fieldset once asked to disable, taking every control out of play at once', () => {
    const { container, rerender } = render(
      <FieldGrid disabled>
        <TextField label="One" />
      </FieldGrid>,
    );
    const group = container.querySelector('fieldset.janso-setup__fields');
    expect(group).toBeDisabled();
    expect(screen.getByRole('textbox', { name: 'One' })).toBeDisabled();
    // The user-agent chrome a fieldset brings is reset, or the grid gains a border and padding.
    expect(SETUP_CSS).toMatch(/fieldset\.janso-setup__fields\s*\{[^}]*border: 0/);
    rerender(
      <FieldGrid disabled={false}>
        <TextField label="One" />
      </FieldGrid>,
    );
    expect(container.querySelector('fieldset.janso-setup__fields')).not.toBeDisabled();
    expect(screen.getByRole('textbox', { name: 'One' })).toBeEnabled();
  });

  it('renders a label and value pair per review row', () => {
    render(
      <ReviewList
        items={[
          { label: 'Base currency', value: 'INR' },
          { label: 'Financial year', value: '01-04-2026 → 31-03-2027' },
        ]}
      />,
    );

    expect(screen.getByText('Base currency')).toBeInTheDocument();
    expect(screen.getByText('INR')).toBeInTheDocument();
    expect(screen.getByText('01-04-2026 → 31-03-2027')).toBeInTheDocument();
    expect(screen.getAllByRole('term')).toHaveLength(2);
    expect(screen.getAllByRole('definition')).toHaveLength(2);
  });
});

describe('Stepper states', () => {
  it('keeps steps up to the furthest reached navigable, and locks the rest', async () => {
    const user = userEvent.setup();
    const onStep = vi.fn();
    render(<Stepper steps={STEPS} current={0} reached={2} onStep={onStep} />);

    // Step 3 has been reached, so returning forwards is allowed — a forward-only stepper would
    // trap someone who stepped back to correct one field.
    const third = screen.getByRole('button', { name: /Money and calendar/ });
    expect(third).toBeEnabled();
    await user.click(third);
    expect(onStep).toHaveBeenCalledWith(2);
  });

  it('marks a visited step that is still missing something, with a glyph and not colour alone', () => {
    render(
      <Stepper
        steps={[{ label: 'Business', complete: false, note: '2 required fields left' }, 'Location and tax']}
        current={1}
        reached={1}
        onStep={vi.fn()}
      />,
    );

    const incomplete = screen.getByRole('button', { name: /Business.*incomplete/ });
    expect(incomplete.closest('li')).toHaveAttribute('data-state', 'incomplete');
    expect(incomplete).toHaveTextContent('!');
    expect(screen.getByText('2 required fields left')).toHaveClass('janso-stepper__note');
    expect(SETUP_CSS).toContain(".janso-stepper [data-state='incomplete'] .janso-stepper__marker");
  });

  it('still reads a visited complete step as completed', () => {
    render(<Stepper steps={[{ label: 'Business', complete: true }, 'Location and tax']} current={1} onStep={vi.fn()} />);
    expect(screen.getByRole('button', { name: /Business.*completed/ })).toHaveTextContent('✓');
  });
});
