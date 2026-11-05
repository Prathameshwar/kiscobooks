import { PartyImportPage } from '../../../components/PartyImportPage';
export default async function ImportParties({
  searchParams = Promise.resolve({}),
}: {
  searchParams?: Promise<{ job?: string; view?: string; returnTo?: string }>;
}) {
  return <PartyImportPage query={await searchParams} />;
}
