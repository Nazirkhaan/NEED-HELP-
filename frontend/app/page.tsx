"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth, ROLE_HOME } from "@/lib/auth";
import { Badge, Button, Card, CardContent } from "@/components/ui";
import { SyntheticTag } from "@/components/shared";

const DEMO_ROLES = [
  {
    role: "Student",
    email: "student.demo@sih.gov.in",
    desc: "Upload resume → skill extraction → gap vs target role → explainable matches → apply",
    home: "/student",
    tone: "brand" as const,
    icon: "🎓",
  },
  {
    role: "Institution / TPO",
    email: "tpo.cse.demo@sih.gov.in",
    desc: "Co-sign claimed skills, curriculum-gap alerts, placement analytics",
    home: "/tpo",
    tone: "blue" as const,
    icon: "🏛️",
  },
  {
    role: "Industry",
    email: "industry.cse.demo@sih.gov.in",
    desc: "Post JDs, review explainable applicant ranking, verify skills, log outcomes",
    home: "/industry",
    tone: "green" as const,
    icon: "🏢",
  },
  {
    role: "Admin / Ministry",
    email: "admin.demo@sih.gov.in",
    desc: "Skill-gap heatmap, curriculum alerts, RBAC editor, live stream re-seed",
    home: "/admin",
    tone: "purple" as const,
    icon: "📊",
  },
];

export default function Home() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && user) router.replace(ROLE_HOME[user.role] || "/login");
  }, [user, loading, router]);

  return (
    <div className="min-h-screen bg-gradient-to-b from-brand-900 via-brand-700 to-slate-50">
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <div className="text-center">
          <div className="mb-3 flex justify-center gap-2">
            <SyntheticTag />
            <Badge tone="green">SIH26044 · MVP build</Badge>
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight text-white sm:text-5xl">
            Academia ↔ Industry Collaboration Portal
          </h1>
          <p className="mx-auto mt-4 max-w-2xl text-sm leading-relaxed text-brand-100 sm:text-base">
            Skill mapping, internships &amp; placement — one closed loop: resume →
            extracted skills → gap vs target role → explainable semantic match →
            application → logged outcome → recalibrated demand weights and
            curriculum-gap alerts on the institution/Ministry dashboard.
          </p>
        </div>

        <div className="mt-12 grid gap-4 sm:grid-cols-2">
          {DEMO_ROLES.map((r) => (
            <Card key={r.role} className="border-slate-200/20 bg-white/95">
              <CardContent className="flex h-full flex-col gap-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-xl">{r.icon}</span>
                    <h2 className="font-semibold text-slate-900">{r.role}</h2>
                  </div>
                  <Badge tone={r.tone}>demo login</Badge>
                </div>
                <p className="text-xs leading-relaxed text-slate-500">{r.desc}</p>
                <div className="rounded-lg bg-slate-50 px-3 py-2 font-mono text-xs text-slate-600">
                  {r.email}
                  <span className="mx-1 text-slate-300">/</span>
                  demo1234
                </div>
                <div className="mt-auto flex gap-2">
                  <Link href="/login" className="flex-1">
                    <Button className="w-full" size="sm">
                      Sign in
                    </Button>
                  </Link>
                  <Link href={r.home} className="flex-1">
                    <Button variant="outline" size="sm" className="w-full">
                      Open view
                    </Button>
                  </Link>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        <p className="mt-10 text-center text-xs text-brand-100">
          Matching engine: local MiniLM sentence embeddings + pgvector cosine
          similarity, taxonomy aliases, TF-IDF fallback — no live LLM calls.
        </p>
      </div>
    </div>
  );
}
