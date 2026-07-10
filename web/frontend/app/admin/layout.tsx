"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { adminStatus } from "@/lib/api";
import AdminLoginForm from "@/components/AdminLoginForm";

const ADMIN_TABS = [
  { href: "/admin", label: "Dashboard", segment: null },
  { href: "/admin/runs", label: "Runs", segment: "runs" },
  { href: "/admin/runners", label: "Runners", segment: "runners" },
  { href: "/admin/incentives", label: "Incentives", segment: "incentives" },
];

function AdminSubNav() {
  const pathname = usePathname();

  return (
    <nav className="flex gap-1 mb-6 border-b border-border pb-3">
      {ADMIN_TABS.map((tab) => {
        const isActive =
          tab.segment === null
            ? pathname === "/admin"
            : pathname.startsWith(`/admin/${tab.segment}`);
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={`px-3 py-1.5 text-sm rounded transition-colors ${
              isActive
                ? "bg-brand/10 text-brand font-semibold"
                : "text-muted hover:text-foreground hover:bg-surface"
            }`}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [authed, setAuthed] = useState<boolean | null>(null);

  useEffect(() => {
    adminStatus()
      .then(() => setAuthed(true))
      .catch(() => setAuthed(false));
  }, []);

  if (authed === null) {
    return <p className="text-muted text-sm mt-8">Loading...</p>;
  }

  if (!authed) {
    return <AdminLoginForm onLogin={() => setAuthed(true)} />;
  }

  return (
    <div>
      <AdminSubNav />
      {children}
    </div>
  );
}
