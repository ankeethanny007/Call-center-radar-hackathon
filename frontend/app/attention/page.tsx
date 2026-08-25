import { AttentionQueue } from "../../components/attention-queue";
import { PageHeader } from "../../components/ui";
import { api } from "../../lib/api";

export default async function AttentionPage() {
  const calls = await api.attention();
  return <><PageHeader eyebrow="Manager workspace" title="Attention queue" description="Prioritized by transparent, evidence-backed signals. Open a call to inspect every contribution and seek directly to its proof." /><AttentionQueue calls={calls} /></>;
}
