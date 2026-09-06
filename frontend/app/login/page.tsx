"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth, ROLE_HOME } from "@/lib/auth";
import { Button, Card, CardContent, ErrorNote, Input, Label } from "@/components/ui";
import { SyntheticTag } from "@/components/shared";

const QUICK = [
  { label: "Student", email: "student.demo@sih.gov.in" },
  { label: "Student (literal twin)", email: "student.demo2@sih.gov.in" },
  { label: "TPO", email: "tpo.cse.demo@sih.gov.in" },
  { label: "Industry", email: "industry.cse.demo@sih.gov.in" },
  { label: "Admin", email: "admin.demo@sih.gov.in" },
];

export default function LoginPage() {
  const { login, user, loading } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("student.demo@sih.gov.in");
  const [password, setPassword] = useState("demo1234");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!loading && user) router.replace(ROLE_HOME[user.role] || "/");
  }, [user, loading, router]);

  async function doLogin(e?: React.FormEvent, overrideEmail?: string) {
    e?.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const u = await login(overrideEmail || email, password);
      router.replace(ROLE_HOME[u.role] || "/");
    } catch (err: any) {
      setError(err.message || "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-md">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-brand-600 text-lg font-bold text-white">
            SI
          </div>
          <h1 className="text-xl font-bold text-slate-900">
            SkillBridge Portal · SIH26044
          </h1>
          <p className="mt-1 text-xs text-slate-500">
            Academia–Industry collaboration MVP · <SyntheticTag />
          </p>
        </div>
        <Card>
          <CardContent className="space-y-4">
            <form onSubmit={doLogin} className="space-y-3">
              <div>
                <Label>Email</Label>
                <Input
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.edu"
                  autoComplete="username"
                />
              </div>
              <div>
                <Label>Password</Label>
                <Input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                />
              </div>
              <ErrorNote message={error} onDismiss={() => setError(null)} />
              <Button type="submit" className="w-full" disabled={busy}>
                {busy ? "Signing in…" : "Sign in"}
              </Button>
            </form>
            <div>
              <div className="mb-2 text-center text-[11px] uppercase tracking-wide text-slate-400">
                Or jump into a demo role
              </div>
              <div className="grid grid-cols-2 gap-1.5">
                {QUICK.map((q) => (
                  <Button
                    key={q.email}
                    variant="subtle"
                    size="sm"
                    onClick={() => {
                      setEmail(q.email);
                      doLogin(undefined, q.email);
                    }}
                    disabled={busy}
                  >
                    {q.label}
                  </Button>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
        <p className="mt-4 text-center text-[11px] text-slate-400">
          All demo accounts use password <code>demo1234</code>. Every seeded
          account is synthetic.
        </p>
      </div>
    </div>
  );
}
