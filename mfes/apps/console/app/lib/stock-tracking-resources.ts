import type { components } from '@janso/api-client/accounting';

export type TrackingKind = 'batches' | 'serials';
export type TrackingListRow = components['schemas']['BatchListItem'] | components['schemas']['SerialListItem'];
export type TrackingSource = components['schemas']['TrackingSource'];
export const trackingId = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
export const trackingBase = (company: string, kind?: TrackingKind) => `/v1/companies/${company}/stock-tracking` + (kind ? '/' + kind : '');
export const trackingTitle = (row: TrackingListRow) => ('code' in row && row.code) || ('identifiers' in row && row.identifiers?.map(value => value.value).join(' / ')) || 'Protected tracking record';
