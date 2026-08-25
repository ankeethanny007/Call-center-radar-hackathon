import type { SVGProps } from "react";

type IconName =
  | "activity"
  | "arrow-right"
  | "briefcase"
  | "chart"
  | "chevron-right"
  | "clock"
  | "customer"
  | "document"
  | "filter"
  | "headphones"
  | "home"
  | "menu"
  | "play"
  | "queue"
  | "radar"
  | "search"
  | "shield"
  | "sparkle"
  | "trend"
  | "user"
  | "warning"
  | "x";

export function Icon({ name, size = 20, ...props }: { name: IconName; size?: number } & SVGProps<SVGSVGElement>) {
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
    ...props,
  };
  switch (name) {
    case "activity":
      return <svg {...common}><path d="M3 12h3l2.2-7 4.1 14 2.3-7H21" /></svg>;
    case "arrow-right":
      return <svg {...common}><path d="M5 12h14M13 6l6 6-6 6" /></svg>;
    case "briefcase":
      return <svg {...common}><rect x="3" y="7" width="18" height="13" rx="2" /><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 12h18M10 12v2h4v-2" /></svg>;
    case "chart":
      return <svg {...common}><path d="M4 19V5M4 19h16" /><path d="m7 16 4-5 3 2 5-7" /></svg>;
    case "chevron-right":
      return <svg {...common}><path d="m9 18 6-6-6-6" /></svg>;
    case "clock":
      return <svg {...common}><circle cx="12" cy="12" r="8.5" /><path d="M12 7v5l3.5 2" /></svg>;
    case "customer":
      return <svg {...common}><circle cx="9" cy="8" r="3" /><path d="M3.5 20c.7-3.5 2.6-5.2 5.5-5.2s4.8 1.7 5.5 5.2M16 8h5M18.5 5.5v5" /></svg>;
    case "document":
      return <svg {...common}><path d="M6 3h8l4 4v14H6z" /><path d="M14 3v5h5M9 12h6M9 16h6" /></svg>;
    case "filter":
      return <svg {...common}><path d="M4 5h16l-6 7v5l-4 2v-7z" /></svg>;
    case "headphones":
      return <svg {...common}><path d="M4 14v-2a8 8 0 0 1 16 0v2" /><path d="M4 14h3v5H5a1 1 0 0 1-1-1zM20 14h-3v5h2a1 1 0 0 0 1-1z" /></svg>;
    case "home":
      return <svg {...common}><path d="m3 10 9-7 9 7v10H3z" /><path d="M9 20v-6h6v6" /></svg>;
    case "menu":
      return <svg {...common}><path d="M4 7h16M4 12h16M4 17h16" /></svg>;
    case "play":
      return <svg {...common} fill="currentColor"><path stroke="none" d="m9 6 10 6-10 6z" /></svg>;
    case "queue":
      return <svg {...common}><path d="M4 6h16M4 12h11M4 18h7" /><circle cx="19" cy="12" r="1" /></svg>;
    case "radar":
      return <svg {...common}><circle cx="12" cy="12" r="8.5" /><path d="M12 12 18 7M12 3v2M21 12h-2M12 21v-2M3 12h2" /><circle cx="12" cy="12" r="1.8" fill="currentColor" /></svg>;
    case "search":
      return <svg {...common}><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4.5 4.5" /></svg>;
    case "shield":
      return <svg {...common}><path d="M12 3 20 6v5c0 5-3.3 8.4-8 10-4.7-1.6-8-5-8-10V6z" /><path d="m8.5 12 2.2 2.2 4.8-5" /></svg>;
    case "sparkle":
      return <svg {...common}><path d="m12 3 1.2 5.8L19 10l-5.8 1.2L12 17l-1.2-5.8L5 10l5.8-1.2zM19 16l.6 2.4L22 19l-2.4.6L19 22l-.6-2.4L16 19l2.4-.6z" /></svg>;
    case "trend":
      return <svg {...common}><path d="M4 17 10 11l4 3 6-7" /><path d="M15 7h5v5" /></svg>;
    case "user":
      return <svg {...common}><circle cx="12" cy="8" r="3.5" /><path d="M5 21c.7-4 3-6 7-6s6.3 2 7 6" /></svg>;
    case "warning":
      return <svg {...common}><path d="m12 3 9 16H3z" /><path d="M12 9v4M12 17h.01" /></svg>;
    case "x":
      return <svg {...common}><path d="m6 6 12 12M18 6 6 18" /></svg>;
  }
}
