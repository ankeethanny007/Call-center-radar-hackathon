import { CallDirectory } from "../../components/call-directory";
import { ProcessNewCalls } from "../../components/process-new-calls";
import { PageHeader } from "../../components/ui";
import { api } from "../../lib/api";

export default async function CallsPage() {
  const calls = await api.calls();
  return <><PageHeader eyebrow="Call archive" title="Calls" description="Search, filter, and open persisted recordings and transcripts." /><ProcessNewCalls /><CallDirectory calls={calls} /></>;
}
