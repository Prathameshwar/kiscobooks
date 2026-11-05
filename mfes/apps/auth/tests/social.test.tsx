import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SocialAuth } from '../app/components/SocialAuth';

describe('SocialAuth', () => {
  it('links to the gateway OAuth start routes', () => {
    render(<SocialAuth />);
    expect(screen.getByRole('link', { name: /continue with google/i })).toHaveAttribute(
      'href',
      '/oauth/google',
    );
    expect(screen.getByRole('link', { name: /continue with facebook/i })).toHaveAttribute(
      'href',
      '/oauth/facebook',
    );
  });

  it('keeps the label true to the flow', () => {
    const { rerender } = render(<SocialAuth verb="Sign in" />);
    expect(screen.getByRole('link', { name: 'Sign in with Google' })).toBeInTheDocument();
    expect(screen.getByText('or sign in with')).toBeInTheDocument();

    rerender(<SocialAuth verb="Sign up" />);
    expect(screen.getByRole('link', { name: 'Sign up with Google' })).toBeInTheDocument();
    expect(screen.getByText('or sign up with')).toBeInTheDocument();
  });
});
