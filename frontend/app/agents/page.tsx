import { AgentDirectory } from "../../components/agent-directory";
import { PageHeader } from "../../components/ui";
import { api } from "../../lib/api";

export default async function AgentsPage() {
  const agents = await api.agents();
  return <><PageHeader eyebrow="Agent analytics" title="Agents" description="Operational metrics are calculated from persisted call data. Identity is shown only when the source metadata explicitly supplies it." /><AgentDirectory agents={agents} /></>;
}
