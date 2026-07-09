"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export function useAuth() {
  const router = useRouter();

  useEffect(() => {
    if (sessionStorage.getItem("esa-auth") !== "1") {
      router.replace("/login");
    }
  }, [router]);
}

export function isAuthenticated(): boolean {
  if (typeof window === "undefined") return false;
  return sessionStorage.getItem("esa-auth") === "1";
}
