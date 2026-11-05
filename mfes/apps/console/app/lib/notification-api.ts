'use client';

import type { components } from '@janso/api-client/notification';
import { serviceCall } from './service-call';

import type { NotificationOwner } from './notification-ownership';
export { notificationPermission, type NotificationOwner } from './notification-ownership';
export type Provider = components['schemas']['ProviderItem'];
export type Template = components['schemas']['TemplateItem'];
export type Sender = components['schemas']['SenderIdentityItem'];
export type Variant = components['schemas']['VariantItem'];
export type Version = components['schemas']['VersionItem'];
export type Delivery = components['schemas']['DeliveryItem'];
export type NotificationRequest = components['schemas']['RequestItem'];
export type PlanningOutcome = components['schemas']['PlanningItem'];
export type ProviderReceipt = components['schemas']['ProviderReceiptItem'];
export type Route = components['schemas']['RoutingRuleItem'];
export type ChannelState = components['schemas']['ChannelReadiness'];
export type Job = components['schemas']['JobItem'];
export type Page<T> = { items: T[]; page: { has_more: boolean; next_cursor: string | null } };
export type UseCase = components['schemas']['UseCaseItem'];

export function notificationCall<T>(owner: NotificationOwner, resource: string, method = 'GET', body?: unknown, key?: string, signal?: AbortSignal): Promise<T> {
  return serviceCall<T>('/api/notifications', { service: 'notification', path: (owner === 'platform' ? '/v1/platform/' : '/v1/') + resource, method, body, key, signal }, 'notification');
}



export type ProviderDetail = components['schemas']['ProviderDetail'];
export type TemplateDetail = components['schemas']['TemplateDetail'];
export type VersionDetail = components['schemas']['VersionDetail'];
export type Activation = components['schemas']['ActivationItem'];
export type Binding = components['schemas']['BindingItem'];
export type Assignment = components['schemas']['AssignmentItem'];
export type DeliveryDetail = components['schemas']['DeliveryDetail'];
export type Attempt = components['schemas']['AttemptItem'];
export type DeliveryEvent = components['schemas']['EventItem'];
export type Endpoint = components['schemas']['RecipientEndpointItem'];
export type Consent = components['schemas']['ConsentStateItem'];
export type Suppression = components['schemas']['SuppressionItem'];
export type EffectiveResult = components['schemas']['EffectiveResult'];
export type CallbackConfiguration = components['schemas']['CallbackConfiguration'];
export type RouteDetail = components['schemas']['RouteDetail'];
export type RequestDetail = components['schemas']['RequestDetail'];
