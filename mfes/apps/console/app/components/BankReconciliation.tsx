'use client';
import {useRef,useState} from 'react';
import {Button,SearchSelect,Select,TextField,useFormatters} from '@janso/ui';
import type {components} from '@janso/api-client/accounting';
import {productFieldRequest as request} from '../lib/product-fields';
import {lookup} from '../lib/voucher-fields';

type Mapping=components['schemas']['MappingView'];
type Import=components['schemas']['ImportView'];
type Entry=components['schemas']['EntryView'];
type Candidate=components['schemas']['CandidateView'];
type Session=components['schemas']['SessionView'];
type Policy=components['schemas']['PolicyView'];
type Proposal=components['schemas']['ProposalView'];
type MatchAssessment=components['schemas']['MatchAssessment'];
type MatchPart={statement_entry_id:string;instrument_id:string;amount:string};

export function BankReconciliation({company,permissions}:{company:string;permissions:readonly string[]}){
  const base='/v1/companies/'+company+'/bank-reconciliation',format=useFormatters();
  const [account,setAccount]=useState(''),[mapping,setMapping]=useState<Mapping|null>(null);
  const [policy,setPolicy]=useState<Policy|null>(null),[mode,setMode]=useState('SUGGEST_AND_REVIEW');
  const [separateReviewer,setSeparateReviewer]=useState(false);
  const [matchWindow,setMatchWindow]=useState('30');
  const [currency,setCurrency]=useState('INR');
  const [columns,setColumns]=useState({date:'date',debit:'debit',credit:'credit',reference:'ref',description:'description',transactionId:'transaction_id',balance:'',account:'',accountValue:'',currency:''});
  const [file,setFile]=useState<File|null>(null),[start,setStart]=useState(''),[end,setEnd]=useState('');
  const [opening,setOpening]=useState(''),[closing,setClosing]=useState(''),[reason,setReason]=useState('');
  const [batch,setBatch]=useState<Import|null>(null),[rows,setRows]=useState<Entry[]>([]),[session,setSession]=useState<Session|null>(null);
  const [sessions,setSessions]=useState<Session[]>([]);
  const [candidateRow,setCandidateRow]=useState(''),[candidates,setCandidates]=useState<Candidate[]>([]);
  const [instrument,setInstrument]=useState(''),[amount,setAmount]=useState('');
  const [matchParts,setMatchParts]=useState<MatchPart[]>([]),[assessment,setAssessment]=useState<MatchAssessment|null>(null);
  const [proposalKind,setProposalKind]=useState('PAYMENT'),[proposalReason,setProposalReason]=useState('');
  const [proposals,setProposals]=useState<Proposal[]>([]),[selectedProposal,setSelectedProposal]=useState(''),[voucherId,setVoucherId]=useState('');
  const [openingInstrument,setOpeningInstrument]=useState(''),[openingAmount,setOpeningAmount]=useState('');
  const [rowAfter,setRowAfter]=useState<string|null>(null),[hasMoreRows,setHasMoreRows]=useState(false);
  const [busy,setBusy]=useState(false),[message,setMessage]=useState('');
  const retry=useRef<{payload:string;key:string}|null>(null);
  const matchGroup=useRef<string|null>(null);
  if(!permissions.includes('accounting.bank.read')||!permissions.includes('accounting.statement.read'))return null;
  const bankManage=permissions.includes('accounting.bank.manage');
  const canImport=bankManage&&permissions.includes('accounting.statement.import');
  const canReview=bankManage&&permissions.includes('accounting.statement.review');
  const canMatch=bankManage&&permissions.includes('accounting.bank_match.manage');
  const canFinalize=bankManage&&permissions.includes('accounting.bank_session.finalize');
  async function act(work:()=>Promise<void>){setBusy(true);setMessage('');try{await work();}catch(error){setMessage(error instanceof Error?error.message:'Unable to review bank statement');}finally{setBusy(false);}}
  async function post<T>(path:string,body:unknown){const payload=JSON.stringify({path,body});if(retry.current?.payload!==payload)retry.current={payload,key:crypto.randomUUID()};const result=await request<T>('accounting','POST',base+path,body,retry.current.key);retry.current=null;return result;}
  async function loadRows(identity:string,after?:string){const page=await request<Entry[]>('accounting','GET',base+'/imports/'+identity+'/rows?limit=200'+(after?'&after='+encodeURIComponent(after):''));setRows(previous=>after?[...previous,...page]:page);setRowAfter(page.at(-1)?.id??null);setHasMoreRows(page.length===200);}
  async function loadProposals(){if(account)setProposals(await request<Proposal[]>('accounting','GET',base+'/proposals?account_id='+encodeURIComponent(account)+'&limit=200'));}
  async function fileBase64(selected:File){if(selected.size>2*1024*1024)throw new Error('CSV exceeds the 2 MB statement limit');return new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onerror=()=>reject(new Error('Unable to read CSV'));reader.onload=()=>resolve(String(reader.result).split(',')[1]??'');reader.readAsDataURL(selected);});}
  return <section aria-label="Bank reconciliation"><h2>Bank reconciliation</h2>
    <SearchSelect label="Bank ledger" value={account||null} loadOptions={lookup(company,'accounts')} minQueryLength={0} disabled={busy} onChange={value=>{setAccount(value??'');setMapping(null);setPolicy(null);setBatch(null);setRows([]);setProposals([]);setSession(null);}}/>
    {canReview&&account&&<><Select label="Bank matching mode" value={mode} options={[{value:'MANUAL_ONLY',label:'Manual only'},{value:'SUGGEST_AND_REVIEW',label:'Suggest, then review'}]} disabled={busy} onChange={setMode}/><TextField label="Candidate date window (days)" type="number" value={matchWindow} min={0} max={90} required disabled={busy} onChange={event=>setMatchWindow(event.target.value)}/><Select label="Separate reviewer required" value={separateReviewer?'yes':'no'} options={[{value:'no',label:'No'},{value:'yes',label:'Yes'}]} disabled={busy} onChange={value=>setSeparateReviewer(value==='yes')}/><Button disabled={busy||!/^\d+$/.test(matchWindow)||Number(matchWindow)>90} onClick={()=>void act(async()=>{setPolicy(await post<Policy>('/policies',{account_id:account,mode,match_window_days:Number(matchWindow),require_separate_reviewer:separateReviewer}));setMessage('Bank reconciliation policy published.');})}>Publish review policy</Button></>}
    {policy&&<p>Policy revision {policy.revision}: {policy.mode}</p>}
    {canImport&&account&&<><TextField label="Bank account currency" value={currency} pattern="[A-Z]{3}" maxLength={3} required disabled={busy} onChange={event=>setCurrency(event.target.value.toUpperCase())}/>
      {([['date','Date column'],['debit','Debit column'],['credit','Credit column'],['reference','Reference column'],['description','Description column'],['transactionId','Transaction ID column'],['balance','Running balance column'],['currency','Currency column'],['account','Bank account column'],['accountValue','Expected bank account value']] as const).map(([key,label])=><TextField key={key} label={label} value={columns[key]} disabled={busy} onChange={event=>setColumns(previous=>({...previous,[key]:event.target.value}))}/>)}
      <Button disabled={busy||currency.length!==3} onClick={()=>void act(async()=>{const created=await post<Mapping>('/mappings',{account_id:account,currency,date_column:columns.date,debit_column:columns.debit,credit_column:columns.credit,reference_column:columns.reference,description_column:columns.description,transaction_id_column:columns.transactionId||null,balance_column:columns.balance||null,currency_column:columns.currency||null,account_column:columns.account||null,account_value:columns.accountValue||null});setMapping(created);setMessage('CSV mapping revision '+created.revision+' published.');})}>Publish CSV mapping</Button></>}
    {mapping&&<p>Mapping revision {mapping.revision} for {mapping.currency}.</p>}
    {canImport&&mapping&&<form onSubmit={event=>{event.preventDefault();void act(async()=>{if(!file)throw new Error('Choose a CSV file');const imported=await post<Import>('/imports',{mapping_id:mapping.id,content_base64:await fileBase64(file),period_from:start,period_to:end,opening_balance:opening,closing_balance:closing});setBatch(imported);await loadRows(imported.id);setMessage('Statement preview saved for review.');});}}>
      <label>Bank CSV <input type="file" accept=".csv,text/csv" disabled={busy} onChange={event=>setFile(event.target.files?.[0]??null)}/></label>
      <TextField label="Statement from" type="date" value={start} required disabled={busy} onChange={event=>setStart(event.target.value)}/>
      <TextField label="Statement to" type="date" value={end} required disabled={busy} onChange={event=>setEnd(event.target.value)}/>
      <TextField label="Opening bank balance" value={opening} required inputMode="decimal" disabled={busy} onChange={event=>setOpening(event.target.value)}/>
      <TextField label="Closing bank balance" value={closing} required inputMode="decimal" disabled={busy} onChange={event=>setClosing(event.target.value)}/>
      <Button type="submit" disabled={busy||!file}>Preview CSV statement</Button>
    </form>}
    {batch&&<><p>Import {batch.status}: {batch.row_count} rows, file {batch.file_sha256}.</p>
      <Button disabled={busy} onClick={()=>void act(()=>loadRows(batch.id))}>Refresh statement rows</Button>
      <ol>{rows.map(row=><li key={row.id}>{row.transaction_date?format.date(row.transaction_date):''} {row.side} {row.amount?format.money(row.amount,{display:'none'}):''} {row.currency} — {row.review_status}
        {row.review_status==='AMBIGUOUS'&&canReview&&<><Button disabled={busy} onClick={()=>void act(async()=>{await post('/rows/'+row.id+'/duplicate-decision',{disposition:'ACCEPTED',reason:'Reviewed as separate transaction'});await loadRows(batch.id);})}>Keep separate row</Button><Button disabled={busy} onClick={()=>void act(async()=>{await post('/rows/'+row.id+'/duplicate-decision',{disposition:'EXISTING',reason:'Reviewed as duplicate export'});await loadRows(batch.id);})}>Already imported</Button></>}
        {batch.status==='COMMITTED'&&row.review_status!=='EXISTING'&&<Button disabled={busy} onClick={()=>void act(async()=>{setCandidates(await request<Candidate[]>('accounting','GET',base+'/rows/'+row.id+'/candidates'));setCandidateRow(row.id);setAmount(row.amount??'');})}>Find book matches</Button>}
      </li>)}</ol>
      {hasMoreRows&&rowAfter&&<Button disabled={busy} onClick={()=>void act(()=>loadRows(batch.id,rowAfter))}>Load more statement rows</Button>}
      {canReview&&batch.status==='PREVIEW'&&<Button disabled={busy||rows.some(row=>row.review_status==='AMBIGUOUS')} onClick={()=>void act(async()=>{const result=await post<Import>('/imports/'+batch.id+'/commit',{reason:'Reviewed statement rows and totals'});setBatch(result);setMessage('Statement evidence committed.');})}>Commit reviewed import</Button>}
      {canReview&&batch.status==='PREVIEW'&&<Button disabled={busy} onClick={()=>void act(async()=>{setBatch(await post<Import>('/imports/'+batch.id+'/reject',{reason:'Reviewed statement preview rejected'}));setMessage('Statement preview rejected; no journal was posted.');})}>Reject statement preview</Button>}
    </>}
    {candidateRow&&<><p>Candidate book instruments for row {candidateRow}</p><ul>{candidates.map(row=><li key={row.instrument_id}><Button disabled={busy} onClick={()=>{setInstrument(row.instrument_id);setAmount(row.remaining_statement);}}>{row.reason}: {row.instrument_id} ({row.remaining_book})</Button></li>)}</ul>
      {canMatch&&<><TextField label="Instrument ID" value={instrument} disabled={busy} onChange={event=>setInstrument(event.target.value)}/><TextField label="Match amount" value={amount} inputMode="decimal" disabled={busy} onChange={event=>setAmount(event.target.value)}/><Button disabled={busy||!instrument||!amount} onClick={()=>{setMatchParts(previous=>[...previous,{statement_entry_id:candidateRow,instrument_id:instrument,amount}]);setAssessment(null);setInstrument('');setAmount('');}}>Add allocation to group</Button></>}
    </>}
    {canMatch&&matchParts.length>0&&<><h3>Reviewed allocation group</h3><ol>{matchParts.map((part,index)=><li key={index}>{part.statement_entry_id} → {part.instrument_id}: {part.amount} <Button disabled={busy} onClick={()=>{setMatchParts(previous=>previous.filter((_,i)=>i!==index));setAssessment(null);}}>Remove</Button></li>)}</ol><Button disabled={busy} onClick={()=>void act(async()=>{matchGroup.current??=crypto.randomUUID();setAssessment(await post<MatchAssessment>('/matches/preview',{group_id:matchGroup.current,parts:matchParts,reason:'Reviewed statement-to-book match'}));})}>Preview exact residuals</Button>{assessment&&<pre>{JSON.stringify(assessment,null,2)}</pre>}<Button disabled={busy||!assessment} onClick={()=>void act(async()=>{matchGroup.current??=crypto.randomUUID();await post('/matches',{group_id:matchGroup.current,parts:matchParts,reason:'Reviewed statement-to-book match'});matchGroup.current=null;setAssessment(null);setMatchParts([]);setCandidateRow('');setCandidates([]);setMessage('Bank allocation group recorded; no journal was posted.');})}>Commit reviewed allocations</Button></>}
    {canReview&&candidateRow&&batch?.status==='COMMITTED'&&<><Select label="Proposed voucher type" value={proposalKind} options={['PAYMENT','RECEIPT','CONTRA','JOURNAL'].map(value=>({value,label:value}))} disabled={busy} onChange={setProposalKind}/><TextField label="Adjustment reason" value={proposalReason} maxLength={500} disabled={busy} onChange={event=>setProposalReason(event.target.value)}/><Button disabled={busy||proposalReason.trim().length<3} onClick={()=>void act(async()=>{await post('/proposals',{statement_entry_id:candidateRow,kind:proposalKind,reason:proposalReason});await loadProposals();setMessage('Adjustment proposed. Post the voucher through the ordinary workflow, then match its bank instrument.');})}>Prepare bank adjustment</Button></>}
    {canReview&&account&&<><Button disabled={busy} onClick={()=>void act(loadProposals)}>Load adjustment proposals</Button><ul>{proposals.map(row=><li key={row.id}>{row.kind} {row.amount} {row.currency}: {row.status} ({row.statement_entry_id}) {row.status==='PREPARED'&&<Button disabled={busy} onClick={()=>setSelectedProposal(row.id)}>Review proposal</Button>}</li>)}</ul>{selectedProposal&&<><TextField label="Posted voucher ID" value={voucherId} disabled={busy} onChange={event=>setVoucherId(event.target.value)}/><Button disabled={busy||!voucherId} onClick={()=>void act(async()=>{await post('/proposals/'+selectedProposal+'/resolve',{voucher_id:voucherId,reason:'Posted voucher and statement match verified'});setSelectedProposal('');setVoucherId('');await loadProposals();})}>Resolve after voucher match</Button><Button disabled={busy} onClick={()=>void act(async()=>{await post('/proposals/'+selectedProposal+'/reject',{reason:'Reviewed bank exception rejected'});setSelectedProposal('');await loadProposals();})}>Reject proposal</Button></>}</>}
    {canReview&&account&&<><h3>Opening uncleared instrument</h3><TextField label="Existing instrument ID" value={openingInstrument} disabled={busy} onChange={event=>setOpeningInstrument(event.target.value)}/><TextField label="Uncleared amount" value={openingAmount} inputMode="decimal" disabled={busy} onChange={event=>setOpeningAmount(event.target.value)}/><Button disabled={busy||!openingInstrument||!openingAmount||!start} onClick={()=>void act(async()=>{await post('/opening-items',{instrument_id:openingInstrument,cutoff_date:start,amount:openingAmount,reason:'Reviewed opening bank reconciliation item'});setMessage('Opening uncleared item recorded; no journal was posted.');})}>Record opening item</Button></>}
    {canReview&&batch?.status==='COMMITTED'&&<><TextField label="Session reason" value={reason} maxLength={500} disabled={busy} onChange={event=>setReason(event.target.value)}/><Button disabled={busy||reason.trim().length<3} onClick={()=>void act(async()=>{const result=await post<Session>('/sessions',{account_id:account,period_from:start,period_to:end,opening_balance:opening,closing_balance:closing,reason});setSession(result);})}>Review session controls</Button></>}
    {account&&<Button disabled={busy} onClick={()=>void act(async()=>{setSessions(await request<Session[]>('accounting','GET',base+'/sessions?account_id='+encodeURIComponent(account)+'&limit=200'));})}>Load session history</Button>}
    {sessions.length>0&&<ul>{sessions.map(row=><li key={row.id}><Button disabled={busy} onClick={()=>setSession(row)}>{row.period_from} to {row.period_to}: {row.status}, generation {row.generation}</Button></li>)}</ul>}
    {session&&<><p>Session {session.status}; balance agrees: {String(session.snapshot?.balance_agrees)}; rows covered: {String(session.snapshot?.rows_covered)}.</p><pre>{JSON.stringify(session.snapshot,null,2)}</pre>{canFinalize&&session.status==='DRAFT'&&<Button disabled={busy||session.snapshot?.balance_agrees!==true||session.snapshot?.rows_covered!==true} onClick={()=>void act(async()=>{setSession(await post<Session>('/sessions/'+session.id+'/finalize',{reason:'Reviewed bank statement and book coverage'}));setMessage('Bank session finalized.');})}>Finalize reconciliation</Button>}{canFinalize&&session.status==='FINALIZED'&&<Button disabled={busy} onClick={()=>void act(async()=>{setSession(await post<Session>('/sessions/'+session.id+'/amend',{reason:'Reopen reviewed bank evidence for correction'}));setMessage('Session amended; create a fresh review generation after corrections.');})}>Amend finalized session</Button>}</>}
    {message&&<p role="status">{message}</p>}
  </section>;
}
