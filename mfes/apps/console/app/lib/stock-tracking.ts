'use client';
import { serviceCall, type ServiceRequest } from './service-call';

export const trackingRequest = <T>(request: ServiceRequest) => serviceCall<T>('/api/product-fields', { ...request, service: 'accounting' }, 'batch and serial tracking');
