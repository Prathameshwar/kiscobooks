export const attributeResources = [
  'attribute-definitions',
  'attribute-options',
  'attribute-sets',
] as const;
export type AttributeResource = (typeof attributeResources)[number];
export const isAttributeResource = (
  value: string,
): value is AttributeResource =>
  (attributeResources as readonly string[]).includes(value);
export type AttributeAccess = Record<AttributeResource, boolean> & {
  units: boolean;
  products: boolean;
  publish: boolean;
};
