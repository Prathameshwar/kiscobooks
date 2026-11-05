import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { Stepper } from '../src/components/Stepper';

describe('Stepper', () => {
  it('allows future navigation without claiming an upcoming step is complete', async () => {
    const onStep = vi.fn();
    render(<Stepper steps={['Details', 'Units', 'Review']} current={0} allowFuture onStep={onStep} />);
    const review = screen.getByRole('button', { name: /Review.*upcoming/ });
    expect(review).toBeEnabled();
    await userEvent.click(review);
    expect(onStep).toHaveBeenCalledWith(2);
  });
  it('supports horizontal page progress while retaining the current-step announcement', () => {
    render(<Stepper steps={['Upload', 'Validate', 'Import']} current={1} orientation="horizontal" />);
    expect(screen.getByRole('navigation', { name: 'Setup progress' })).toHaveClass('janso-stepper--horizontal');
    expect(screen.getByRole('button', { name: /Validate/ })).toHaveAttribute('aria-current', 'step');
  });
  it('announces progress, locks future steps and allows revisiting completed steps', async () => {
    const onStep = vi.fn();
    render(<Stepper steps={['Unlock', 'Connections', 'Administrator']} current={1} onStep={onStep} />);
    expect(screen.getByRole('navigation', { name: 'Setup progress' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Connections/ })).toHaveAttribute('aria-current', 'step');
    expect(screen.getByRole('button', { name: /Administrator/ })).toBeDisabled();
    const unlock = screen.getByRole('button', { name: /Unlock.*completed/ });
    await userEvent.click(unlock);
    expect(onStep).toHaveBeenCalledWith(0);
  });
  it('disables all navigation when no handler is provided', () => {
    render(<Stepper steps={['One', 'Two']} current={0} />);
    expect(screen.getAllByRole('button').every(button => (button as HTMLButtonElement).disabled)).toBe(true);
  });
});
