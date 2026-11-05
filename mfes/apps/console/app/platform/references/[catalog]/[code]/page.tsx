import { ReferenceRecordPage } from '../../ReferenceRecordPage';
export default function ViewReferencePage(props: { params: Promise<{ catalog: string; code: string }>; searchParams: Promise<{ returnTo?: string; action?: string }> }) { return ReferenceRecordPage({ ...props, mode: 'view' }); }
