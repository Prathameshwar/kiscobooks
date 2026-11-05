'use client';
import { PageNavigation, Notice } from '@janso/ui';
import { masterReturn } from '../lib/master-navigation';
import { useServiceRead } from '../lib/service-resource';
import { masterRequest } from '../lib/catalog-master-api';
import { bomBase } from '../lib/boms';

export function useBomContext(company: string) {
  return useServiceRead<{
    company_id: string;
    enabled: boolean;
    operational_ready: false;
  }>(
    bomBase(company, '/authoring-context'),
    masterRequest,
    (value) => {
      if (
        value.company_id !== company ||
        typeof value.enabled !== 'boolean' ||
        value.operational_ready !== false
      )
        throw {
          status: 502,
          message: 'BOM company configuration could not be verified.',
        };
    },
    'BOM company configuration',
  );
}
export function BomNavigation({
  title,
  back = '/masters/boms',
  onLeave,
}: {
  title: string;
  back?: string;
  onLeave?: React.MouseEventHandler<HTMLAnchorElement>;
}) {
  return (
    <PageNavigation
      back={{
        href: masterReturn(back, '/masters/boms'),
        label: 'previous page',
      }}
      breadcrumbs={[
        { label: 'Business overview', href: '/' },
        { label: 'Masters', href: '/masters' },
        ...(title === 'Bills of materials'
          ? []
          : [{ label: 'Bills of materials', href: '/masters/boms' }]),
        { label: title },
      ]}
      onNavigate={onLeave}
    />
  );
}
export function BomExplanation() {
  return (
    <Notice>
      Define a single-level recipe with one primary output and optional
      co-products, by-products or scrap. Publication preserves the reviewed
      recipe and its references. Quantity previews do not reserve stock,
      schedule production or post costs.
    </Notice>
  );
}
