import { CatalogMasterPage } from '../../../components/CatalogMasterPage';
export default async function Page({ params, searchParams }: { params: Promise<{ resource: string; record?: string[] }>; searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const route = await params;
  return CatalogMasterPage({ ...route, query: await searchParams });
}
