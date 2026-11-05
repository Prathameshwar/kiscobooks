'use client';

import { useId } from 'react';

/**
 * The JANSO logomark: a ledger tile holding the one truth of double-entry — that
 * the books balance — drawn as a rising top rule (growth, "in the black") over a
 * flat base rule, with a bright settled point.
 *
 * A self-contained SVG that carries its own gradient (influence: AI Force's
 * AiForceGlyph). Every gradient id is namespaced with `useId()` so two lockups on
 * one page — the sign-in panel renders one, the mobile header another — never both
 * paint from whichever mounted first (SVG resolves `url(#id)` document-wide).
 */
export function JansoMark({ size = 40, title = 'KiscoBooks' }: { size?: number; title?: string }) {
  const uid = useId();
  const tile = `${uid}-tile`;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      role="img"
      aria-label={title}
      focusable="false"
    >
      <defs>
        <linearGradient id={tile} x1="4" y1="2" x2="36" y2="38" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#4257a8" />
          <stop offset="1" stopColor="#2c3c86" />
        </linearGradient>
      </defs>
      <rect width="40" height="40" rx="10.5" fill={`url(#${tile})`} />
      <g stroke="#ffffff" strokeWidth="3.4" strokeLinecap="round">
        <path d="M9.5 16.6 27 11.8" />
        <path d="M9.5 25.6 31 25.6" />
      </g>
      <circle cx="30.2" cy="15" r="2.7" fill="#5b72d6" />
    </svg>
  );
}
