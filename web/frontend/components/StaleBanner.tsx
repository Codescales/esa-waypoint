"use client";

import { useEffect, useState } from "react";
import { getHealth, StaleInfo } from "@/lib/api";

export default function StaleBanner() {
  const [stale, setStale] = useState<StaleInfo | null>(null);

  useEffect(() => {
    getHealth()
      .then(setStale)
      .catch(() => setStale({ age_hours: null, is_stale: true, is_missing: true }));
  }, []);

  if (!stale || (!stale.is_stale && !stale.is_missing)) return null;

  return (
    <div className="bg-stale/10 border-b border-stale/30 px-4 py-2 text-sm text-stale flex items-center gap-2">
      <span className="font-bold">⚠</span>
      <span>
        {stale.is_missing
          ? "Spreadsheet not found — run the pipeline first."
          : `Spreadsheet ${stale.age_hours?.toFixed(0)}h old — data may be stale.`}
      </span>
    </div>
  );
}
