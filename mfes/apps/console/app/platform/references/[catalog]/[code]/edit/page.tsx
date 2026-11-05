import { ReferenceRecordPage } from '../../../ReferenceRecordPage';
export default function EditReferencePage(props: { params: Promise<{ catalog: string; code: string }>; searchParams: Promise<{ returnTo?: string }> }) { return ReferenceRecordPage({ ...props, mode: 'edit' }); }
