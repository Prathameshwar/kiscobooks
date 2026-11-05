'use client';
import { useState } from 'react';
import {
  Button,
  Card,
  CardHeader,
  DataTable,
  Notice,
  Pager,
  Select,
  useFormatters,
} from '@janso/ui';
import { masterRequest } from '../lib/catalog-master-api';
import type { MasterRow } from '../lib/catalog-masters';
import { useServiceList } from '../lib/service-resource';
import {
  profileBase,
  profileId,
  profileLink,
  profileVisible,
  useProfileFields,
} from '../lib/product-profiles';
import {
  profileDefinitions,
  type ProductProfileResource,
} from '../lib/product-profile-resources';
import { ProfileFailure } from './ProductProfileCommon';
import { masterRevisionActions } from '../lib/master-navigation';
export function ProductProfileHistory({
  company,
  resource,
  parentId,
  here,
  active,
  canManage,
  blocked,
  onLeave,
}: {
  company: string;
  resource: ProductProfileResource;
  parentId: string;
  here: string;
  active: boolean;
  canManage: boolean;
  blocked: boolean;
  onLeave: React.MouseEventHandler<HTMLAnchorElement>;
}) {
  const operation = resource.startsWith('manufacturing-');
  const noun = resource === 'manufacturing-routes' ? 'route' : 'operation';
  const [published, setPublished] = useState(''),
    metadata = useProfileFields(
      company,
      profileDefinitions[resource].entity + '_revision',
    ),
    fields = metadata.data?.fields ?? [],
    format = useFormatters();
  const list = useServiceList<MasterRow>(
    profileBase(company, resource + '/' + parentId + '/revisions'),
    (profileVisible(fields, operation ? 'status' : 'published_at') && published
      ? (operation ? 'status=' : 'published=') + published + '&'
      : '') +
      'sort=' +
      (profileVisible(fields, 'revision') ? '-revision' : '-id'),
    masterRequest,
    (row) => {
      const key = profileDefinitions[resource].parent;
      if (!profileId.test(row.id) || (key in row && row[key] !== parentId))
        throw {
          status: 502,
          message: 'The revision history does not match this profile.',
        };
    },
  );
  const root = '/masters/' + resource + '/' + parentId + '/revisions',
    failure = metadata.failure ?? list.failure;
  return (
    <Card>
      <CardHeader
        title={
          operation
            ? noun === 'route'
              ? 'Route revisions'
              : 'Operation revisions'
            : 'Profile revisions'
        }
        action={
          <Button
            variant="ghost"
            disabled={list.loading || blocked}
            onClick={list.first}
          >
            Refresh revisions
          </Button>
        }
      />
      <div className="janso-page-navigation">
        {canManage && active && !blocked && (
          <a
            className="janso-btn janso-btn--primary"
            href={profileLink(root + '/new', here)}
            onClick={onLeave}
          >
            New draft revision
          </a>
        )}
        {profileVisible(fields, operation ? 'status' : 'published_at') && (
          <Select
            label="Revision status"
            value={published}
            placeholder="All revisions"
            options={
              operation
                ? [
                    { value: 'DRAFT', label: 'Drafts' },
                    { value: 'PUBLISHED', label: 'Published' },
                    { value: 'RETIRED', label: 'Retired' },
                  ]
                : [
                    { value: 'false', label: 'Drafts' },
                    { value: 'true', label: 'Published' },
                  ]
            }
            onChange={setPublished}
          />
        )}
      </div>
      {!active && (
        <Notice>
          Activate the {operation ? noun : 'profile'} before creating, editing
          or publishing revisions.
        </Notice>
      )}
      <ProfileFailure
        failure={failure}
        retry={() => {
          metadata.refresh();
          list.first();
        }}
      />
      {!failure && (
        <>
          <DataTable
            caption={
              operation
                ? 'Operation revision history'
                : 'Profile revision history'
            }
            rowId={(row) => row.id}
            loading={metadata.loading || list.loading}
            rows={list.data?.items ?? []}
            emptyTitle="No revisions found"
            emptyBody={
              operation
                ? 'Create a draft revision to define this ' + noun + '.'
                : 'Create a draft revision to define this profile.'
            }
            columns={[
              {
                key: 'revision',
                header: 'Revision',
                type: 'custom',
                render: (row) => (
                  <a
                    className="janso-link"
                    href={profileLink(root + '/' + row.id, here)}
                    onClick={onLeave}
                  >
                    {profileVisible(fields, 'revision') && row.revision != null
                      ? 'Revision ' + row.revision
                      : 'View revision'}
                  </a>
                ),
              },
              ...(profileVisible(fields, 'published_at')
                ? [
                    {
                      key: 'published_at',
                      header: 'Status',
                      type: 'custom' as const,
                      render: (row: MasterRow) =>
                        !('published_at' in row)
                          ? 'Protected'
                          : row.status === 'RETIRED' &&
                              profileVisible(fields, 'status')
                            ? 'Retired'
                            : row.published_at === null
                              ? 'Draft'
                              : 'Published ' +
                                format.dateTime(String(row.published_at)),
                    },
                  ]
                : []),
            ]}
            rowActions={(row) =>
              masterRevisionActions(
                root,
                row,
                here,
                canManage && active && profileVisible(fields, 'published_at'),
                blocked,
              )
            }
          />
          <Pager
            noun="revision"
            count={list.data?.items.length ?? 0}
            limit={list.limit}
            hasPrevious={list.hasPrevious}
            hasNext={list.data?.page.has_more ?? false}
            onPrevious={list.previous}
            onNext={list.next}
            onLimitChange={list.setLimit}
            busy={list.loading || blocked}
          />
        </>
      )}
    </Card>
  );
}
