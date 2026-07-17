"use client";

import { useState, useEffect, useCallback } from "react";
import {
  getIncentives,
  patchIncentive,
  deleteIncentive,
  createIncentive,
  getNews,
  Incentive,
  IncentiveCreateRequest,
  NewsItem,
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

/**
 * Poll the news ticker endpoint on an interval.
 * Silent on error (ticker just stays empty / shows last data).
 */
export function useNews(pollMs = 60000) {
  const [news, setNews] = useState<NewsItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    const load = () => {
      getNews()
        .then((items) => {
          if (active) setNews(items);
        })
        .catch(() => {
          /* keep prior items; ticker is non-critical */
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    };
    load();
    const id = setInterval(load, pollMs);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [pollMs]);

  return { news, loading };
}
