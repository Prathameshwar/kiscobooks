/**
 * Human labels for the company's stored vocabularies.
 *
 * **Why this file exists.** `gst_in`, `half_up` and `exclusive` are what the column holds, and
 * they were reaching the screen: the tax dropdown offered `gst_in` as its option text and the
 * review step printed "rounded half_up" to the person about to create a company. The wizard
 * already had human labels for entity types and rounding modes as local constants, so the
 * labels existed — they were just not used everywhere the value is shown.
 *
 * **Where this should live, eventually.** Entity types and rounding modes are a closed set this
 * client can reasonably own. **Tax systems are not**: `GET /v1/reference/countries` returns
 * `tax_systems: ['gst_in']` as bare codes, and every new jurisdiction the identity service
 * learns about would need a matching entry here or it would show a code again. The right fix is
 * for that endpoint to return `{ code, label }` the way it already does for currencies and
 * states. Until it does, `taxSystemLabel` falls back to a readable rendering of the code rather
 * than to the code itself, so a jurisdiction nobody has typed a label for still reads as words.
 */

/** Legal form of the business. A closed set, and the console's own vocabulary. */
export const ENTITY_TYPES = [
  { value: 'pvt_ltd', label: 'Private limited company' },
  { value: 'public', label: 'Public limited company' },
  { value: 'llp', label: 'Limited liability partnership' },
  { value: 'partnership', label: 'Partnership' },
  { value: 'sole_prop', label: 'Sole proprietorship' },
  { value: 'trust', label: 'Trust or society' },
  { value: 'branch', label: 'Branch or liaison office' },
] as const;

/**
 * How a half is rounded. The example matters more than the name — "banker's rounding" is a
 * phrase most people have heard and few could apply, so each option shows what it does.
 */
export const ROUNDING_MODES = [
  { value: 'half_up', label: 'Half up — 0.005 becomes 0.01' },
  { value: 'half_even', label: "Half even — banker's rounding, 0.005 becomes 0.00" },
  { value: 'down', label: 'Down — always towards zero' },
] as const;

/** Whether a quoted price already contains the tax. */
export const TAX_TREATMENTS = [
  { value: 'exclusive', label: 'Prices exclude tax' },
  { value: 'inclusive', label: 'Prices include tax' },
] as const;

/** The statutory tax regimes the platform has words for. */
const TAX_SYSTEMS: Record<string, string> = {
  gst_in: 'GST (India)',
  vat_gb: 'VAT (United Kingdom)',
  vat_eu: 'VAT (European Union)',
  gst_au: 'GST (Australia)',
  gst_nz: 'GST (New Zealand)',
  sales_tax_us: 'Sales tax (United States)',
  vat_ae: 'VAT (United Arab Emirates)',
  vat_sa: 'VAT (Saudi Arabia)',
  none: 'No tax system',
};

/** A readable rendering of an unknown code: `gst_sg` → "GST SG". Never the raw code. */
function readableCode(code: string): string {
  return code
    .split('_')
    .map((part) => (part.length <= 3 ? part.toUpperCase() : part.charAt(0).toUpperCase() + part.slice(1)))
    .join(' ');
}

export function taxSystemLabel(code: string): string {
  if (!code) return '';
  return TAX_SYSTEMS[code] ?? readableCode(code);
}

/** Options for a tax-system select, from the codes a country declares. */
export function taxSystemOptions(codes: readonly string[]): { value: string; label: string }[] {
  return codes.map((value) => ({ value, label: taxSystemLabel(value) }));
}

const from = (
  entries: readonly { readonly value: string; readonly label: string }[],
  value: string,
  fallback = value,
): string => entries.find((entry) => entry.value === value)?.label ?? fallback;

export const entityTypeLabel = (value: string): string => from(ENTITY_TYPES, value);

/**
 * The rounding mode in a sentence, without the worked example.
 *
 * The select needs "Half up — 0.005 becomes 0.01" because that is where the choice is made;
 * a review line reading "rounded Half up — 0.005 becomes 0.01" is the same explanation
 * arriving a second time, in the wrong place.
 */
export const roundingLabel = (value: string): string =>
  ({ half_up: 'half up', half_even: "banker's rounding", down: 'down' })[value] ?? readableCode(value);

export const taxTreatmentLabel = (value: string): string => from(TAX_TREATMENTS, value, value);

/* ---------------------------------------------------------------- presentation vocabularies */

/**
 * Suggested date patterns.
 *
 * **Suggestions, not a closed set.** `formatDate` is a pattern formatter with a documented
 * token vocabulary (`yyyy yy MMMM MMM MM M dd d HH mm ss`) and deliberate support for quoted
 * literals, so a `Select` here would remove capability the platform offers on purpose. These
 * are the patterns worth one click; anything else stays typeable, and the live preview beside
 * the field is what makes typing safe.
 */
export const DATE_FORMATS = [
  'dd-MM-yyyy',
  'dd/MM/yyyy',
  'dd MMM yyyy',
  'dd MMMM yyyy',
  'yyyy-MM-dd',
  'MM/dd/yyyy',
] as const;

export const DATETIME_FORMATS = [
  'dd-MM-yyyy HH:mm',
  'dd/MM/yyyy HH:mm',
  'dd MMM yyyy, HH:mm',
  'yyyy-MM-dd HH:mm',
  'MM/dd/yyyy HH:mm',
] as const;

/** The marks anyone actually uses between digits. Free entry stays open. */
export const SEPARATORS = ['.', ',', ' ', "'"] as const;

/** Language tags worth suggesting. The column takes any BCP-47 tag up to 8 characters. */
export const LOCALES = ['en', 'en-IN', 'en-GB', 'en-US', 'hi', 'mr', 'ta', 'te', 'gu', 'bn'] as const;

export const DIGIT_GROUPINGS = [
  { value: 'indian', label: 'Indian — 12,34,567' },
  { value: 'western', label: 'Western — 1,234,567' },
] as const;

export const NEGATIVE_FORMATS = [
  { value: 'minus', label: 'Minus sign — -1,234.00' },
  { value: 'parentheses', label: 'Parentheses — (1,234.00)' },
] as const;

export const SYMBOL_POSITIONS = [
  { value: 'prefix', label: 'Before the amount' },
  { value: 'suffix', label: 'After the amount' },
] as const;

/**
 * Canonical zones that must always be offered.
 *
 * Not only a fallback. This runtime's ICU reports `Asia/Calcutta` and not `Asia/Kolkata`:
 * both are valid IANA identifiers and Kolkata is the current canonical name, so a list taken
 * purely from the runtime suggested a zone the operator had not chosen while omitting the one
 * already sitting in the field. Merged, the list offers both and the field's own value is
 * always in it.
 */
const CANONICAL_TIMEZONES = [
  'Asia/Kolkata',
  'Asia/Dubai',
  'Asia/Singapore',
  'Europe/London',
  'Europe/Berlin',
  'America/New_York',
  'America/Los_Angeles',
  'Australia/Sydney',
  'UTC',
];

/**
 * Every IANA zone this runtime knows, for the time-zone suggestions.
 *
 * Read from the platform rather than kept as a list here: a hand-maintained copy of the tz
 * database is a copy that goes stale, and the browser already ships the real one. The short
 * canonical list is merged in rather than used only as a fallback, both because
 * `Intl.supportedValuesOf` is absent in some runtimes and because the ones that have it do
 * not all use the current canonical names.
 */
export function supportedTimezones(): readonly string[] {
  const intl = Intl as typeof Intl & { supportedValuesOf?: (key: string) => string[] };
  let zones: readonly string[] = [];
  try {
    zones = intl.supportedValuesOf?.('timeZone') ?? [];
  } catch {
    zones = [];
  }
  return [...new Set([...CANONICAL_TIMEZONES, ...zones])].sort((a, b) => a.localeCompare(b));
}

/* ---------------------------------------------------------------- capability tree */

type Capability = { key: string; requires: readonly string[] };

/**
 * The capability catalogue as the chain it actually is.
 *
 * Stock, then batches, then expiry dates: three levels, stated in the catalogue as
 * `requires` and previously rendered as a flat list of seven checkboxes whose descriptions
 * ended "Also turns on: Batches." A reader had to assemble the hierarchy from prose. This
 * returns the same set in depth-first order with a depth per entry, so the indent carries it.
 *
 * Depth is capped at 2 because the card styling offers two indents; a catalogue that grows a
 * fourth level will show it flat rather than silently mis-indent, which is the failure mode
 * worth having.
 */
export function capabilityTree<T extends Capability>(
  items: readonly T[],
): readonly { item: T; depth: 0 | 1 | 2 }[] {
  const byKey = new Map(items.map((item) => [item.key, item]));
  const out: { item: T; depth: 0 | 1 | 2 }[] = [];
  const placed = new Set<string>();

  /** How far down the chain this capability sits, following the first requirement. */
  const depthOf = (item: Capability, guard = 0): number => {
    const parent = item.requires.find((key) => byKey.has(key));
    if (!parent || guard > 8) return 0;
    const next = byKey.get(parent);
    return next ? depthOf(next, guard + 1) + 1 : 0;
  };

  const emit = (item: T): void => {
    if (placed.has(item.key)) return;
    placed.add(item.key);
    const depth = Math.min(depthOf(item), 2) as 0 | 1 | 2;
    out.push({ item, depth });
    // Dependents directly after their parent, in catalogue order.
    for (const candidate of items) {
      if (candidate.requires.includes(item.key)) emit(candidate);
    }
  };

  for (const item of items) {
    if (!item.requires.some((key) => byKey.has(key))) emit(item);
  }
  // Anything whose requirement is not in the offered set still has to appear.
  for (const item of items) emit(item);
  return out;
}
