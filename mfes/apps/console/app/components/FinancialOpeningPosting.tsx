'use client';
import { useEffect, useState } from 'react';
import { Button, Card, CardBody, Notice, SectionHeader } from '@janso/ui';
import type { Access, Workspace } from '../lib/financial-opening';
import { OpeningJournal } from './FinancialOpeningJournal';
import { FinancialOpeningRecovery } from './FinancialOpeningRecovery';

export function FinancialOpeningPosting({ company, workspace, access, blocked = false, onDirty, onChanged }: {
  company: string; workspace: Workspace; access: Access; blocked?: boolean;
  onDirty: (dirty: boolean) => void; onChanged: () => void;
}) {
  const [selected, setSelected] = useState<string | null>(null), [postingBusy, setPostingBusy] = useState(false),
    [recoveryBusy, setRecoveryBusy] = useState(false), [revision, setRevision] = useState(0);
  const locked = postingBusy || recoveryBusy;
  useEffect(() => { onDirty(locked); return () => onDirty(false); }, [locked, onDirty]);
  const changed = () => { setRevision(value => value + 1); onChanged(); };
  return <Card><CardBody><div className="janso-flow"><SectionHeader title="Native opening journals" description={workspace.status === 'FINALIZED' ? 'All opening journals are posted. View their details here; corrections retain the original facts and require reversal.' : 'Review and explicitly post each journal. Corrections retain the original facts and use native cancellation or reversal.'} />
    {!workspace.journal_ids.length && <Notice>No journals are prepared yet.</Notice>}
    <div className="janso-form-actions">{workspace.journal_ids.map((id, i) => <Button key={id} disabled={locked} variant={selected === id ? 'primary' : 'ghost'} onClick={() => setSelected(id)}>Review journal {i + 1}</Button>)}</div>
    {selected && workspace.journal_ids.includes(selected) && <div className="janso-flow" key={selected}>
      <OpeningJournal company={company} id={selected} access={{ ...access, post: access.post && access.manage && !blocked && !recoveryBusy }} onDirty={setPostingBusy} onChanged={changed} revision={revision} />
      <FinancialOpeningRecovery company={company} batch={workspace.id} journal={selected} date={workspace.posting_date} access={access} blocked={blocked} disabled={postingBusy} onDirty={setRecoveryBusy} onChanged={changed} revision={revision} />
    </div>}
  </div></CardBody></Card>;
}
