"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import Chevron from "./Chevron";
import { useTheme } from "./ThemeProvider";

export default function Nav() {
  const path = usePathname();
  const { theme, toggle } = useTheme();

  const links = [
    { href: "/", label: "Marathon", exact: true },
    { href: "/schedule", label: "Schedule", exact: true },
    { href: "/incentives", label: "Incentives", exact: true },
    { href: "/admin", label: "Admin", exact: false },
  ];

  return (
    <nav className="bg-surface">
      <div className="flex items-center gap-4 px-4 py-3">
        <Link
          href="/"
          className="flex items-center gap-2 text-2xl font-display tracking-wide"
        >
          <Chevron size={20} />
          <span className="text-gradient">waypoint</span>
        </Link>
        <div className="flex gap-3 ml-4">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={`text-sm transition-colors ${
                (l.exact ? path === l.href : path.startsWith(l.href))
                  ? "text-brand font-semibold"
                  : "text-muted hover:text-foreground"
              }`}
            >
              {l.label}
            </Link>
          ))}
        </div>
        <button
          onClick={toggle}
          aria-label={`Switch to ${theme === "light" ? "dark" : "light"} mode`}
          className="ml-auto p-2 rounded text-muted hover:text-foreground transition-colors"
          title={theme === "light" ? "Dark mode" : "Light mode"}
        >
          {theme === "light" ? (
            // Moon icon
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
            </svg>
          ) : (
            // Sun icon
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="12" cy="12" r="5" />
              <line x1="12" y1="1" x2="12" y2="3" />
              <line x1="12" y1="21" x2="12" y2="23" />
              <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
              <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
              <line x1="1" y1="12" x2="3" y2="12" />
              <line x1="21" y1="12" x2="23" y2="12" />
              <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
              <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
            </svg>
          )}
        </button>
      </div>
      <div className="sep-4" />
    </nav>
  );
}
