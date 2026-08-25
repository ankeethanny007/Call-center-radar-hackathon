import { CustomerDirectory } from "../../components/customer-directory";
import { PageHeader } from "../../components/ui";
import { api } from "../../lib/api";

export default async function CustomersPage() {
  const customers = await api.customers();
  return <><PageHeader eyebrow="Customer intelligence" title="Customers" description="Bring repeat contact, unresolved issues, and individual call history into one evidence-backed view." /><CustomerDirectory customers={customers} /></>;
}
