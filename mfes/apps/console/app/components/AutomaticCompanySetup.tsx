'use client';
import { useEffect, useRef, useState } from 'react';
import { Button, Card, CardBody, CardHeader, Notice, PreparationProgress } from '@janso/ui';
import { companyCall, companyFailure } from '../lib/company-api';
import type { components } from '@janso/api-client/identity';

type Status = components['schemas']['CompanySetupStatus'];
const labels: Record<string, string> = { features: 'Capabilities', catalog: 'Products and pricing setup', vouchers: 'Voucher types', chart: 'Account chart', books: 'Books', calendar: 'Financial year', opening: 'Opening balances', reports: 'Report preparation' };
export function AutomaticCompanySetup({ company, canRetry, onComplete, openingFinalized, notifyInitialComplete = false, autoScroll = false }: { company: string; canRetry: boolean; onComplete?: () => void; openingFinalized?: boolean; notifyInitialComplete?: boolean; autoScroll?: boolean }) {
  const [status, setStatus] = useState<Status | null>(null), [failure, setFailure] = useState('');
  const [revision, setRevision] = useState(0), [retrying, setRetrying] = useState(false);
  const [checking, setChecking] = useState(true);
  const preparingCompany = useRef<string | null>(null);
  const completion = useRef(onComplete); completion.current = onComplete;
  useEffect(() => {
    const controller = new AbortController(); let timer: ReturnType<typeof setTimeout> | undefined;
    setStatus(null); setFailure(''); setChecking(true);
    if (notifyInitialComplete) preparingCompany.current = company;
    async function poll() {
      try {
        const value = await companyCall<Status>('identity', `/v1/companies/${company}/setup`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        if (value.company_id !== company || !Array.isArray(value.steps)) throw new Error('Invalid setup response');
        setStatus(value); setFailure(''); setChecking(false);
        if (value.status === 'COMPLETE') {
          if (preparingCompany.current === company) { preparingCompany.current = null; completion.current?.(); }
          return;
        }
        // A failed run can be resumed from another tab or by an administrator.
        // Keep reading its evidence so this panel cannot retain an old failure.
        preparingCompany.current = company;
      } catch (error) {
        if (controller.signal.aborted) return;
        const failed = companyFailure(error);
        setChecking(false);
        if ([401, 403, 404].includes(failed.status)) {
          setStatus(null);
          setFailure(failed.status === 401 ? 'Sign in again to check company setup.'
            : failed.status === 403 ? 'Your access does not permit checking company setup.' : '');
          return;
        }
        setFailure('Setup status is temporarily unavailable. Checking again automatically.');
      }
      timer = setTimeout(poll, 5000);
    }
    void poll(); return () => { controller.abort(); clearTimeout(timer); };
  }, [company, revision, notifyInitialComplete]);
  if (!status || status.company_id !== company) return failure ? <Notice tone="warning">{failure}</Notice>
    : checking ? <PreparationProgress autoScroll={autoScroll} label="Company setup progress" title="Checking company setup…" detail="Your company is saved. Checking the latest preparation steps." /> : null;
  const readyCount = status.steps.filter(step => step.status === 'READY' || step.key === 'opening' && openingFinalized).length;
  const currentStep = status.steps.find(step => step.status === 'RUNNING');
  const openingNeeded = !openingFinalized && status.steps.some(step => step.status === 'AWAITING_OPENING');
  const completionMessage = !openingNeeded ? 'Automatic setup is complete.'
    : openingFinalized === false ? 'Automatic preparation is complete. Opening balances still need your decision.'
    : 'Automatic preparation is complete. Opening balances were deferred during setup.';
  const deferredOpeningLabel = openingFinalized === false ? 'Your opening-balance choice is still needed' : 'Deferred during setup';
  return <Card><CardHeader title="Automatic company setup" /><CardBody>
    {!failure && ['PENDING', 'RUNNING'].includes(status.status) && <PreparationProgress autoScroll={autoScroll} label="Company setup progress"
      title={currentStep ? `Preparing ${(labels[currentStep.key] ?? 'company setup').toLowerCase()}` : 'Preparing your company'}
      detail={status.steps.length ? `${readyCount} of ${status.steps.length} setup steps ready. You can open your company while setup continues.` : 'Your company is saved. Setup continues automatically in the background.'} />}
    <Notice tone={status.status === 'COMPLETE' ? 'success' : status.status === 'NEEDS_ACTION' ? 'warning' : 'info'}>
      {status.status === 'COMPLETE' ? completionMessage
        : status.status === 'NEEDS_ACTION' ? 'Company saved. Some setup steps need your attention.'
        : status.status === 'RETRY_WAIT' ? 'Company saved. Setup is waiting and will retry automatically.'
        : 'Company saved. Setup is still running in the background.'}
    </Notice>
    {status.status !== 'COMPLETE' && status.status !== 'NEEDS_ACTION' && Date.now() - Date.parse(status.updated_at) > 180000 && <Notice tone="warning">Company preparation is taking longer than expected. An administrator should check the background services; your saved setup request is retained.</Notice>}
    <ul>{status.steps.map(step => <li key={step.key}>{labels[step.key] ?? 'Setup'}: {step.key === 'opening' && openingFinalized ? 'Finalised' : step.status === 'READY' ? 'Ready' : step.status === 'AWAITING_OPENING' ? deferredOpeningLabel : step.status === 'NEEDS_ACTION' ? 'Needs review' : step.status === 'PENDING' ? 'Waiting' : 'Preparing automatically'}</li>)}</ul>
    {status.steps.some(step => step.key === 'catalog' && step.status === 'NEEDS_ACTION' && step.failure_code === 'PRODUCT_CONFIGURATION_REVIEW_REQUIRED') && <Notice tone="warning">Product configuration needs review. Existing drafts are preserved. <a className="janso-link" href="/products/configuration">Review product configuration</a>, then complete remaining setup.</Notice>}
    {status.steps.some(step => step.key === 'catalog' && step.status === 'NEEDS_ACTION' && step.failure_code === 'PRODUCT_PRICING_POLICY_REVIEW_REQUIRED') && <Notice tone="warning">A current company pricing policy is needed. Ask an administrator to review the existing pricing setup, then complete remaining setup.</Notice>}
    {failure && <Notice tone="warning">{failure}</Notice>}
    {canRetry && ['NEEDS_ACTION', 'RETRY_WAIT'].includes(status.status) && <><p>Finishes missing setup steps without changing your opening-balance choice.</p><Button type="button" loading={retrying} loadingLabel="Starting setup…" onClick={async () => {
      setRetrying(true); setFailure('');
      try {
        await companyCall('identity', `/v1/companies/${company}/setup/retry`, { method: 'POST' });
        preparingCompany.current = company; setRevision(v => v + 1);
      }
      catch (error) { setFailure(companyFailure(error).message); }
      finally { setRetrying(false); }
    }}>{retrying ? 'Starting setup…' : 'Complete remaining setup'}</Button></>}
  </CardBody></Card>;
}
