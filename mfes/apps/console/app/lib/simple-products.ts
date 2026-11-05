'use client';
import type { components } from '@janso/api-client/catalog';
export type SimpleFields = components['schemas']['SimpleProductFieldSet'];
export function verifySimpleFields(value: SimpleFields, company: string) {
  if (
    value.company_id !== company ||
    !Array.isArray(value.fields) ||
    new Set(value.fields.map((field) => field.key)).size !==
      value.fields.length ||
    !Number.isSafeInteger(value.authoring_version)
  )
    throw { status: 502, message: 'Product fields could not be verified.' };
}
export const simpleRoot = '/masters/items';
