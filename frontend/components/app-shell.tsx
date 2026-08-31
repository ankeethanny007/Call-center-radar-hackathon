"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { Icon } from "./icons";

const navigation = [
  { href: "/", label: "Overview", icon: "home" as const },
  { href: "/attention", label: "Manager attention", icon: "queue" as const },
  { href: "/customers", label: "Customers", icon: "customer" as const },
  { href: "/calls", label: "Calls", icon: "headphones" as const },
  { href: "/trends", label: "Trends", icon: "trend" as const },
  { href: "/agents", label: "Agents", icon: "briefcase" as const },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [expanded, setExpanded] = useState(false);
  const [navigatingTo, setNavigatingTo] = useState<string | null>(null);

  useEffect(() => {
    setNavigatingTo(null);
  }, [pathname]);

  function startNavigation(href: string) {
    setExpanded(false);
    if (!isActive(pathname, href)) setNavigatingTo(href);
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-inner">
          <Link className="brand" href="/" onClick={() => setExpanded(false)} aria-label="Call-Centre Radar home">
            <span className="brand-mark"><Icon name="radar" size={23} /></span>
            <span>Call-Centre <em>Radar</em></span>
          </Link>
          <button className="mobile-menu" type="button" onClick={() => setExpanded((open) => !open)} aria-expanded={expanded} aria-label="Toggle navigation">
            <Icon name={expanded ? "x" : "menu"} />
          </button>
          <nav className={expanded ? "main-nav is-open" : "main-nav"} aria-label="Primary navigation">
            {navigation.map((item) => (
              <Link
                className={`${isActive(pathname, item.href) ? "nav-link is-active" : "nav-link"}${navigatingTo === item.href ? " is-loading" : ""}`}
                href={item.href}
                key={item.href}
                onClick={() => startNavigation(item.href)}
              >
                {navigatingTo === item.href ? <span className="nav-loader" aria-hidden="true" /> : <Icon name={item.icon} size={18} />}
                <span>{item.label}</span>
              </Link>
            ))}
          </nav>
          <div className="topbar-status"><span className="live-dot" /> Evidence-first analysis</div>
        </div>
      </header>
      <main className="page-container">{children}</main>
      <footer className="site-footer">
        <span>Submitted by Ankeet Hanny for AI Hackathon at VRIZE</span>
      </footer>
    </div>
  );
}
