import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react';

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  /** `danger` is the confirming action of a destructive step — never a page's default action. */
  variant?: 'primary' | 'ghost' | 'danger';
  block?: boolean;
  /** Shows a spinner and disables the button; keeps the accessible name via `loadingLabel`. */
  loading?: boolean;
  loadingLabel?: string;
  children: ReactNode;
};

/** The ref is forwarded so a disclosure trigger can take focus back when its panel closes. */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button({
  variant = 'primary',
  block = false,
  loading = false,
  loadingLabel = 'Working…',
  className = '',
  disabled,
  children,
  ...rest
}, ref) {
  const classes = [
    'janso-btn',
    `janso-btn--${variant}`,
    block ? 'janso-btn--block' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <button ref={ref} className={classes} disabled={disabled || loading} aria-busy={loading} {...rest}>
      {loading ? (
        <>
          <span className="janso-btn__spinner" aria-hidden="true" />
          {loadingLabel}
        </>
      ) : (
        children
      )}
    </button>
  );
});
