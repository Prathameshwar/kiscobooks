import { TaxPage } from '../../components/TaxPage';
export default async function Page({ params, searchParams }: { params: Promise<{ segments?: string[] }>; searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const { segments } = await params; return <TaxPage segments={segments} query={await searchParams} />;
}
