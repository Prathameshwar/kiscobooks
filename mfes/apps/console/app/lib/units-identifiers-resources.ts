/** Shared route registry; server pages must not call exports of a client module. */
export const identifierResources = [
  'unit-conversions',
  'pack-types',
  'identifier-types',
  'identifier-namespaces',
  'identifier-profiles',
] as const;

export const isUnitsIdentifier = (resource: string) =>
  (identifierResources as readonly string[]).includes(resource);
