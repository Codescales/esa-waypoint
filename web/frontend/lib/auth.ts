"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

function getApiBase(): string {
  if (typeof window === "undefined") return "";
  return process.env.NEXT_PUBLIC_API_BASE || "";
}

async function checkSession(): Promise<boolean> {
  try {
    const res = await fetch(`${getApiBase()}/api/auth/status`, {
      credentials: "include",
    });
    return res.ok;
  } catch {
    return false;
  }
}

export function useAuth() {
  const router = useRouter();

  useEffect(() => {
    checkSession().then((ok) => {
      if (!ok) {
        const redirect = encodeURIComponent(window.location.pathname);
        router.replace(`/login?redirect=${redirect}`);
      }
    });
  }, [router]);
}

export function isAuthenticated(): Promise<boolean> {
  return checkSession();
}
