import type {components} from '@janso/api-client/reports';

type Schemas=components['schemas'];
export type TrialNode=Schemas['TrialNode'];
export type TrialRow=Schemas['TrialHierarchyRow'];
export type TrialPage=Schemas['TrialHierarchyPage'];
export type TrialPresentation=Schemas['TrialPresentation'];
export type TrialLevel=TrialPresentation['level'];
export type TrialMode='default'|'detailed';
export const trialAmounts=['opening_debit','opening_credit','period_debit','period_credit','closing_debit','closing_credit'] as const;
export const nodeKey=/^(?:head|group|account):[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/;

export function trialExpanded(node:TrialNode,settings:TrialPresentation):boolean {
  if(!node.child_count||settings.collapsed?.includes(node.node_key))return false;
  if(settings.expanded?.includes(node.node_key))return true;
  return settings.level==='LEDGERS'||settings.level==='ALL_GROUPS'&&node.group_child_count>0
    ||settings.level==='GROUPS'&&node.row_kind==='HEAD';
}

export const initialTrialPresentation:TrialPresentation={period:'CURRENT',hierarchy:'CURRENT',level:'GROUPS',expanded:[],collapsed:[],show_zero:false};
export type TrialBranch={page:TrialPage;cursors:(string|null)[];position:number;offset:number};
export type TrialSaved={run:string;mode:TrialMode;settings:TrialPresentation;scroll:number;cursors:Record<string,{values:(string|null)[];position:number;offset?:number}>};

/** Restore only bounded identifiers and presentation choices; no financial values enter storage. */
export function restoreTrial(raw:string|null,run:string):TrialSaved|null {
  if(!raw||raw.length>180_000)return null;
  try {
    const value=JSON.parse(raw) as TrialSaved,s=value.settings;
    if(value.run!==run||!['default','detailed'].includes(value.mode)||!s
      ||!['HEADS','GROUPS','ALL_GROUPS','LEDGERS'].includes(s.level??'')
      ||!['CURRENT','COMPARATIVE'].includes(s.period??'')||typeof s.show_zero!=='boolean'
      ||!Array.isArray(s.expanded)||!Array.isArray(s.collapsed)
      ||s.expanded.length+s.collapsed.length>2000||[...s.expanded,...s.collapsed].some(key=>!nodeKey.test(key))
      ||!Number.isFinite(value.scroll)||value.scroll<0)return null;
    const cursors=Object.entries(value.cursors??{}).slice(0,20).filter(([key,entry])=>(key==='root'||nodeKey.test(key))
      &&Array.isArray(entry.values)&&entry.values.length<=100&&Number.isInteger(entry.position)
      &&entry.position>=0&&entry.position<entry.values.length
      &&(entry.offset===undefined||Number.isInteger(entry.offset)&&entry.offset>=0&&entry.offset<=100_000)
      &&entry.values.every(cursor=>cursor===null||typeof cursor==='string'&&cursor.length<=4096));
    return {...value,settings:{...s,hierarchy:'CURRENT'},cursors:Object.fromEntries(cursors)};
  }catch{return null;}
}
