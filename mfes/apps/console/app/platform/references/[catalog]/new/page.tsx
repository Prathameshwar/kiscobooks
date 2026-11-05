import { ReferenceRecordPage } from '../../ReferenceRecordPage';
export default function NewReferencePage(props: { params: Promise<{ catalog: string }>; searchParams: Promise<{ returnTo?: string }> }) { return ReferenceRecordPage({ ...props, mode: 'new' }); }
