/** Match Accounting/Pydantic's character count, including supplementary Unicode characters. */
export const masterCodeLength = (value: string) => Array.from(value).length;

/** HTML maxlength counts UTF-16 units; cap master input by native characters instead. */
export const limitMasterCode = (value: string, max = 40) => Array.from(value).slice(0, max).join('');
