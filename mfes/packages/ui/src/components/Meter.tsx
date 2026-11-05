import type { Tone } from './Badge';

type MeterProps = {
  /** A share, 0–1. Out-of-range input is clamped rather than allowed to overflow the track. */
  value: number;
  tone?: Tone;
  /** The accessible name. "42%" on its own tells a screen-reader user 42% of what. */
  label?: string;
};

/**
 * The thin share meter under a list row. A real `progressbar` with aria bounds on the 0–1
 * scale the prop uses, plus `aria-valuetext` so the announcement is the percentage a sighted
 * reader sees rather than "0.42".
 */
export function Meter({ value, tone = 'brand', label = 'Share' }: MeterProps) {
  const clamped = Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 0;
  const percent = Math.round(clamped * 100);

  return (
    <div className="janso-meter" data-tone={tone}>
      <div
        className="janso-meter__track"
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={1}
        aria-valuenow={clamped}
        aria-valuetext={`${percent}%`}
      >
        {/* A data-driven width is the one thing no token can express, so it stays inline. */}
        <span className="janso-meter__fill" style={{ width: `${percent}%` }} />
      </div>
      <span className="janso-meter__percent janso-figure">{percent}%</span>
    </div>
  );
}
