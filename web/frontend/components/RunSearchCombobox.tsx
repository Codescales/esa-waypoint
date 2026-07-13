"use client";

import { useState, useRef, useEffect } from "react";
import { getRuns, Run } from "@/lib/api";

export default function RunSearchCombobox({
  value,
  onChange,
}: {
  value: string;
  onChange: (slug: string) => void;
}) {
  const [query, setQuery] = useState(value);
  const [results, setResults] = useState<Run[]>([]);
  const [open, setOpen] = useState(false);
  const [highlightIdx, setHighlightIdx] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const blurTimer = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => {
    const timer = setTimeout(async () => {
      try {
        const q = query.trim();
        const runs = await getRuns({ search: q || undefined, marathon: true });
        setResults(runs.slice(0, 50));
        setOpen(true);
        setHighlightIdx(-1);
      } catch {
        // ignore
      }
    }, 200);
    return () => clearTimeout(timer);
  }, [query]);

  function select(slug: string, label: string) {
    onChange(slug);
    setQuery(label);
    setOpen(false);
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") {
      // Always prevent Enter from submitting a parent form while the combobox is active.
      e.preventDefault();
      if (open && highlightIdx >= 0) {
        const r = results[highlightIdx];
        select(r.slug, `${r.game} — ${r.runner_display}`);
      }
      return;
    }
    if (!open) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightIdx((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  useEffect(() => {
    if (highlightIdx >= 0 && listRef.current) {
      const item = listRef.current.children[highlightIdx] as HTMLElement;
      item?.scrollIntoView({ block: "nearest" });
    }
  }, [highlightIdx]);

  function handleBlur() {
    blurTimer.current = setTimeout(() => setOpen(false), 300);
  }

  function handleFocus() {
    if (blurTimer.current) clearTimeout(blurTimer.current);
    if (results.length > 0) setOpen(true);
  }

  return (
    <div className="relative">
      <input
        ref={inputRef}
        type="text"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          if (value && e.target.value !== query) onChange("");
        }}
        onFocus={handleFocus}
        onBlur={handleBlur}
        onKeyDown={handleKeyDown}
        placeholder="Search game / runner..."
        className="input input-sm w-full"
      />
      {open && results.length > 0 && (
        <ul
          ref={listRef}
          className="absolute z-50 mt-1 w-full max-h-[300px] overflow-y-auto card p-1 shadow-lg"
        >
          {results.map((r, i) => (
            <li
              key={r.slug}
              onMouseDown={() => select(r.slug, `${r.game} — ${r.runner_display}`)}
              onMouseEnter={() => setHighlightIdx(i)}
              className={`px-2 py-1.5 rounded cursor-pointer text-sm ${
                i === highlightIdx ? "bg-brand/20" : "hover:bg-surface"
              }`}
            >
              <span className="font-medium">{r.game}</span>
              <span className="text-muted ml-1">{r.category}</span>
              <span className="text-muted text-xs ml-2">— {r.runner_display}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
