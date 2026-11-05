import { AccountingConfigurationPage } from '../../components/AccountingConfigurationPage';

export default async function Page({ params, searchParams }: { params: Promise<{ segments?: string[] }>; searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  return AccountingConfigurationPage({ segments: (await params).segments, query: await searchParams });
}
