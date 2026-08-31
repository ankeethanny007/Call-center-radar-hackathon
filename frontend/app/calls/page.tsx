import { CallDirectory, type CallDirectoryFilters } from "../../components/call-directory";
import { ProcessNewCalls } from "../../components/process-new-calls";
import { PageHeader } from "../../components/ui";
import { api } from "../../lib/api";

function value(parameter: string | string[] | undefined): string | undefined {
  return Array.isArray(parameter) ? parameter[0] : parameter;
}

export default async function CallsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const parameters = await searchParams;
  const initialFilters: CallDirectoryFilters = {
    query: value(parameters.query),
    status: value(parameters.status),
    resolution: value(parameters.resolution),
    minimumScore: value(parameters.minimumScore),
  };
  const calls = await api.calls();
  return <><PageHeader eyebrow="Call archive" title="Calls" description="Search, filter, and open persisted recordings and transcripts." action={<ProcessNewCalls />} /><CallDirectory calls={calls} initialFilters={initialFilters} /></>;
}
