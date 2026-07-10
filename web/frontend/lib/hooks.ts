"use client";

import { useState, useEffect, useCallback } from "react";
import {
  getIncentives,
  patchIncentive,
  deleteIncentive,
  createIncentive,
  Incentive,
  IncentiveCreateRequest,
} from "@/lib/api";

export function useIncentives(opts?: string | { runSlug?: string; upcoming?: boolean }) {
  const [incentives, setIncentives] = useState<Incentive[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const runSlug = typeof opts === "string" ? opts : opts?.runSlug;
  const upcoming = typeof opts === "object" ? opts?.upcoming : undefined;

  const fetch = useCallback(() => {
    setLoading(true);
    setError(null);
    const params: Record<string, string> = {};
    if (runSlug) params.run_slug = runSlug;
    if (upcoming) params.upcoming = "true";
    getIncentives(Object.keys(params).length ? params : undefined)
      .then(setIncentives)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [runSlug, upcoming]);

  useEffect(() => {
    fetch();
  }, [fetch]);

  useEffect(() => {
    window.addEventListener("focus", fetch);
    return () => window.removeEventListener("focus", fetch);
  }, [fetch]);

  function updateIncentive(updated: Incentive) {
    setIncentives((prev) =>
      prev.map((x) => (x.uuid === updated.uuid ? updated : x))
    );
  }

  function removeIncentive(uuid: string) {
    setIncentives((prev) =>
      prev.map((x) => (x.uuid === uuid ? { ...x, status: "Removed" } : x))
    );
  }

  function addIncentive(created: Incentive) {
    setIncentives((prev) => [...prev, created]);
  }

  return {
    incentives,
    loading,
    error,
    updateIncentive,
    removeIncentive,
    addIncentive,
  };
}
