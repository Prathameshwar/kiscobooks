import { OrganisationMasterPage } from '../../components/OrganisationMasterPage';
export default async function UserGroupsPage(props: { params: Promise<{ segments?: string[] }>; searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  return OrganisationMasterPage({ ...props, resource: 'user-groups' });
}
