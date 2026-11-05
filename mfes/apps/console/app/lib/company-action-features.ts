'use client';
import type { components } from '@janso/api-client/identity';
import { companyCall } from './company-api';
import { useServiceRead } from './service-resource';
import type { ServiceRequest } from './service-call';

type Configuration = components['schemas']['CompanySetupReadiness'];
export type CompanyActionFeatures = {
  enabled: readonly string[] | null;
  restriction?: string;
};
const readConfiguration = <T>(request: ServiceRequest) =>
  companyCall<T>('identity', request.path, { signal: request.signal });

export function useCompanyActionFeatures(
  company: string,
  canRead: boolean,
  requiredKeys: readonly string[],
) {
  const read = useServiceRead<Configuration>(
    canRead ? `/v1/companies/${company}/setup-readiness` : undefined,
    readConfiguration,
    (value) => {
      if (
        value?.company_id !== company ||
        !Array.isArray(value.features) ||
        value.features.length > 512 ||
        new Set(value.features.map((feature) => feature.feature_key)).size !==
          value.features.length ||
        value.features.some(
          (feature) =>
            !['ENABLED', 'DISABLED', 'INCONSISTENT'].includes(feature.state),
        ) ||
        !requiredKeys.every((key) =>
          value.features.some((feature) => feature.feature_key === key),
        )
      )
        throw {
          status: 502,
          message: 'Company capabilities could not be verified.',
        };
    },
    'company action configuration',
  );
  const data = canRead && read.data?.company_id === company ? read.data : null;
  const features: CompanyActionFeatures = {
    enabled: data
      ? data.features
          .filter((feature) => feature.state === 'ENABLED')
          .map((feature) => feature.feature_key)
      : null,
    restriction: !canRead
      ? 'Company configuration read access is required to verify availability.'
      : read.failure
        ? 'Company configuration is unavailable. Refresh to try again.'
        : !data
          ? 'Checking company configuration.'
          : undefined,
  };
  return { features, refresh: read.refresh, failure: read.failure };
}
