import { ProductConfigurationPage } from '../../../components/ProductConfigurationPage';
export default async function Page({ params, searchParams }: { params: Promise<{ segments?: string[] }>; searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  return ProductConfigurationPage({ segments: (await params).segments, query: await searchParams });
}
