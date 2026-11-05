/**
 * Plural nouns, for the copy the list surface builds from a caller-supplied word.
 *
 * `DataTable`, `Pager` and `BulkBar` all take a `noun` — "invoice", "customer", "event" — and all
 * three write it into a sentence: "25 rows", "No invoices", "Previous page of customers",
 * "3 events selected on this page". Each had its own `${noun}s`, which is right for those three
 * words and wrong for most of the ledger's: `company` is the second resource this platform has, and
 * "2 companys selected" is the kind of copy defect that ships because it is nobody's component.
 *
 * Deliberately a small rule set, not a dictionary. It covers the regular English inflections —
 * consonant + `y`, and the sibilant endings that take `-es` — which is every entity name in
 * docs/org-model.md and docs/catalog-schema.md. An irregular noun states its own plural instead of
 * teaching this file a list of exceptions it would then have to keep: `series` is not hypothetical
 * here (an invoice series, docs/fiscal-year.md §7) and no rule turns it into itself.
 */

/** Ends in `y` after a consonant: `company`, `entry`, `currency`. `day` and `assay` do not. */
const CONSONANT_Y = /[^aeiou]y$/i;

/** Endings that need the extra syllable: `tax`, `address`, `batch`, `dispatch`, `size`. */
const SIBILANT = /(s|x|z|ch|sh)$/i;

/**
 * The plural of an English noun.
 *
 * Case is preserved by only ever appending — `Invoice` becomes `Invoices`, never `invoices` — so a
 * noun that arrives capitalised for a heading stays that way.
 */
export function pluralOf(noun: string): string {
  if (noun === '') return noun;
  if (CONSONANT_Y.test(noun)) return `${noun.slice(0, -1)}ies`;
  if (SIBILANT.test(noun)) return `${noun}es`;
  return `${noun}s`;
}

/**
 * The noun in the number the count calls for.
 *
 * Only `1` takes the singular: zero is plural in English ("No invoices", "0 rows"), which is the
 * case a naive `count > 1` gets wrong.
 */
export function pluralNoun(noun: string, count: number, plural?: string): string {
  return count === 1 ? noun : (plural ?? pluralOf(noun));
}
