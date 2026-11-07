'use client';
import { useEffect, useRef, useState } from 'react';
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  ConfirmDialog,
  DataTable,
  Disclosure,
  FileUpload,
  FormActions,
  FormLayout,
  Notice,
  PageHeader,
  PageNavigation,
  SectionHeader,
  Select,
  SearchSelect,
  TextField,
  Skeleton,
  StatRow,
  StatTile,
  Stepper,
  Tabs,
  tabButtonId,
  type FileUploadItem,
} from '@janso/ui';
import { useServiceCommand, useServiceRead } from '../lib/service-resource';
import {
  requestFailure,
  type RequestFailure,
  type ServiceRequest,
} from '../lib/service-call';
import type { MasterImportProfile } from '../lib/master-import-profiles';
import {
  assertImportJob,
  assertImportTemplate,
  importBase,
  importFileProblem,
  importMaximumBytes,
  importMaximumFiles,
  importSourceFiles,
  importStateLabel,
  type ImportArtifact,
  type ImportDefinitions,
  type ImportDownload,
  type ImportFormat,
  type ImportJob,
  type ImportTemplate,
  type StageImport,
} from '../lib/product-import';
import { ProductCatalogFailure } from './ProductCatalogCommon';
import { useAccessDraft } from './AccessCommon';
import { ProductImportHistory } from './ProductImportHistory';
import { ProductImportResults } from './ProductImportResults';
import { ProductImportConfigurationGuide } from './ProductImportConfigurationGuide';
import { PartyImportOpeningGuide } from './PartyImportOpeningGuide';
import { SimpleProductImportProgress } from './SimpleProductImportProgress';

type Intent = {
  request: ServiceRequest;
  kind: 'template' | 'job';
  message: string;
  after?: (value: ImportTemplate | ImportJob) => Promise<void>;
};
type Schema = {
  properties?: Record<
    string,
    { title?: string; type?: string; enum?: unknown[] }
  >;
  required?: string[];
};
const titles: Record<string, string> = {
  STAGED: 'Files uploaded. Validate them before importing.',
  INVALID:
    'Validation found problems. Review the messages and upload corrected files.',
  READY:
    'Validation passed. Review the results before importing. Validation has not saved product changes.',
  SUCCEEDED:
    'Product import completed successfully. Open the imported products to review their setup.',
  PARTIAL:
    'Some commands were imported. Correct or retry the remaining work; completed commands will not run again.',
  FAILED:
    'The import did not complete. Review its messages, then correct or revalidate the remaining work.',
  CANCELLED:
    'This import is cancelled. Its history and any completed work are retained.',
  EXPIRED:
    'The source files have expired. Start a new import using a current template.',
};

export function MasterImport({
  profile,
  company,
  canManage,
  returnTo,
  initialJob,
  initialHistory = false,
}: {
  profile: MasterImportProfile;
  company: string;
  canManage: boolean;
  returnTo?: string;
  initialJob?: string;
  initialHistory?: boolean;
}) {
  const base = importBase(company),
    back = profile.back(returnTo, profile.directory);
  const [view, setView] = useState(
      initialHistory ? 'import-history' : 'product-import',
    ),
    [jobKey, setJobKey] = useState(initialJob),
    [job, setJob] = useState<ImportJob | null>(null);
  const [template, setTemplate] = useState<ImportTemplate | null>(null),
    [resource, setResource] = useState(profile.defaultResource),
    [kind, setKind] = useState(profile.defaultParameter),
    [mode, setMode] = useState<'CREATE_ONLY' | 'UPDATE_ONLY'>('CREATE_ONLY'),
    [format, setFormat] = useState<ImportFormat>('XLSX');
  const [autoRun, setAutoRun] = useState(false);
  const [pendingOwner, setPendingOwner] = useState<boolean | null>(null);
  const [templateContext, setTemplateContext] = useState<
    Record<string, string>
  >(profile.templateContext?.defaults ?? {});
  const [contextLabels, setContextLabels] = useState<
    Record<string, { id: string; label: string }>
  >({});
  const [atomicity, setAtomicity] =
      useState<StageImport['atomicity']>('CHANGE_SET'),
    [onError, setOnError] = useState<StageImport['on_error']>(
      'CONTINUE_INDEPENDENT',
    );
  const [files, setFiles] = useState<File[]>([]),
    [localFailure, setLocalFailure] = useState<RequestFailure | null>(null),
    [fileError, setFileError] = useState(''),
    [message, setMessage] = useState('');
  const [reading, setReading] = useState(false),
    [downloading, setDownloading] = useState(false),
    [stale, setStale] = useState(false),
    [review, setReview] = useState<{
      action: 'commit' | 'cancel';
      version: number;
      digest: string | null;
      count: number;
    } | null>(null);
  const intent = useRef<Intent | null>(null),
    readingBusy = useRef(false),
    command = useServiceCommand(profile.request, profile.singular + ' import');
  const busy = command.pending || reading || downloading,
    locked = busy || command.uncertain;
  const guard = useAccessDraft(
    files.length > 0 || command.uncertain || !!review,
    command.pending || reading,
  );
  const definitions = useServiceRead<ImportDefinitions>(
    base + '/import-definitions',
    profile.request,
    (value) => {
      if (
        !value ||
        !Array.isArray(value.items) ||
        !value.items.some((row) => row.key === profile.definition) ||
        !Array.isArray(value.formats) ||
        value.formats.some(
          (value) => !['CSV', 'TSV', 'XLSX'].includes(value),
        ) ||
        !Number.isInteger(value.maximum_commands) ||
        value.maximum_commands < 1
      )
        throw {
          status: 502,
          message: profile.label + ' import options could not be verified.',
        };
    },
  );
  const selected = useServiceRead<ImportJob>(
    jobKey ? base + '/import-jobs/' + jobKey : undefined,
    profile.request,
    (value) => assertImportJob(value, jobKey, profile.definition),
  );
  useEffect(() => {
    if (selected.data)
      setJob((current) =>
        !current ||
        current.id !== selected.data!.id ||
        current.row_version <= selected.data!.row_version
          ? selected.data
          : current,
      );
  }, [selected.data]);
  const terminal =
      !!job && ['SUCCEEDED', 'CANCELLED', 'EXPIRED'].includes(job.state),
    expired = !!job && Date.parse(job.expires_at) <= Date.now();
  const actionable =
    !!job && canManage && !terminal && !expired && !locked && !files.length;
  const ownerPending =
    ['VALIDATING', 'IMPORTING'].includes(job?.state ?? '') ||
    (!!profile.readyProducts && job?.state === 'PARTIAL' && pendingOwner !== false);
  const canReadDetails = !profile.detailsRequireManage || canManage;
  const here =
    profile.path +
    '?' +
    new URLSearchParams({ ...(jobKey ? { job: jobKey } : {}), returnTo: back });
  const jobLink = (id: string) =>
    profile.path + '?' + new URLSearchParams({ job: id, returnTo: back });
  const newLink = profile.path + '?' + new URLSearchParams({ returnTo: back });
  const action = mode === 'UPDATE_ONLY' ? 'UPDATE' : 'CREATE';
  const schema = template
    ? (template.snapshot.schemas as Record<string, Schema>)[
        resource + ':' + action
      ]
    : undefined;
  function updateTemplate(change: () => void) {
    if (locked || job || files.length) return;
    change();
    setTemplate(null);
    command.clear();
    setLocalFailure(null);
    setMessage('');
  }
  async function execute(next: Intent) {
    if (command.pending || (command.uncertain && intent.current !== next))
      return;
    intent.current = next;
    setLocalFailure(null);
    const value = await command.execute<ImportTemplate | ImportJob>(
      next.request,
      (result) =>
        next.kind === 'template'
          ? assertImportTemplate(result as ImportTemplate, profile.definition)
          : assertImportJob(result as ImportJob, job?.id, profile.definition),
    );
    if (!value) {
      setReview(null);
      if (next.kind === 'job') setStale(true);
      return;
    }
    intent.current = null;
    setReview(null);
    setMessage(next.message);
    if (next.kind === 'template') setTemplate(value as ImportTemplate);
    else {
      const saved = value as ImportJob;
      setJob(saved);
      setJobKey(saved.id);
      setFiles([]);
      setFileError('');
      window.history.replaceState(null, '', jobLink(saved.id));
      setStale(false);
    }
    try {
      await next.after?.(value);
    } catch (error) {
      setLocalFailure(
        requestFailure(error, profile.singular + ' import download'),
      );
    }
  }
  async function getTemplate() {
    if (!canManage || locked) return;
    const startDownload = async (value: ImportTemplate | ImportJob) => {
      const prepared = value as ImportTemplate;
      if (
        !(prepared.snapshot.schemas as Record<string, unknown>)[
          resource + ':' + action
        ]
      )
        throw {
          status: 403,
          message: `Your current ${profile.singular} permissions do not include this template operation.`,
        };
      setDownloading(true);
      try {
        await profile.download(
          {
            path:
              base +
              '/import-templates/' +
              prepared.id +
              '?' +
              new URLSearchParams({ resource, action, format }),
          },
          profile.plural +
            '-' +
            resource.replaceAll('_', '-') +
            '.' +
            format.toLowerCase(),
        );
      } finally {
        setDownloading(false);
      }
    };
    if (template) {
      try {
        await startDownload(template);
      } catch (error) {
        setLocalFailure(
          requestFailure(error, profile.singular + ' import template'),
        );
      }
    } else
      await execute({
        request: {
          path: base + '/import-templates',
          method: 'POST',
          body: {
            definition: profile.definition,
            parameters: {
              resource,
              ...(resource === profile.parameterResource
                ? Object.fromEntries(
                    Object.entries(templateContext).filter(
                      ([, value]) => value,
                    ),
                  )
                : {}),
              [profile.templateParameter]:
                resource === 'supplier'
                  ? 'SUPPLIER'
                  : resource === 'customer'
                    ? 'CUSTOMER'
                    : kind,
            },
          },
        },
        kind: 'template',
        message: `Your current ${profile.singular} template is ready. Fill it in, then upload the completed file.`,
        after: startDownload,
      });
  }
  function chooseFiles(chosen: File[]) {
    if (locked) return;
    const next = [...files, ...chosen],
      problem = importFileProblem(next);
    if (problem) {
      setFileError(problem);
      return;
    }
    setFiles(next);
    setFileError('');
    setLocalFailure(null);
    command.clear();
  }
  async function upload() {
    if (!canManage || locked || readingBusy.current || (!job && !template))
      return;
    const problem = importFileProblem(files);
    if (problem) {
      setFileError(problem);
      return;
    }
    readingBusy.current = true;
    setReading(true);
    setLocalFailure(null);
    try {
      const source = await importSourceFiles(files);
      await execute({
        kind: 'job',
        request: job
          ? {
              path: base + '/import-jobs/' + job.id + '/revisions',
              method: 'POST',
              body: { expected_version: job.row_version, files: source },
            }
          : {
              path: base + '/import-jobs',
              method: 'POST',
              body: {
                template_id: template!.id,
                mode,
                atomicity,
                on_error: onError,
                files: source,
              },
            },
        message: job
          ? 'Corrected files uploaded. Validate this revision before importing.'
          : `Files uploaded successfully. Validate them to check each ${profile.singular}.`,
      });
    } catch (error) {
      setLocalFailure({
        status: 422,
        message:
          error instanceof Error
            ? error.message
            : 'The selected file could not be prepared. Choose it again.',
      });
    } finally {
      readingBusy.current = false;
      setReading(false);
    }
  }
  async function mutate(name: 'validate' | 'retry' | 'commit' | 'cancel') {
    if (!job || !canManage || locked || terminal || expired) return;
    const snapshot = review;
    if (
      ['commit', 'cancel'].includes(name) &&
      (!snapshot ||
        snapshot.action !== name ||
        snapshot.version !== job.row_version)
    )
      return;
    if (
      name === 'commit' &&
      (job.state !== 'READY' ||
        stale ||
        !snapshot?.digest ||
        snapshot.digest !== job.review_digest)
    )
      return;
    await execute({
      kind: 'job',
      request: {
        path: base + '/import-jobs/' + job.id + '/' + name,
        method: 'POST',
        body: {
          expected_version:
            snapshot && snapshot.action === name
              ? snapshot.version
              : job.row_version,
          ...(name === 'commit' ? { review_digest: snapshot!.digest } : {}),
        },
      },
      message:
        name === 'cancel'
          ? 'Import cancelled. Its history is retained.'
          : name === 'commit'
            ? 'Import attempt finished. Review the results below.'
            : 'Validation finished. Review the row results and messages below.',
      after:
        profile.readyProducts && ['commit', 'validate', 'retry'].includes(name)
          ? async (value) => {
              setAutoRun(
                ['VALIDATING', 'IMPORTING', 'PARTIAL'].includes(
                  (value as ImportJob).state,
                ),
              );
              setMessage(
                name === 'commit'
                  ? 'Import started. Product readiness and opening stock are being processed.'
                  : 'Validation checks each product. No product changes are saved.',
              );
            }
          : undefined,
    });
  }
  async function continueImport() {
    if (!job || !canManage || locked || !actionable || profile.readyProducts ||
        !['VALIDATING', 'IMPORTING'].includes(job.state) || command.failure) return;
    const name = job.state === 'VALIDATING' ? 'validate' : 'commit';
    if (name === 'commit' && !job.review_digest) return;
    await execute({
      kind: 'job',
      request: {
        path: base + '/import-jobs/' + job.id + '/' + name,
        method: 'POST',
        body: {expected_version: job.row_version,
          ...(name === 'commit' ? {review_digest: job.review_digest} : {})},
      },
      message: name === 'validate' ? 'Remaining products checked. Review the results below.' :
        'Reviewed import continued. Review the results below.',
    });
  }
  async function download(
    kind: ImportDownload['kind'] = 'RESULT',
    artifact?: ImportArtifact,
    attempt?: string,
    revision?: number,
  ) {
    if (!job || downloading || command.pending) return;
    setDownloading(true);
    setLocalFailure(null);
    try {
      const options: ImportDownload = {
        kind,
        format: (artifact?.format as ImportFormat) ?? 'CSV',
        ...(artifact ? { artifact_id: artifact.id } : {}),
        ...(attempt ? { attempt_id: attempt } : {}),
        ...(revision ? { revision } : {}),
      };
      const ticket = await profile.request<{ token: string }>({
        path: base + '/import-jobs/' + job.id + '/download-ticket',
        method: 'POST',
        body: options,
      });
      if (
        !ticket ||
        typeof ticket.token !== 'string' ||
        !ticket.token ||
        ticket.token.length > 4096
      )
        throw {
          status: 502,
          message: 'A private download could not be prepared.',
        };
      await profile.download(
        {
          path: base + '/import-jobs/' + job.id + '/download',
          method: 'POST',
          body: { ...options, token: ticket.token },
        },
        artifact?.filename ??
          profile.singular + '-import-' + kind!.toLowerCase() + '.csv',
      );
    } catch (error) {
      setLocalFailure(
        requestFailure(error, profile.singular + ' import download'),
      );
    } finally {
      setDownloading(false);
    }
  }
  const uploadItems: FileUploadItem[] = files.map((file, index) => ({
    id: String(index),
    name: file.name,
    size: file.size,
    status: reading ? 'uploading' : 'pending',
  }));
  const uploadControl = (
    <FileUpload
      label={
        job ? 'Corrected import files' : `Completed ${profile.singular} files`
      }
      items={uploadItems}
      accept=".csv,.tsv,.xlsx"
      acceptLabel="CSV, TSV or Excel XLSX"
      multiple
      maxFiles={importMaximumFiles}
      maxSizeBytes={importMaximumBytes}
      onSelect={chooseFiles}
      onRemove={(item) => {
        setFiles((current) =>
          current.filter((_, index) => String(index) !== item.id),
        );
        setFileError('');
      }}
      disabled={locked || !canManage || (!job && !template)}
      error={fileError}
      hint="Up to 16 files, 8 MB combined. Use the downloaded template and keep identifiers and decimal values as text."
    />
  );
  return (
    <div className="janso-page">
      <PageNavigation
        back={{ href: back, label: profile.plural }}
        breadcrumbs={[
          { label: 'Masters', href: '/masters' },
          { label: profile.directoryLabel, href: back },
          { label: profile.title },
        ]}
        onNavigate={guard.leave}
      />
      <PageHeader
        title={profile.title}
        lede={`Upload ${profile.singular} files, check every row, then review and import. Your results and messages remain available in history.`}
        actions={
          job ? (
            <a
              className="janso-btn janso-btn--ghost"
              href={newLink}
              onClick={guard.leave}
            >
              Start another import
            </a>
          ) : undefined
        }
      />
      <Tabs
        label={profile.label + ' import workspace'}
        tabs={[
          {
            id: 'product-import',
            label: job ? 'Import details' : 'New import',
          },
          { id: 'import-history', label: 'Import history' },
        ]}
        active={view}
        onChange={(value) => {
          if (locked) return;
          setView(value);
        }}
        panelId="product-import-panel"
      />
      {!canManage && <Notice>{profile.readOnlyMessage}</Notice>}
      <ProductCatalogFailure
        failure={localFailure ?? command.failure}
        write={command.uncertain}
      />
      {command.uncertain && (
        <Notice
          tone="warning"
          action={
            <Button
              onClick={() => intent.current && void execute(intent.current)}
              loading={command.pending}
            >
              Retry same action
            </Button>
          }
        >
          The last action could not be confirmed. Your exact request is
          retained. Recover that action before making another change.
        </Notice>
      )}
      {(command.failure ||
        (!job && [409, 410].includes(localFailure?.status ?? 0))) &&
        !command.uncertain &&
        command.failure?.status !== 422 && (
          <Button
            variant="ghost"
            disabled={busy}
            onClick={() => {
              command.clear();
              setLocalFailure(null);
              if (job) selected.refresh();
              else {
                setTemplate(null);
                definitions.refresh();
              }
              setReview(null);
            }}
          >
            Reload and review
          </Button>
        )}
      {message && (
        <Notice
          tone={
            job && ['INVALID', 'FAILED'].includes(job.state)
              ? 'warning'
              : 'success'
          }
          live="polite"
        >
          {message}
        </Notice>
      )}
      {(busy || command.pending) && (
        <p role="status">
          {reading
            ? 'Preparing your files…'
            : downloading
              ? 'Preparing your download…'
              : 'Processing the import action. Please keep this page open.'}
        </p>
      )}
      <section
        id="product-import-panel"
        role="tabpanel"
        aria-labelledby={tabButtonId(view)}
        className="janso-flow"
      >
        {view === 'import-history' ? (
          <ProductImportHistory
            profile={profile}
            company={company}
            jobLink={jobLink}
            onLeave={guard.leave}
          />
        ) : (
          <>
            <ProductCatalogFailure
              failure={definitions.failure ?? selected.failure}
              retry={() => {
                definitions.refresh();
                selected.refresh();
              }}
            />
            {definitions.loading || (selected.loading && !job) ? (
              <div
                role="status"
                aria-label={'Loading ' + profile.singular + ' import'}
              >
                <Skeleton />
              </div>
            ) : job ? (
              <>
                <Stepper
                  orientation="horizontal"
                  steps={[
                    'Upload files',
                    'Validate',
                    'Review and import',
                    'Complete',
                  ]}
                  current={
                    job.state === 'SUCCEEDED'
                      ? 3
                      : ['READY', 'PARTIAL', 'IMPORTING'].includes(job.state)
                        ? 2
                        : 1
                  }
                />
                <Notice
                  tone={
                    job.state === 'SUCCEEDED'
                      ? 'success'
                      : ['INVALID', 'FAILED'].includes(job.state)
                        ? 'danger'
                        : 'info'
                  }
                  title={importStateLabel(job.state)}
                >
                  {job.state === 'SUCCEEDED'
                    ? profile.success
                    : job.state === 'VALIDATING'
                      ? 'Validation is in progress. Continue checking remaining products below.'
                      : ownerPending
                        ? 'Import is in progress. Resume pending products below; completed products are preserved.'
                        : titles[job.state]?.replace(
                            'product changes',
                            profile.singular + ' changes',
                          )}
                </Notice>
                {expired && job.state !== 'EXPIRED' && (
                  <Notice tone="warning">
                    Source files have expired. You can still review retained
                    import history.
                  </Notice>
                )}
                {stale && (
                  <Notice tone="warning">
                    Reload the latest import and validate again before
                    importing. The previous review is no longer usable.
                  </Notice>
                )}
                <StatRow>
                  <StatTile
                    label={
                      profile.readyProducts
                        ? 'Products in this revision'
                        : 'Commands in this revision'
                    }
                    value={String(job.record_count)}
                  />
                  <StatTile
                    label="Imported"
                    value={String(job.completed_count)}
                    tone="success"
                  />
                  <StatTile
                    label="File revision"
                    value={String(job.revision)}
                  />
                  <StatTile
                    label="Status"
                    value={importStateLabel(job.state)}
                    tone={job.state === 'INVALID' ? 'danger' : 'brand'}
                  />
                </StatRow>
                <Card>
                  <CardHeader title="Review and continue" />
                  <CardBody>
                    <div className="janso-flow">
                      {files.length > 0 && (
                        <Notice>
                          Upload the corrected revision or remove the selected
                          files before validating or importing the current
                          revision.
                        </Notice>
                      )}
                      <p>
                        Imports use your current {profile.singular} permissions
                        and configuration. {profile.lifecycle}
                      </p>
                      <div className="janso-form-actions">
                        {!profile.readyProducts && ownerPending && canManage && (
                          <Button disabled={!actionable || !!command.failure}
                            onClick={() => void continueImport()}>
                            {job.state === 'VALIDATING' ? 'Continue validation' : 'Continue import'}
                          </Button>
                        )}
                        {canManage &&
                          !terminal &&
                          !expired &&
                          !ownerPending && (
                            <Button
                              disabled={
                                !actionable ||
                                (!!command.failure &&
                                  command.failure.status !== 422)
                              }
                              onClick={() =>
                                void mutate(
                                  ['PARTIAL', 'FAILED'].includes(job.state)
                                    ? 'retry'
                                    : 'validate',
                                )
                              }
                            >
                              {job.state === 'STAGED'
                                ? 'Validate files'
                                : 'Revalidate remaining work'}
                            </Button>
                          )}
                        {job.state === 'READY' && canManage && (
                          <Button
                            disabled={
                              !actionable ||
                              stale ||
                              !job.review_digest ||
                              !!command.failure
                            }
                            onClick={() =>
                              setReview({
                                action: 'commit',
                                version: job.row_version,
                                digest: job.review_digest,
                                count: job.record_count,
                              })
                            }
                          >
                            Review import
                          </Button>
                        )}
                        {canManage &&
                          !terminal &&
                          !expired &&
                          !ownerPending && (
                            <Button
                              variant="ghost"
                              disabled={!actionable}
                              onClick={() =>
                                setReview({
                                  action: 'cancel',
                                  version: job.row_version,
                                  digest: null,
                                  count: job.record_count,
                                })
                              }
                            >
                              Cancel import
                            </Button>
                          )}
                        {canReadDetails &&
                          !expired &&
                          job.state !== 'STAGED' && (
                            <Button
                              variant="ghost"
                              disabled={locked}
                              onClick={() => void download('RESULT')}
                            >
                              Download results
                            </Button>
                          )}
                        {canReadDetails && !expired && (
                          <Button
                            variant="ghost"
                            disabled={locked}
                            onClick={() => void download('NORMALIZED')}
                          >
                            Download staged input
                          </Button>
                        )}
                        {canManage &&
                          !terminal &&
                          !expired &&
                          !ownerPending && (
                            <Button
                              variant="ghost"
                              disabled={locked}
                              onClick={() => void download('CORRECTION')}
                            >
                              Download correction file
                            </Button>
                          )}
                      </div>
                    </div>
                  </CardBody>
                </Card>
                {canManage && !terminal && !expired && !ownerPending && (
                  <Card>
                    <CardHeader title="Upload corrected files" />
                    <CardBody>
                      <div className="janso-flow">
                        <p className="janso-fine">
                          Use the correction file to retain row keys and
                          successful prerequisites. Upload all replacement files
                          for the revision, then validate again. Successful work
                          is preserved.
                        </p>
                        {uploadControl}
                        <Button
                          disabled={locked || !files.length}
                          loading={reading}
                          onClick={() => void upload()}
                        >
                          Upload corrected revision
                        </Button>
                      </div>
                    </CardBody>
                  </Card>
                )}
                {canReadDetails && (
                  <>
                    {profile.readyProducts && (
                      <SimpleProductImportProgress
                        key={company + ':' + job.id}
                        company={company}
                        job={job}
                        canManage={canManage && !locked}
                        autoRun={autoRun}
                        onStarted={() => setAutoRun(false)}
                        onPending={setPendingOwner}
                        onJob={(value) => {
                          setJob(value);
                          setStale(false);
                          if (value.state === 'SUCCEEDED') setMessage('');
                        }}
                      />
                    )}
                    <ProductImportResults
                      profile={profile}
                      key={job.id + ':' + job.row_version}
                      company={company}
                      job={job}
                      here={here}
                      download={(kind, artifact, attempt, revision) =>
                        void download(kind, artifact, attempt, revision)
                      }
                      downloading={locked}
                      onLeave={guard.leave}
                    />
                  </>
                )}
              </>
            ) : (
              !jobKey &&
              definitions.data &&
              !definitions.failure && (
                <>
                  <Stepper
                    orientation="horizontal"
                    steps={[
                      'Upload files',
                      'Validate',
                      'Review and import',
                      'Complete',
                    ]}
                    current={0}
                  />
                  <FormLayout
                    aside={
                      <>
                        <SectionHeader title="Prepare your file" />
                        <p className="janso-fine">
                          Download a current template. Excel includes field
                          instructions and permitted reference options in
                          separate sheets.
                        </p>
                        <p className="janso-fine">{profile.preparation}</p>
                        {profile.openingResources?.includes(resource) && (
                          <PartyImportOpeningGuide company={company} />
                        )}
                        <p className="janso-fine">
                          Up to {definitions.data.maximum_commands}{' '}
                          {profile.readyProducts ? 'products' : 'commands'} per
                          import. Validation checks required fields, references
                          and duplicates before you confirm any changes.
                        </p>
                      </>
                    }
                  >
                    <div className="janso-flow">
                      <Card>
                        <CardHeader
                          title={
                            '1. Choose a ' + profile.singular + ' template'
                          }
                        />
                        <CardBody>
                          <div className="janso-form-grid">
                            {!profile.readyProducts && (
                              <Select
                                label="Import content"
                                value={resource}
                                options={profile.resources}
                                disabled={
                                  locked || !canManage || !!files.length
                                }
                                onChange={(value) =>
                                  updateTemplate(() => {
                                    setResource(value);
                                    if (
                                      profile.createOnlyResources.includes(
                                        value,
                                      )
                                    )
                                      setMode('CREATE_ONLY');
                                    else if (
                                      profile.updateOnlyResources?.includes(
                                        value,
                                      )
                                    )
                                      setMode('UPDATE_ONLY');
                                  })
                                }
                              />
                            )}
                            {(resource === profile.parameterResource ||
                              (profile.definition === 'parties' &&
                                [
                                  'party_accounting_policy',
                                  'party_credit_policy',
                                ].includes(resource))) && (
                              <Select
                                label={profile.parameterLabel}
                                value={kind}
                                options={profile.parameters}
                                disabled={
                                  locked || !canManage || !!files.length
                                }
                                onChange={(value) =>
                                  updateTemplate(() => {
                                    setKind(value);
                                    setTemplateContext((previous) => ({
                                      as_of: previous.as_of ?? '',
                                    }));
                                    setContextLabels({});
                                  })
                                }
                              />
                            )}
                            {profile.templateContext &&
                              resource === profile.parameterResource && (
                                <>
                                  <TextField
                                    label="Configuration date"
                                    type="date"
                                    value={templateContext.as_of ?? ''}
                                    disabled={
                                      locked || !canManage || !!files.length
                                    }
                                    onChange={(event) =>
                                      updateTemplate(() =>
                                        setTemplateContext((previous) => ({
                                          ...previous,
                                          as_of: event.target.value,
                                        })),
                                      )
                                    }
                                  />
                                  {(
                                    [
                                      'product_type_revision_id',
                                      'group_id',
                                    ] as const
                                  ).map((field) => (
                                    <SearchSelect
                                      key={field}
                                      label={
                                        field === 'group_id'
                                          ? 'Product group for template'
                                          : 'Published product type for template'
                                      }
                                      hint="Optional. Choose the context used to prepare this template."
                                      value={templateContext[field] || null}
                                      selected={contextLabels[field] ?? null}
                                      disabled={
                                        locked || !canManage || !!files.length
                                      }
                                      loadOptions={(args) =>
                                        profile.templateContext!.loadOptions(
                                          company,
                                          field,
                                          { ...templateContext, kind },
                                          args,
                                        )
                                      }
                                      onChange={(id, option) =>
                                        updateTemplate(() => {
                                          setTemplateContext((previous) => ({
                                            ...previous,
                                            [field]: id ?? '',
                                          }));
                                          setContextLabels((previous) => {
                                            const next = { ...previous };
                                            if (option) next[field] = option;
                                            else delete next[field];
                                            return next;
                                          });
                                        })
                                      }
                                    />
                                  ))}
                                </>
                              )}
                            {!profile.readyProducts && (
                              <Select
                                label="Import operation"
                                value={mode}
                                options={[
                                  {
                                    value: 'CREATE_ONLY',
                                    label:
                                      'Create new ' + profile.plural + ' only',
                                    disabled:
                                      profile.updateOnlyResources?.includes(
                                        resource,
                                      ),
                                  },
                                  {
                                    value: 'UPDATE_ONLY',
                                    label:
                                      'Update existing ' +
                                      profile.plural +
                                      ' only',
                                    disabled:
                                      profile.createOnlyResources.includes(
                                        resource,
                                      ),
                                  },
                                ]}
                                disabled={
                                  locked || !canManage || !!files.length
                                }
                                onChange={(value) =>
                                  updateTemplate(() =>
                                    setMode(value as typeof mode),
                                  )
                                }
                              />
                            )}
                            <Select
                              label="Template format"
                              value={format}
                              options={definitions.data.formats.map(
                                (value) => ({
                                  value,
                                  label:
                                    value === 'XLSX'
                                      ? 'Excel workbook (.xlsx)'
                                      : value + ' text file',
                                }),
                              )}
                              disabled={locked || !canManage}
                              onChange={(value) =>
                                setFormat(value as ImportFormat)
                              }
                            />
                          </div>
                        </CardBody>
                        <FormActions>
                          <Button
                            variant="ghost"
                            disabled={locked || !canManage}
                            onClick={() => void getTemplate()}
                          >
                            Download template
                          </Button>
                        </FormActions>
                      </Card>
                      <Card>
                        <CardHeader title="2. Upload your completed files" />
                        <CardBody>
                          <div className="janso-flow">
                            {!template && (
                              <Notice>
                                Download the current template before uploading
                                completed files.
                              </Notice>
                            )}
                            {uploadControl}
                            {!profile.readyProducts && (
                              <Disclosure summary="Import behaviour">
                                <div className="janso-form-grid">
                                  <Select
                                    label={
                                      'If a ' + profile.singular + ' fails'
                                    }
                                    value={onError ?? 'CONTINUE_INDEPENDENT'}
                                    options={[
                                      {
                                        value: 'CONTINUE_INDEPENDENT',
                                        label:
                                          'Continue with unrelated ' +
                                          profile.plural,
                                      },
                                      {
                                        value: 'STOP',
                                        label: 'Stop at the first failed group',
                                      },
                                    ]}
                                    disabled={locked || !canManage}
                                    onChange={(value) =>
                                      setOnError(value as typeof onError)
                                    }
                                  />
                                  <Select
                                    label="Save changes"
                                    value={atomicity ?? 'CHANGE_SET'}
                                    options={[
                                      {
                                        value: 'CHANGE_SET',
                                        label:
                                          'Each ' +
                                          profile.singular +
                                          ' group independently',
                                      },
                                      {
                                        value: 'ATOMIC',
                                        label:
                                          'All ' + profile.plural + ' together',
                                      },
                                    ]}
                                    disabled={locked || !canManage}
                                    onChange={(value) =>
                                      setAtomicity(value as typeof atomicity)
                                    }
                                  />
                                </div>
                              </Disclosure>
                            )}
                          </div>
                        </CardBody>
                        <FormActions>
                          <Button
                            disabled={
                              locked ||
                              !canManage ||
                              !template ||
                              !schema ||
                              !files.length
                            }
                            loading={reading}
                            onClick={() => void upload()}
                          >
                            Upload and prepare validation
                          </Button>
                        </FormActions>
                      </Card>
                      {template && (
                        <Disclosure summary="Template column guide">
                          <div className="janso-flow">
                            {!!template.snapshot.product_configuration && (
                              <ProductImportConfigurationGuide
                                value={template.snapshot.product_configuration}
                              />
                            )}
                            {profile.readyProducts ? (
                              <p className="janso-fine">
                                One row creates one product. Keep codes and
                                decimal amounts as text. Blank code is generated
                                automatically; blank group uses Default.
                                Corrections retain the supplied row key.
                              </p>
                            ) : (
                              <p className="janso-fine">
                                Set _key and _set to stable row/group keys,
                                _resource to {resource}, and _action to AUTO.
                                Nested fields use JSON text; identifiers and
                                decimals stay text. Empty update cells leave
                                saved values unchanged.
                              </p>
                            )}
                            {schema ? (
                              <DataTable
                                caption={profile.label + ' template fields'}
                                rows={Object.entries(
                                  schema.properties ?? {},
                                ).map(([key, value]) => ({
                                  key,
                                  title:
                                    value.title ?? key.replaceAll('_', ' '),
                                  required: schema.required?.includes(key)
                                    ? 'Required'
                                    : 'Optional',
                                  type:
                                    value.type ??
                                    'See workbook field instructions',
                                }))}
                                rowId={(row) => row.key}
                                rowLabel={(row) => row.title}
                                columns={[
                                  {
                                    key: 'key',
                                    header: 'Column',
                                    type: 'code',
                                  },
                                  {
                                    key: 'title',
                                    header: 'Field',
                                    type: 'text',
                                  },
                                  {
                                    key: 'required',
                                    header: 'Requirement',
                                    type: 'text',
                                  },
                                  {
                                    key: 'type',
                                    header: 'Value',
                                    type: 'text',
                                  },
                                ]}
                              />
                            ) : (
                              <Notice tone="warning">
                                Your permissions do not include the selected
                                operation. Select another operation or ask an
                                administrator to review your access.
                              </Notice>
                            )}
                          </div>
                        </Disclosure>
                      )}
                    </div>
                  </FormLayout>
                </>
              )
            )}
          </>
        )}
      </section>
      <ConfirmDialog
        open={!!review}
        title={
          review?.action === 'commit'
            ? 'Import validated ' + profile.plural + '?'
            : 'Cancel this import?'
        }
        confirmLabel={
          review?.action === 'commit' ? profile.title : 'Cancel import now'
        }
        tone={review?.action === 'cancel' ? 'danger' : 'default'}
        busy={command.pending}
        onCancel={() => setReview(null)}
        onConfirm={() => review && void mutate(review.action)}
      >
        {review?.action === 'commit' ? (
          <p>
            Import the reviewed revision containing {review.count} commands.
            Review its row results and staged input: this runs the commands
            declared in your files. Current permissions and {profile.singular}
            configuration will be checked again. Completed work will not be
            repeated.
          </p>
        ) : (
          <p>
            Stop further work on this import. Its history and any{' '}
            {profile.plural}
            already imported will be retained.
          </p>
        )}
      </ConfirmDialog>
      {guard.confirmation}
    </div>
  );
}
