import type { ReactNode } from 'react';

export type StatTone = 'default' | 'brand' | 'success' | 'warn' | 'danger';

type StatTileProps = {
  label: ReactNode;
  /**
   * Already formatted, and a **string**: money and quantities never become a JS `number` on
   * the client (design-system §5.4). `null`, `undefined` or blank means *no data*, which is a
   * different fact from zero — it renders an em-dash, never `0`.
   */
  value: string | null | undefined;
  footnote?: ReactNode;
  icon?: ReactNode;
  /** Colours the figure with `--janso-<tone>-ink`. */
  tone?: StatTone;
  /** Additionally tints the tile with the tone's triplet — how a row marks its lead metric. */
  emphasis?: boolean;
  /** A tile inside a card: quieter surface and the smaller figure step. */
  nested?: boolean;
  /**
   * A word-sized trend beside the footnote — normally a `Sparkline` over the same measure's own
   * series. A slot rather than a values prop, so the tile never has to know how a series is
   * labelled for a screen reader; the caller owns that sentence.
   */
  trend?: ReactNode;
};

export function StatTile({
  label,
  value,
  footnote,
  icon,
  tone = 'default',
  emphasis = false,
  nested = false,
  trend,
}: StatTileProps) {
  const classes = [
    'janso-stat',
    nested ? 'janso-stat--nested' : '',
    emphasis ? 'janso-stat--emphasis' : '',
  ]
    .filter(Boolean)
    .join(' ');

  const hasValue = typeof value === 'string' && value.trim() !== '';

  return (
    <div className={classes} data-tone={tone}>
      <div className="janso-stat__label">
        {icon ? (
          <span className="janso-stat__icon" aria-hidden="true">
            {icon}
          </span>
        ) : null}
        <span className="janso-stat__label-text">{label}</span>
      </div>
      <p className="janso-stat__value janso-figure">
        {hasValue ? (
          value
        ) : (
          /* An em-dash alone is announced as punctuation or skipped, so it carries a text
           * equivalent — "no value" and "0" must never sound the same either. */
          <>
            <span aria-hidden="true">&mdash;</span>
            <span className="janso-visually-hidden">No value</span>
          </>
        )}
      </p>
      {footnote || trend ? (
        <div className="janso-stat__foot">
          {footnote ? <p className="janso-stat__footnote">{footnote}</p> : null}
          {trend ? <span className="janso-stat__trend">{trend}</span> : null}
        </div>
      ) : null}
    </div>
  );
}

type StatRowProps = {
  /** 4-up by default; 3-up for a three-metric band. Both collapse at 1100px and 680px. */
  columns?: 3 | 4;
  children: ReactNode;
};

export function StatRow({ columns = 4, children }: StatRowProps) {
  return (
    <div className="janso-stat-row" data-columns={columns}>
      {children}
    </div>
  );
}
