"use client";

import { useState, FormEvent } from "react";
import { adminLogin } from "@/lib/api";

interface Props {
  onLogin: () => void;
}

export default function AdminLoginForm({ onLogin }: Props) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await adminLogin(password);
      setPassword("");
      onLogin();
    } catch {
      setError("Invalid admin password");
    }
  }

  return (
    <div className="max-w-md mx-auto mt-12">
      <form onSubmit={handleSubmit} className="p-6 card space-y-4">
        <h1 className="text-xl font-bold">Admin Login</h1>
        <p className="text-sm text-muted">
          Admin operations require a separate password. Hosts cannot see this page.
        </p>
        {error && (
          <p className="text-sm text-remove bg-remove/10 px-3 py-2 rounded">{error}</p>
        )}
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Admin password"
          className="input"
          autoFocus
        />
        <button type="submit" className="btn w-full">
          log in
        </button>
        <p className="text-xs text-muted">
          <a href="/" className="hover:underline">
            ← Back to marathon
          </a>
        </p>
      </form>
    </div>
  );
}
