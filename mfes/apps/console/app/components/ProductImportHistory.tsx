'use client';
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  DataTable,
  EmptyState,
  Pager,
  Skeleton,
  useFormatters,
  type Column,
} from '@janso/ui';
import { ProductCatalogFailure } from './ProductCatalogCommon';
import {
  productImportProfile,
  type MasterImportProfile,
} from '../lib/master-import-profiles';
import {
  importBase,
  importStateLabel,
  importStateTone,
  useImportList,
  type ImportJobItem,
} from '../lib/product-import';

export function ProductImportHistory({
  company,
  jobLink,
  onLeave,
  profile = productImportProfile,
}: {
  company: string;
  jobLink: (id: string) => string;
  onLeave: React.MouseEventHandler<HTMLAnchorElement>;
  profile?: MasterImportProfile;
}) {
  const history = useImportList<ImportJobItem>(
      importBase(company) + '/import-jobs',
      profile.request,
    ),
    format = useFormatters();
  const rows =
    history.data?.items.filter((row) =>
      (profile.historyDefinitions ?? [profile.definition]).includes(
        row.definition,
      ),
    ) ?? [];
  const columns: Column<ImportJobItem>[] = [
    {
      key: 'created_at',
      header: 'Uploaded',
      type: 'custom',
      render: (row) => format.dateTime(row.created_at),
    },
    {
      key: 'state',
      header: 'Status',
      type: 'custom',
      render: (row) => (
        <Badge tone={importStateTone(row.state)}>
          {importStateLabel(row.state)}
        </Badge>
      ),
    },
    {
      key: 'revision',
      header: 'File revision',
      type: 'custom',
      render: (row) => String(row.revision),
    },
    {
      key: 'record_count',
      header: 'Commands',
      type: 'custom',
      render: (row) => String(row.record_count),
    },
    {
      key: 'completed_count',
      header: 'Imported',
      type: 'custom',
      render: (row) => String(row.completed_count),
    },
    {
      key: 'id',
      header: 'Review',
      type: 'custom',
      render: (row) => (
        <a className="janso-link" href={jobLink(row.id)} onClick={onLeave}>
          Open import {row.id.slice(-8)}
        </a>
      ),
    },
  ];
  return (
    <Card>
      <CardHeader
        title="Import history"
        action={
          <Button
            variant="ghost"
            onClick={history.first}
            disabled={history.loading}
          >
            Refresh history
          </Button>
        }
      />
      <CardBody>
        <div className="janso-flow">
          <p className="janso-fine">
            Your{' '}
            {profile.definition === 'parties'
              ? 'party and supplier'
              : 'product'}{' '}
            imports for this company, oldest first. Open an import to review
            validation messages, files and results.
          </p>
          <ProductCatalogFailure
            failure={history.failure}
            retry={history.first}
          />
          {history.loading ? (
            <div role="status" aria-label="Loading import history">
              <Skeleton />
            </div>
          ) : (
            !history.failure &&
            (rows.length ? (
              <DataTable
                caption={
                  (profile.definition === 'parties'
                    ? 'Party and supplier'
                    : 'Product') + ' import history'
                }
                columns={columns}
                rows={rows}
                rowId={(row) => row.id}
                rowLabel={(row) =>
                  profile.label + ' import ' + row.id.slice(-8)
                }
              />
            ) : (
              <EmptyState
                title={'No ' + profile.singular + ' imports on this page'}
                body={
                  'Upload a ' +
                  profile.singular +
                  ' file to start an import, or use the page controls to browse other history entries.'
                }
              />
            ))
          )}
          {history.data && !history.failure && (
            <Pager
              count={rows.length}
              limit={history.limit}
              noun={profile.singular + ' import'}
              hasPrevious={history.hasPrevious}
              hasNext={history.data.page.has_more}
              onPrevious={history.previous}
              onNext={history.next}
              busy={history.loading}
            />
          )}
        </div>
      </CardBody>
    </Card>
  );
}
