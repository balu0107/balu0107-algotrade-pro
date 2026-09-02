"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { API_URL } from "@/lib/api";
import { ThemeToggle, useTheme } from "@/components/ThemeToggle";

type NotificationChannel = "email" | "whatsapp" | "telegram";

const NOTIFICATION_OPTIONS: { value: NotificationChannel; label: string }[] = [
  { value: "email", label: "Email" },
  { value: "whatsapp", label: "WhatsApp" },
  { value: "telegram", label: "Telegram" },
];

export default function SignupPage() {
  const router = useRouter();
  const { theme, toggleTheme } = useTheme();

  const [fullName, setFullName] = useState("");
  const [age, setAge] = useState("");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [gender, setGender] = useState("");
  const [notificationPreference, setNotificationPreference] =
    useState<NotificationChannel>("email");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    const ageNumber = Number(age);
    if (!fullName.trim() || !phoneNumber.trim() || !gender || !username.trim() || !password) {
      setError("Please fill in every field.");
      return;
    }
    if (!Number.isFinite(ageNumber) || ageNumber <= 0 || ageNumber > 120) {
      setError("Enter a valid age.");
      return;
    }

    setIsSubmitting(true);
    try {
      const res = await fetch(`${API_URL}/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: username.trim(),
          password,
          full_name: fullName.trim(),
          age: ageNumber,
          phone_number: phoneNumber.trim(),
          gender,
          notification_preference: notificationPreference,
        }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error(data?.detail ?? "Could not create account.");
      }

      setSuccess(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Server error. Ensure backend is running.");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (success) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--surface-0)] p-4 text-[var(--text-primary)]">
        <div className="w-full max-w-sm space-y-6 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] p-8 text-center shadow-2xl">
          <div className="flex justify-end">
            <ThemeToggle theme={theme} onToggle={toggleTheme} />
          </div>
          <h2 className="text-2xl font-extrabold text-[var(--text-primary)]">Account created</h2>
          <p className="text-sm text-[var(--text-muted)]">
            You&apos;re all set. Log in with your new username and password to continue.
          </p>
          <button
            onClick={() => router.push("/")}
            className="w-full rounded-lg bg-blue-600 p-3 font-bold text-white shadow-lg shadow-blue-900/50 transition hover:bg-blue-500"
          >
            GO TO LOGIN
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--surface-0)] p-4 text-[var(--text-primary)]">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm space-y-6 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] p-8 shadow-2xl"
      >
        <div className="flex justify-end">
          <ThemeToggle theme={theme} onToggle={toggleTheme} />
        </div>
        <div className="text-center">
          <h2 className="text-3xl font-extrabold text-[var(--text-primary)]">Create Account</h2>
          <p className="mt-1 text-sm text-[var(--text-muted)]">Join Pro Terminal to track your stocks</p>
        </div>

        {error && (
          <p className="rounded bg-red-900/20 p-2 text-center text-sm text-red-400">{error}</p>
        )}

        <div className="space-y-3">
          <input
            type="text"
            placeholder="Full name"
            className="w-full rounded-lg border border-[var(--border-strong)] bg-[var(--surface-2)] p-3 outline-none transition focus:ring-2 focus:ring-blue-500"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
          />

          <div className="grid grid-cols-2 gap-3">
            <input
              type="number"
              min="1"
              max="120"
              placeholder="Age"
              className="w-full rounded-lg border border-[var(--border-strong)] bg-[var(--surface-2)] p-3 outline-none transition focus:ring-2 focus:ring-blue-500"
              value={age}
              onChange={(e) => setAge(e.target.value)}
            />
            <select
              value={gender}
              onChange={(e) => setGender(e.target.value)}
              className="w-full rounded-lg border border-[var(--border-strong)] bg-[var(--surface-2)] p-3 text-[var(--text-primary)] outline-none transition focus:ring-2 focus:ring-blue-500"
            >
              <option value="" disabled>
                Gender
              </option>
              <option value="female">Female</option>
              <option value="male">Male</option>
              <option value="other">Other</option>
              <option value="prefer_not_to_say">Prefer not to say</option>
            </select>
          </div>

          <input
            type="tel"
            placeholder="Phone number"
            className="w-full rounded-lg border border-[var(--border-strong)] bg-[var(--surface-2)] p-3 outline-none transition focus:ring-2 focus:ring-blue-500"
            value={phoneNumber}
            onChange={(e) => setPhoneNumber(e.target.value)}
          />

          <input
            type="text"
            placeholder="Username"
            className="w-full rounded-lg border border-[var(--border-strong)] bg-[var(--surface-2)] p-3 outline-none transition focus:ring-2 focus:ring-blue-500"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />

          <input
            type="password"
            placeholder="Password"
            className="w-full rounded-lg border border-[var(--border-strong)] bg-[var(--surface-2)] p-3 outline-none transition focus:ring-2 focus:ring-blue-500"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-widest text-[var(--text-faint)]">
            Notify me via
          </p>
          <div className="flex rounded-lg border border-[var(--border-strong)] bg-[var(--surface-0)] p-1">
            {NOTIFICATION_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => setNotificationPreference(option.value)}
                className={`flex-1 rounded-md px-3 py-2 text-sm font-bold transition ${
                  notificationPreference === option.value
                    ? "bg-blue-600 text-white"
                    : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
          <p className="mt-2 text-xs text-[var(--text-faint)]">
            Delivery integrations are coming soon &mdash; this just saves your preference for now.
          </p>
        </div>

        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full rounded-lg bg-blue-600 p-3 font-bold text-white shadow-lg shadow-blue-900/50 transition hover:bg-blue-500 disabled:opacity-50"
        >
          {isSubmitting ? "CREATING..." : "CREATE ACCOUNT"}
        </button>

        <p className="text-center text-sm text-[var(--text-muted)]">
          Already have an account?{" "}
          <Link href="/" className="font-semibold text-blue-400 transition hover:text-blue-300">
            Log in
          </Link>
        </p>
      </form>
    </div>
  );
}
