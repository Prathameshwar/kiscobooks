import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import { SimpleProductProgress } from '../app/components/SimpleProductProgress';

it('omits pricing milestones when no prices were captured', () => {
  render(<SimpleProductProgress pricing={false} busy job={{ status: 'RUNNING', step: 'ACTIVATE', code: 'SIMMINIMAL', opening_posted: false }} />);
  expect(screen.queryByText('Prices')).toBeNull();
  expect(screen.getByText('Activation')).toBeVisible();
});
it('includes pricing when the native stage confirms price work', () => {
  render(<SimpleProductProgress pricing={false} busy job={{ status: 'RUNNING', step: 'PUBLISH', code: 'SIMPRICES', opening_posted: false }} />);
  expect(screen.getByText('Prices')).toBeVisible();
});
