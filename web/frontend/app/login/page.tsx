"use client";

import { useState, FormEvent, useEffect } from "react";
import { useRouter } from "next/navigation";

const PASSWORD = process.env.NEXT_PUBLIC_ESA_PASSWORD || "testpass";

export default function LoginPage() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  useEffect(() => {
    if (sessionStorage.getItem("esa-auth") === "1") {
      router.replace("/");
    }
  }, [router]);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    if (password === PASSWORD) {
      sessionStorage.setItem("esa-auth", "1");
      router.push("/");
    } else {
      setError("Invalid password");
      setLoading(false);
    }
  }

  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm p-6 card space-y-4"
      >
        <h1 className="text-3xl font-bold font-display text-gradient">Waypoint</h1>
        <p className="text-sm text-muted">Enter the shared password to continue.</p>
        {error && (
          <p className="text-sm text-remove bg-remove/10 px-3 py-2 rounded">{error}</p>
        )}
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password"
          className="input"
          autoFocus
        />
        <button
          type="submit"
          disabled={loading}
          className="btn w-full"
        >
          {loading ? "logging in…" : "log in"}
        </button>
      </form>
    </div>
  );
}
