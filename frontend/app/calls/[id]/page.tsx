import { notFound } from "next/navigation";
import { api } from "../../../lib/api";
import { CallWorkspace } from "../../../components/call-workspace";

export default async function CallDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const call = await api.call(id);
  if (!call) notFound();
  return <CallWorkspace call={call} />;
}
