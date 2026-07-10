"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

function hasSession(): boolean {
  return (
    sessionStorage.getItem("esa-auth") === "1" ||
    sessionStorage.getItem("esa_admin_authed") === "1"
  );
}

export function useAuth() {
  const router = useRouter();

  useEffect(() => {
    if (!hasSession()) {
      router.replace("/login");
    }
  }, [router]);
}

export function isAuthenticated(): boolean {
  if (typeof window === "undefined") return false;
  return hasSession();
}
