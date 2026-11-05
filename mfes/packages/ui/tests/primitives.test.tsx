/**
 * The form and brand primitives.
 *
 * These tests moved here from `apps/auth/tests/ui-primitives.test.tsx`: a shared library
 * has to cover its own units, or its coverage floor depends on which consumer happens to
 * exercise it — and the second consumer (the console) uses a different subset. The auth app
 * keeps the tests for its own screens.
 *
 * Imports are source paths rather than '@janso/ui' so a package with a half-written barrel
 * still tests cleanly.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createRef } from 'react';
import { describe, expect, it } from 'vitest';
import { Button } from '../src/components/Button';
import { Checkbox } from '../src/components/Checkbox';
import { JansoMark } from '../src/components/JansoMark';
import { PasswordField, scorePassword } from '../src/components/PasswordField';
import { TextField } from '../src/components/TextField';
import { Wordmark } from '../src/components/Wordmark';
import { MailIcon } from '../src/components/icons';

describe('scorePassword', () => {
  it('scores by length then character variety', () => {
    expect(scorePassword('short')).toBe(0); // under 8 chars
    expect(scorePassword('abcdefgh')).toBe(1); // length only
    expect(scorePassword('Abcdefgh')).toBe(2); // + mixed case
    expect(scorePassword('Abcdefg1')).toBe(3); // + digit
    expect(scorePassword('Abcdefg1!')).toBe(4); // + symbol
  });
});

describe('Button', () => {
  it('shows a spinner, announces busy, and disables while loading', () => {
    render(
      <Button loading loadingLabel="Signing in…">
        Sign in
      </Button>,
    );
    const btn = screen.getByRole('button');
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute('aria-busy', 'true');
    expect(btn).toHaveTextContent('Signing in…');
    expect(btn).not.toHaveTextContent('Sign in');
  });

  it('forwards its ref to the native button', () => {
    const ref = createRef<HTMLButtonElement>();
    render(<Button ref={ref}>Filters</Button>);
    expect(ref.current).toBe(screen.getByRole('button', { name: 'Filters' }));
  });
});

describe('TextField', () => {
  it('wires label to input via a generated id', () => {
    render(<TextField label="User ID" placeholder="x" />);
    expect(screen.getByLabelText('User ID')).toBeInTheDocument();
  });

  it('marks the input invalid and announces the error', () => {
    render(<TextField label="Email" error="Enter a valid email" />);
    const input = screen.getByLabelText('Email');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('Enter a valid email');
    expect(input.getAttribute('aria-describedby')).toContain(alert.id);
  });

  it('renders a leading icon decoratively and pads the input for it', () => {
    render(<TextField label="Work email" leading={<MailIcon size={18} />} />);
    const input = screen.getByLabelText('Work email');
    expect(input.className).toContain('janso-input--leading');
    // the icon is decorative — the label names the field, so it is hidden from AT
    const lead = document.querySelector('.janso-input__lead');
    expect(lead).toHaveAttribute('aria-hidden', 'true');
  });
});

describe('PasswordField', () => {
  it('toggles between hidden and visible', async () => {
    const user = userEvent.setup();
    render(<PasswordField label="Password" value="hunter2" onChange={() => {}} />);
    const input = screen.getByLabelText('Password');
    expect(input).toHaveAttribute('type', 'password');
    // The toggle's accessible name carries the field it belongs to — a create-account form has
    // two of these, and "Show / Show" says nothing about which. Its visible word is still `Show`.
    await user.click(screen.getByRole('button', { name: 'Show password' }));
    expect(input).toHaveAttribute('type', 'text');
    await user.click(screen.getByRole('button', { name: 'Hide password' }));
    expect(input).toHaveAttribute('type', 'password');
  });

  it('shows the strength meter only when asked and only with input', () => {
    const { rerender } = render(
      <PasswordField label="Password" value="" onChange={() => {}} showStrength />,
    );
    expect(screen.queryByText(/Add|strong/i)).not.toBeInTheDocument();
    rerender(<PasswordField label="Password" value="Abcdef1!" onChange={() => {}} showStrength />);
    expect(screen.getByText('Strong')).toBeInTheDocument();
  });
});

describe('Checkbox', () => {
  it('renders a real checkbox with its label', async () => {
    const user = userEvent.setup();
    render(<Checkbox>Keep me signed in</Checkbox>);
    const box = screen.getByRole('checkbox', { name: /keep me signed in/i });
    expect(box).not.toBeChecked();
    await user.click(box);
    expect(box).toBeChecked();
  });

  it('carries the mixed state, which HTML has no attribute for', () => {
    const { rerender } = render(<Checkbox indeterminate>Select all rows on this page</Checkbox>);
    const box = screen.getByRole('checkbox');

    // The DOM property, set through a ref — browsers expose it as `aria-checked="mixed"`.
    expect(box).toBePartiallyChecked();
    expect(box).not.toBeChecked();

    rerender(<Checkbox indeterminate={false}>Select all rows on this page</Checkbox>);
    // Kept in step with the prop, not only set on mount: the parent re-renders with every tick.
    expect(box).not.toBePartiallyChecked();
  });

  it('describes a consequential option without swallowing it into the name', () => {
    render(<Checkbox hint="Permanent once used.">Stock and inventory</Checkbox>);
    const box = screen.getByRole('checkbox', { name: 'Stock and inventory' });

    // Described, not named: a screen reader says the label, then the explanation.
    expect(box).toHaveAccessibleDescription('Permanent once used.');
    expect(box).not.toHaveAccessibleName(/Permanent/);
  });

  it('keeps a label clickable when it carries a hint', async () => {
    const user = userEvent.setup();
    render(<Checkbox hint="Also turns on: Stock and inventory.">Batches</Checkbox>);

    await user.click(screen.getByText('Batches'));
    expect(screen.getByRole('checkbox')).toBeChecked();
  });
});

describe('JansoMark / Wordmark', () => {
  it('namespaces gradient ids so two lockups on one page do not collide', () => {
    const { container } = render(
      <div>
        <JansoMark />
        <JansoMark />
      </div>,
    );
    const grads = Array.from(container.querySelectorAll('linearGradient')).map((g) => g.id);
    expect(grads).toHaveLength(2);
    expect(grads[0]).not.toEqual(grads[1]);
  });

  it('renders the product name as live text', () => {
    const { container } = render(<Wordmark />);
    expect(container.querySelector('.janso-wordmark__name')).toHaveTextContent(/^KiscoBooks$/);
    expect(screen.getByText('Kisco')).toHaveClass('janso-wordmark__first');
    expect(screen.getByText('Books')).toHaveClass('janso-wordmark__last');
    expect(screen.getByRole('img', { name: 'KiscoBooks' })).toBeInTheDocument();
  });

  it('keeps the compact mark accessible without visible name or strapline', () => {
    render(<Wordmark size={28} showName={false} strapline="always balances" />);
    expect(screen.getByRole('img', { name: 'KiscoBooks' })).toHaveAttribute('width', '28');
    expect(screen.queryByText('Kisco')).not.toBeInTheDocument();
    expect(screen.queryByText('always balances')).not.toBeInTheDocument();
  });

  it('supports a strapline, requested name size and caller class', () => {
    const { container } = render(<Wordmark className="custom-lockup" nameSize="1.3rem" strapline="always balances" />);
    expect(container.firstChild).toHaveClass('custom-lockup');
    expect(container.querySelector('.janso-wordmark__name')).toHaveStyle({ fontSize: '1.3rem' });
    expect(screen.getByText('always balances')).toBeInTheDocument();
  });

  it('preserves a caller-supplied accessible mark title', () => {
    render(<JansoMark title="Workspace home" />);
    expect(screen.getByRole('img', { name: 'Workspace home' })).toBeInTheDocument();
  });
});
