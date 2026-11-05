import { PartyImportPage } from '../../../components/PartyImportPage';
export default async function ImportSuppliers({
  searchParams = Promise.resolve({}),
}: {
  searchParams?: Promise<{ job?: string; view?: string; returnTo?: string }>;
}) {
  return <PartyImportPage supplier query={await searchParams} />;
}
