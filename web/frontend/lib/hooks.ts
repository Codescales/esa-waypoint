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

export function useIncentives(runSlug?: string) {
  const [incentives, setIncentives] = useState<Incentive[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(() => {
    setLoading(true);
    setError(null);
    getIncentives(runSlug ? { run_slug: runSlug } : undefined)
      .then(setIncentives)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [runSlug]);

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
