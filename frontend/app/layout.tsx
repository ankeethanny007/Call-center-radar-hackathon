import type { Metadata } from "next";
import { AppShell } from "../components/app-shell";
import "./styles.css";

export const metadata: Metadata = {
  title: "Call-Centre Radar",
  description: "Evidence-first intelligence for consumer-bank support calls.",
};

export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><AppShell>{children}</AppShell></body></html>;
}
