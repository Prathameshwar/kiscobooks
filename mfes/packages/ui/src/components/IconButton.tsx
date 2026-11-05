import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react';

type IconButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'aria-label' | 'title'> & {
  /**
   * Required. An icon-only control with no accessible name is invisible to a screen
   * reader and unlabelled on hover, so the label is not optional — it becomes both the
   * `aria-label` and the native tooltip.
   */
  label: string;
  icon: ReactNode;
  variant?: 'ghost' | 'outline';
  /** Renders a dot over the icon — an unread marker. Never the only signal: see `label`. */
  badged?: boolean;
  /**
   * `sm` for a dense host — a table row, a toast — where the default 32px box would set the
   * host's height. The hit area stays above the 24px target-size floor.
   */
  size?: 'md' | 'sm';
};

/**
 * A square, icon-only button: the top bar's refresh / overflow / collapse controls.
 * Deliberately not a `Button` variant — its whole contract is that the label is a name
 * rather than visible content.
 *
 * The ref is forwarded because an icon button is what an anchored popover hangs off: `Menu`
 * measures its trigger to place the panel and returns focus to it on Escape, and neither is
 * possible through a wrapper element.
 */
export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { label, icon, variant = 'ghost', badged = false, size = 'md', className = '', type = 'button', ...rest },
  ref,
) {
  const classes = [
    'janso-btn',
    'janso-btn--icon',
    `janso-btn--icon-${variant}`,
    size === 'sm' ? 'janso-btn--icon-sm' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <button ref={ref} type={type} className={classes} aria-label={label} title={label} {...rest}>
      <span className="janso-btn__icon" aria-hidden="true">
        {icon}
      </span>
      {badged ? <span className="janso-btn__dot" aria-hidden="true" /> : null}
    </button>
  );
});
