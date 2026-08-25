"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { CustomerRef } from "../lib/types";
import { displayName, formatDate, humanize } from "../lib/format";
import { Icon } from "./icons";
import { EmptyState } from "./ui";

type Sort = "calls" | "recent" | "name";

export function CustomerDirectory({ customers }: { customers: CustomerRef[] }) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<Sort>("calls");
  const visible = useMemo(() => customers
    .filter((customer) => `${customer.id} ${customer.displayName || ""}`.toLowerCase().includes(query.trim().toLowerCase()))
    .sort((left, right) => {
      if (sort === "name") return displayName(left.id, left.displayName).localeCompare(displayName(right.id, right.displayName));
      if (sort === "recent") return new Date(right.lastContactAt || 0).getTime() - new Date(left.lastContactAt || 0).getTime();
      return (right.callCount || 0) - (left.callCount || 0);
    }), [customers, query, sort]);
  return <>
    <div className="filter-toolbar compact-toolbar">
      <label className="search-input"><Icon name="search" size={18} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search customer name or ID" aria-label="Search customers" /></label>
      <label className="select-input">Sort <select value={sort} onChange={(event) => setSort(event.target.value as Sort)}><option value="calls">Most calls</option><option value="recent">Most recent</option><option value="name">Name</option></select></label>
    </div>
    <p className="result-count">{visible.length} customer{visible.length === 1 ? "" : "s"}</p>
    {visible.length ? <div className="customer-grid">{visible.map((customer) => <Link className="customer-card" href={`/customers/${encodeURIComponent(customer.id)}`} key={customer.id}>
      <div className="customer-avatar">{displayName(customer.id, customer.displayName).slice(0, 1).toUpperCase()}</div>
      <div className="customer-card-heading"><div><h2>{displayName(customer.id, customer.displayName)}</h2><span>{customer.id}</span></div><Icon name="chevron-right" size={18} /></div>
      <div className="customer-stat-row"><div><strong>{customer.callCount ?? "—"}</strong><span>calls</span></div><div><strong>{customer.unresolvedCount ?? "—"}</strong><span>unresolved</span></div></div>
      <div className="customer-card-footer"><span>{customer.averageMood ? humanize(customer.averageMood) : "Mood pending"}</span><span>Last contact {formatDate(customer.lastContactAt)}</span></div>
    </Link>)}</div> : <EmptyState icon={customers.length ? "search" : "customer"} title={customers.length ? "No customer matches" : "No customers imported"} description={customers.length ? "Try a name or identifier from the source metadata." : "Customers appear when the dataset manifest is ingested."} />}
  </>;
}
