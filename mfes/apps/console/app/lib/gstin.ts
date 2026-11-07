/** Accounting stores Indian GSTINs in uppercase without formatting separators. */
export const cleanGstin = (value: string) => value.toUpperCase().replace(/[\s-]/g, '');
