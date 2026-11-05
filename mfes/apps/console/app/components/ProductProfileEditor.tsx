'use client';
import { useEffect, useRef, useState } from 'react';
import {
  Button,
  Card,
  CardBody,
  ConfirmDialog,
  FormActions,
  FormLayout,
  Notice,
  PageHeader,
} from '@janso/ui';
import {
  masterBody,
  type MasterConfig,
  type MasterRow,
} from '../lib/catalog-masters';
import { masterRequest, useMasterRecord } from '../lib/catalog-master-api';
import {
  useServiceCommand,
  useServiceRead,
  type ServicePage,
} from '../lib/service-resource';
import {
  profileBase,
  profileLink,
  profileReceipt,
  profileReturn,
  profileVisible,
  profileWritable,
} from '../lib/product-profiles';
import type {
  ProductProfileAccess,
  ProductProfileResource,
} from '../lib/product-profile-resources';
import {
  ProfileFailure,
  ProfileField,
  ProfileNavigation,
} from './ProductProfileCommon';
import { useAccessDraft } from './AccessCommon';
export function ProductProfileEditor({
  company,
  config,
  id,
  returnTo,
  access,
}: {
  company: string;
  config: MasterConfig;
  id?: string;
  returnTo?: string;
  access: ProductProfileAccess;
}) {
  const root = '/masters/' + config.resource,
    back = profileReturn(returnTo, id ? root + '/' + id : root),
    record = useMasterRecord(company, config, id, true);
  const history = useServiceRead<ServicePage<MasterRow>>(
    id
      ? profileBase(
          company,
          config.resource + '/' + id + '/revisions?limit=1&sort=-id',
        )
      : undefined,
    masterRequest,
    (page) => {
      if (!Array.isArray(page.items) || !page.page)
        throw {
          status: 502,
          message: 'Profile revision history could not be verified.',
        };
    },
  );
  const codeLocked = !!id && !!history.data?.items.length;
  const fields = record.fields.map((field) => ({
    ...field,
    writable:
      field.writable &&
      !field.conditional_access &&
      !(codeLocked && field.key === 'code'),
  }));
  const [values, setValues] = useState<Record<string, unknown>>({}),
    [initialized, setInitialized] = useState(false),
    [dirty, setDirty] = useState(false),
    [errors, setErrors] = useState<Record<string, string>>({}),
    [saved, setSaved] = useState<MasterRow | null>(null),
    [frozen, setFrozen] = useState<Record<string, unknown> | null>(null),
    [reload, setReload] = useState(false),
    [notice, setNotice] = useState('');
  const command = useServiceCommand(masterRequest, 'product profiles'),
    guard = useAccessDraft(dirty || command.uncertain, command.pending),
    form = useRef<HTMLFormElement>(null);
  useEffect(() => {
    if (record.loading || history.loading) {
      setInitialized(false);
      return;
    }
    setValues(id ? { ...record.row } : { ...config.initial });
    setDirty(false);
    setErrors({});
    setSaved(null);
    setFrozen(null);
    setNotice('');
    setInitialized(true);
  }, [record.loading, history.loading, record.row, config, id]);
  useEffect(() => {
    if (command.failure?.fields) setErrors(command.failure.fields);
  }, [command.failure]);
  useEffect(() => {
    if (Object.keys(errors).length)
      form.current
        ?.querySelector<HTMLElement>('[aria-invalid="true"]')
        ?.focus();
  }, [errors]);
  const complete =
    profileVisible(fields, 'row_version') &&
    (id
      ? ['code', 'name'].some((key) => profileWritable(fields, [key]))
      : profileWritable(fields, ['code', 'name', 'is_active']));
  async function submit() {
    if (
      !complete ||
      record.loading ||
      !initialized ||
      history.loading ||
      saved ||
      command.pending ||
      (command.blocked && !command.uncertain) ||
      record.failure ||
      history.failure
    )
      return;
    const result = masterBody(config, fields, values, record.row ?? undefined);
    setErrors(result.errors);
    if (Object.keys(result.errors).length) return;
    if (id && Object.keys(result.body).length === 1) {
      setDirty(false);
      setNotice('No changes to save.');
      return;
    }
    const body = command.uncertain && frozen ? frozen : result.body;
    setFrozen(body);
    const row = await command.execute<MasterRow>(
      {
        path: profileBase(company, config.resource) + (id ? '/' + id : ''),
        method: id ? 'PATCH' : 'POST',
        body,
      },
      (row) => profileReceipt(row, company, id, record.row?.row_version),
    );
    if (row) {
      setSaved(row);
      setDirty(false);
      setFrozen(null);
    }
  }
  const change = (key: string, value: unknown) => {
    if (!id && command.failure?.status === 409) command.clear();
    setValues((current) => ({ ...current, [key]: value }));
    setDirty(true);
    setErrors({});
    setNotice('');
  };
  return (
    <div className="janso-page">
      <ProfileNavigation
        resource={config.resource as ProductProfileResource}
        title={(id ? 'Edit ' : 'New ') + config.singular}
        back={back}
        access={access}
        onLeave={guard.leave}
      />
      <PageHeader
        title={(id ? 'Edit ' : 'New ') + config.singular}
        lede={
          config.resource.startsWith('manufacturing-')
            ? 'Save the ' +
              (config.resource === 'manufacturing-routes'
                ? 'route'
                : 'operation') +
              ' identity, then define its specifications and revisions.'
            : 'Save the profile identity, then define its reusable revisions.'
        }
      />
      <ProfileFailure
        failure={record.failure ?? history.failure}
        retry={() => {
          record.refresh();
          history.refresh();
        }}
      />
      <ProfileFailure failure={command.failure} write={command.uncertain} />
      {command.failure && !command.uncertain && id && (
        <Button variant="ghost" onClick={() => setReload(true)}>
          Reload and review
        </Button>
      )}
      {command.failure?.status === 409 && !id && (
        <Notice>
          Correct the duplicate code or name and try again. Your values are
          retained.
        </Notice>
      )}
      {command.uncertain && (
        <Button disabled={command.pending} onClick={submit}>
          Retry same save
        </Button>
      )}
      {saved && (
        <Notice tone="success">
          {config.singular} {id ? 'updated' : 'created'} successfully.{' '}
          <a
            className="janso-link"
            href={profileLink(root + '/' + saved.id, back)}
          >
            View{' '}
            {config.resource === 'manufacturing-routes'
              ? 'route'
              : config.resource === 'manufacturing-operations'
                ? 'operation'
                : 'profile'}{' '}
            and revisions
          </a>
        </Notice>
      )}
      {notice && <Notice>{notice}</Notice>}
      {record.loading ||
      history.loading ||
      (!initialized && !record.failure && !history.failure) ? (
        <p role="status">Loading profile...</p>
      ) : (
        !record.failure &&
        !history.failure &&
        !saved && (
          <FormLayout>
            <form
              ref={form}
              noValidate
              onSubmit={(event) => {
                event.preventDefault();
                void submit();
              }}
            >
              <Card>
                <CardBody>
                  <div className="janso-form-grid">
                    {!complete && (
                      <Notice tone="warning">
                        Required fields or edit access are unavailable. Check
                        your company permissions before saving.
                      </Notice>
                    )}
                    {codeLocked && (
                      <Notice>
                        The code is fixed because this profile already has
                        revisions. You can update its name.
                      </Notice>
                    )}
                    {fields
                      .filter((field) => ['code', 'name'].includes(field.key))
                      .map((field) => (
                        <ProfileField
                          key={field.key}
                          company={company}
                          field={field}
                          value={values[field.key]}
                          disabled={command.pending || command.uncertain}
                          error={errors[field.key]}
                          access={access}
                          onChange={(value) => change(field.key, value)}
                        />
                      ))}
                  </div>
                </CardBody>
                <FormActions cancel={{ href: back, onClick: guard.leave }}>
                  <Button
                    type="submit"
                    loading={command.pending}
                    disabled={!complete || command.blocked}
                  >
                    {' '}
                    {id
                      ? 'Save changes'
                      : config.resource.startsWith('manufacturing-')
                        ? 'Create ' + config.singular
                        : 'Create profile'}
                  </Button>
                </FormActions>
              </Card>
            </form>
          </FormLayout>
        )
      )}
      <ConfirmDialog
        open={reload}
        title="Reload and discard this draft?"
        confirmLabel="Reload"
        onCancel={() => setReload(false)}
        onConfirm={() => {
          setReload(false);
          command.clear();
          record.refresh();
          history.refresh();
        }}
      >
        Your unsaved values will be replaced with the latest saved profile.
      </ConfirmDialog>
      {guard.confirmation}
    </div>
  );
}
