export default function Loading() {
  return (
    <div className="route-loading" role="status" aria-live="polite" aria-label="Loading page">
      <div className="route-loading-heading">
        <span className="skeleton skeleton-eyebrow" />
        <span className="skeleton skeleton-title" />
        <span className="skeleton skeleton-copy" />
      </div>
      <div className="route-loading-grid">
        {Array.from({ length: 4 }, (_, index) => <span className="skeleton skeleton-card" key={index} />)}
      </div>
      <span className="skeleton skeleton-panel" />
      <span className="sr-only">Loading page</span>
    </div>
  );
}
