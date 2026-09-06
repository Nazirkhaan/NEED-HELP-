"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth, ROLE_HOME } from "@/lib/auth";
import { api } from "@/lib/api";
import { Badge, Button, Spinner } from "./ui";
import { SyntheticTag } from "./shared";

export function AppShell({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const [provider, setProvider] = useState<string | null>(null);

  useEffect(() => {
    if (user) {
      api<{ provider: string }>("/meta/provider")
        .then((r) => setProvider(r.provider))
        .catch(() => setProvider(null));
    }
  }, [user]);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center gap-3 text-slate-500">
        <Spinner /> Loading your session…
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-4 py-2.5 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <Link
              href={ROLE_HOME[user.role] || "/"}
              className="flex items-center gap-2 whitespace-nowrap"
            >
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-sm font-bold text-white">
                SI
              </span>
              <span className="hidden text-sm font-semibold text-slate-800 sm:block">
                SkillBridge Portal
              </span>
            </Link>
            <Badge tone="brand">{user.role_display}</Badge>
            <SyntheticTag />
            {provider && (
              <Badge tone={provider === "fastembed" ? "green" : "slate"} className="hidden md:inline-flex">
                matcher: {provider === "fastembed" ? "MiniLM embeddings + pgvector" : "TF-IDF fallback"}
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-3">
            <div className="hidden text-right sm:block">
              <div className="text-xs font-semibold text-slate-800">{user.full_name}</div>
              <div className="text-[11px] text-slate-400">{user.email}</div>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                logout();
                router.replace("/login");
              }}
            >
              Sign out
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        <div className="mb-5">
          <h1 className="text-xl font-bold text-slate-900 sm:text-2xl">{title}</h1>
          {subtitle && <p className="mt-0.5 text-sm text-slate-500">{subtitle}</p>}
        </div>
        {children}
      </main>

      <footer className="border-t border-slate-200 py-4 text-center text-[11px] text-slate-400">
        SIH26044 MVP · Synthetic demo data only · Matching runs locally (no live LLM)
      </footer>
    </div>
  );
}

export function PageGuard({ role, children }: { role: string; children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (!loading && user && user.role !== role) {
      router.replace(ROLE_HOME[user.role] || "/login");
    }
  }, [loading, user, role, router]);
  if (loading) return <Splash />;
  if (!user || user.role !== role) return <Splash />;
  return <>{children}</>;
}

function Splash() {
  return (
    <div className="flex min-h-screen items-center justify-center gap-3 text-slate-500">
      <Spinner /> Checking your role…
    </div>
  );
}
