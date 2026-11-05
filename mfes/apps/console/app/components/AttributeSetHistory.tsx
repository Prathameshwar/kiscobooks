'use client';
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  DataTable,
  Notice,
  Pager,
  Select,
} from '@janso/ui';
import { useState } from 'react';
import { masterRequest } from '../lib/catalog-master-api';
import type { MasterRow } from '../lib/catalog-masters';
import { useServiceList } from '../lib/service-resource';
import {
  attributeBase,
  attributeId,
  attributeLink,
  attributeVisible,
  useAttributeFields,
} from '../lib/attribute-masters';
import type { AttributeAccess } from '../lib/attribute-resources';
import { AttributeFailure } from './AttributeMasterCommon';
import { masterRevisionActions } from '../lib/master-navigation';
export function AttributeSetHistory({
  company,
  setId,
  here,
  active,
  canManage,
  access,
  blocked,
  onLeave,
}: {
  company: string;
  setId: string;
  here: string;
  active: boolean;
  canManage: boolean;
  access: AttributeAccess;
  blocked: boolean;
  onLeave: React.MouseEventHandler<HTMLAnchorElement>;
}) {
  const [published, setPublished] = useState(''),
    metadata = useAttributeFields(company, 'catalog.attribute_set_revision'),
    fields = metadata.data?.fields ?? [];
  const list = useServiceList<MasterRow>(
    attributeBase(company, 'attribute-sets/' + setId + '/revisions'),
    (attributeVisible(fields, 'published_at') && published
      ? 'published=' + published + '&'
      : '') + 'sort=-id',
    masterRequest,
    (row) => {
      if (
        !attributeId.test(row.id) ||
        (row.attribute_set_id && row.attribute_set_id !== setId)
      )
        throw {
          status: 502,
          message: 'Revision history could not be verified.',
        };
    },
  );
  return (
    <Card>
      <CardHeader
        title="Template revisions"
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
      <CardBody>
        <Notice>
          Published revisions are immutable. Create and publish a new draft to
          change requirements; product types retain their pinned revision.
        </Notice>
        {canManage && active && !blocked && access['attribute-definitions'] && (
          <a
            className="janso-btn janso-btn--primary"
            href={attributeLink(
              '/masters/attribute-sets/' + setId + '/revisions/new',
              here,
            )}
            onClick={onLeave}
          >
            New draft revision
          </a>
        )}
        {!active && (
          <Notice tone="warning">
            Activate this template before creating or publishing a revision.
          </Notice>
        )}
        {attributeVisible(fields, 'published_at') && (
          <Select
            label="Revision status"
            placeholder="All revisions"
            value={published}
            options={[
              { value: 'false', label: 'Draft' },
              { value: 'true', label: 'Published' },
            ]}
            onChange={setPublished}
          />
        )}
        <AttributeFailure
          failure={metadata.failure ?? list.failure}
          retry={() => {
            metadata.refresh();
            list.first();
          }}
        />
      </CardBody>
      <DataTable<MasterRow>
        rowActions={(row) =>
          masterRevisionActions(
            '/masters/attribute-sets/' + setId + '/revisions',
            row,
            here,
            canManage && active && attributeVisible(fields, 'published_at'),
            blocked,
          )
        }
        caption="Template revision history"
        rowId={(row) => row.id}
        rows={metadata.failure || list.failure ? [] : (list.data?.items ?? [])}
        loading={metadata.loading || list.loading}
        emptyTitle="No template revisions"
        emptyBody="Create a draft and add its attribute definitions."
        columns={[
          {
            key: 'revision',
            header: 'Revision',
            type: 'custom',
            render: (row) => (
              <a
                className="janso-link"
                href={attributeLink(
                  '/masters/attribute-sets/' + setId + '/revisions/' + row.id,
                  here,
                )}
                onClick={onLeave}
              >
                {row.revision != null && attributeVisible(fields, 'revision')
                  ? 'Revision ' + row.revision
                  : 'View revision'}
              </a>
            ),
          },
          ...(attributeVisible(fields, 'published_at')
            ? [
                {
                  key: 'status',
                  header: 'Status',
                  type: 'custom' as const,
                  render: (row: MasterRow) =>
                    !('published_at' in row)
                      ? 'Protected'
                      : row.published_at
                        ? 'Published'
                        : 'Draft',
                },
              ]
            : []),
        ]}
      />
      <Pager
        count={list.data?.items.length ?? 0}
        limit={list.limit}
        busy={list.loading}
        hasPrevious={list.hasPrevious}
        hasNext={!!list.data?.page.has_more}
        onPrevious={list.previous}
        onNext={list.next}
        onLimitChange={list.setLimit}
        noun="revision"
      />
    </Card>
  );
}
