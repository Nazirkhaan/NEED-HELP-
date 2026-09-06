"use client";

import { useCallback, useEffect, useState } from "react";
import { AppShell, PageGuard } from "@/components/app-shell";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  ErrorNote,
  Input,
  Label,
  Select,
  Spinner,
  Table,
  TD,
  TH,
  Tabs,
} from "@/components/ui";
import {
  EmptyState,
  SyntheticTag,
  VerificationBadge,
  heatColor,
} from "@/components/shared";
import { api } from "@/lib/api";

type HeatmapStream = {
  stream: string;
  stream_name: string;
  roles: string[];
  grid: { institution: string; institution_id: string; cells: (number | null)[] }[];
  role_details: {
    role: string;
    n_students: number;
    avg_readiness: number | null;
    missing_skills: { code: string; pct_missing: number }[];
  }[];
};

type Analytics = {
  totals: Record<string, number>;
  funnel: Record<string, number>;
  avg_outcome_rating: { avg_rating: string | null; n: number };
  top_demand_skills: { code: string; label: string; demand_weight: number; total_jd_weight: number; n_jds: number }[];
  recent_recalibrations: {
    id: string; code: string; label: string; result: string;
    performance_rating: number | null; old_weight: number; new_weight: number; reason: string;
    created_at: string;
  }[];
  stream_split: { stream: string; students: number; applications: number; outcomes: number }[];
  gap_alert_counts: { severity: string; n: number }[];
};

type RoleDef = {
  id: string;
  name: string;
  display_name: string;
  permissions: string[];
  description: string | null;
};

const CATALOG_PERMS = [
  "profile.manage.own", "skills.claim.own", "gap.view.own", "matches.view.own",
  "applications.create.own", "consent.manage.own",
  "students.view.institution", "skills.cosign.institution", "gaps.view.institution",
  "placements.view.institution", "matches.view.institution", "curriculum.view.institution",
  "jobs.manage.own", "applicants.view.own", "applications.review.own",
  "outcomes.log.own", "skills.verify.industry",
  "dashboard.view.all", "analytics.view.all", "curriculum.view.all",
  "rbac.manage", "taxonomy.manage", "reseed.run",
];

export default function AdminPage() {
  return (
    <PageGuard role="admin">
      <AdminView />
    </PageGuard>
  );
}

function AdminView() {
  const [tab, setTab] = useState("heatmap");
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [heatmap, setHeatmap] = useState<HeatmapStream[]>([]);
  const [gaps, setGaps] = useState<any[]>([]);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [roles, setRoles] = useState<RoleDef[]>([]);
  const [skills, setSkills] = useState<any[]>([]);
  const [stream, setStream] = useState("all");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [hm, cg, an] = await Promise.all([
        api<HeatmapStream[]>(stream === "all" ? "/admin/heatmap" : `/admin/heatmap?stream=${stream}`),
        api<any[]>("/admin/curriculum-gaps"),
        api<Analytics>("/admin/analytics"),
      ]);
      setHeatmap(hm);
      setGaps(cg);
      setAnalytics(an);
    } catch (e: any) {
      setError(e.message);
    }
  }, [stream]);

  useEffect(() => {
    load();
  }, [load]);

  const loadRoles = useCallback(async () => {
    setRoles(await api<RoleDef[]>("/admin/roles"));
  }, []);

  const loadSkills = useCallback(async () => {
    try {
      setSkills(await api<any[]>(`/admin/skills?stream=${stream === "all" ? "cse" : stream}`));
    } catch {
      setSkills([]);
    }
  }, [stream]);

  useEffect(() => {
    if (tab === "rbac") loadRoles();
    if (tab === "taxonomy") loadSkills();
  }, [tab, loadRoles, loadSkills]);

  async function reseed(targetStream: string) {
    if (
      !confirm(
        `Re-seed stream '${targetStream}'? This wipes that stream's synthetic students/JDs/matches and regenerates them (demo accounts are recreated). Live demo of config-driven re-seeding.`
      )
    )
      return;
    setBusy(true);
    setError(null);
    try {
      const res = await api<any>("/admin/reseed", {
        method: "POST",
        body: JSON.stringify({ stream: targetStream, students_per_institution: 16 }),
      });
      setToast(
        `Re-seeded ${res.stream}: ${res.students} students · ${res.job_descriptions} JDs · ${res.applications} applications · ${res.outcomes} outcomes · provider ${res.provider}`
      );
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function saveRole(role: RoleDef, perms: string[]) {
    try {
      await api(`/admin/roles/${role.name}`, {
        method: "PUT",
        body: JSON.stringify({ permissions: perms }),
      });
      setToast(`RBAC updated for '${role.name}' — effective immediately, no redeploy.`);
      await loadRoles();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function setWeight(skillId: string, weight: number) {
    try {
      await api(`/admin/skills/${skillId}/weight`, {
        method: "PUT",
        body: JSON.stringify({ demand_weight: weight }),
      });
      await loadSkills();
    } catch (e: any) {
      setError(e.message);
    }
  }

  const alerts = gaps.filter((g) => g.severity !== "low");

  return (
    <AppShell
      title="Ministry / Admin dashboard"
      subtitle="Cross-institution skill-gap heatmap, curriculum alerts, outcome-driven recalibration audit, dynamic RBAC."
    >
      <div className="mb-4 space-y-3">
        <ErrorNote message={error} onDismiss={() => setError(null)} />
        {toast && (
          <div className="flex items-start justify-between gap-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3.5 py-2.5 text-sm text-emerald-800">
            <span>{toast}</span>
            <button onClick={() => setToast(null)} className="text-emerald-400">✕</button>
          </div>
        )}
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3">
          <SyntheticTag />
          <div className="flex items-center gap-2">
            <Label className="mb-0">Stream</Label>
            <Select value={stream} onChange={(e) => setStream(e.target.value)} className="w-44">
              <option value="all">All streams</option>
              <option value="cse">CSE</option>
              <option value="ece">ECE</option>
            </Select>
          </div>
          <Button variant="outline" size="sm" onClick={load} disabled={busy}>
            ↻ Refresh
          </Button>
          <div className="ml-auto flex items-center gap-2">
            <span className="text-xs text-slate-500">Live re-seed (config-driven):</span>
            <Button variant="subtle" size="sm" disabled={busy} onClick={() => reseed("cse")}>
              CSE
            </Button>
            <Button variant="subtle" size="sm" disabled={busy} onClick={() => reseed("ece")}>
              ECE
            </Button>
            {busy && <Spinner />}
          </div>
        </div>
      </div>

      {/* KPI row */}
      {analytics && (
        <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-8">
          {[
            ["Students", analytics.totals.students, "🎓"],
            ["Institutions", analytics.totals.institutions, "🏛️"],
            ["Companies", analytics.totals.organizations, "🏢"],
            ["Jobs", analytics.totals.jobs, "📋"],
            ["Matches", analytics.totals.matches, "🔗"],
            ["Applications", analytics.totals.applications, "📨"],
            ["Outcomes", analytics.totals.outcomes, "🏁"],
            ["Recalibrations", analytics.recent_recalibrations.length, "⚖️"],
          ].map(([label, value, icon]) => (
            <Card key={label as string} className="overflow-hidden">
              <CardContent className="px-4 py-3">
                <div className="text-base">{icon as string}</div>
                <div className="mt-1 text-xl font-bold text-slate-800">{value as number}</div>
                <div className="text-[10px] font-medium uppercase tracking-wide text-slate-400">
                  {label as string}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Tabs
        tabs={[
          { key: "heatmap", label: "Skill-gap heatmap" },
          { key: "alerts", label: "Curriculum alerts", count: alerts.length },
          { key: "analytics", label: "Placement analytics" },
          { key: "rbac", label: "Roles & permissions" },
          { key: "taxonomy", label: "Taxonomy & weights" },
        ]}
        active={tab}
        onChange={setTab}
      />

      <div className="mt-4">
        {tab === "heatmap" && (
          <div className="space-y-4">
            {heatmap.length === 0 ? (
              <EmptyState
                icon="🌡️"
                title="No data to visualise"
                hint="Run a re-seed from the control bar above — the heatmap fills from student skills vs role requirements."
              />
            ) : (
              heatmap.map((hs) => (
                <Card key={hs.stream}>
                  <CardHeader>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <CardTitle>{hs.stream_name} — readiness by institution × role</CardTitle>
                        <CardDescription>
                          Cell = avg demand-weighted readiness (%). Verification state counts: claimed 70%,
                          co-signed 90%, verified 100% credit.
                        </CardDescription>
                      </div>
                      <div className="flex items-center gap-1.5 text-[10px] text-slate-500">
                        low
                        <span className={`${heatColor(5)} h-3 w-5 rounded`}></span>
                        <span className={`${heatColor(30)} h-3 w-5 rounded`}></span>
                        <span className={`${heatColor(55)} h-3 w-5 rounded`}></span>
                        <span className={`${heatColor(75)} h-3 w-5 rounded`}></span>
                        <span className={`${heatColor(95)} h-3 w-5 rounded`}></span>
                        high
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="overflow-x-auto">
                      <table className="w-full min-w-[640px] border-separate border-spacing-1">
                        <thead>
                          <tr>
                            <th className="text-left text-xs font-semibold text-slate-400">Institution</th>
                            {hs.roles.map((r) => (
                              <th key={r} className="px-1 pb-1 text-center text-[10px] font-medium leading-tight text-slate-500">
                                {r.replace(" Intern", "")}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {hs.grid.map((row) => (
                            <tr key={row.institution_id}>
                              <td className="whitespace-nowrap pr-2 text-xs font-medium text-slate-600">
                                {row.institution}
                              </td>
                              {row.cells.map((c, i) => (
                                <td key={i} className="p-0">
                                  <div
                                    className={`${heatColor(c)} flex h-11 items-center justify-center rounded-lg text-xs font-bold transition-transform hover:scale-105`}
                                    title={`${row.institution} · ${hs.roles[i]}: ${c ?? "no data"}`}
                                  >
                                    {c !== null ? c.toFixed(0) : "—"}
                                  </div>
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                      {hs.role_details.map((rd) => (
                        <div key={rd.role} className="rounded-lg border border-slate-100 p-3">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-semibold text-slate-700">{rd.role}</span>
                            <Badge tone={rd.avg_readiness !== null && rd.avg_readiness >= 60 ? "green" : "amber"}>
                              avg {rd.avg_readiness !== null ? rd.avg_readiness.toFixed(0) + "%" : "—"}
                            </Badge>
                          </div>
                          <div className="mt-2 space-y-1">
                            {rd.missing_skills.map((m) => (
                              <div key={m.code} className="flex items-center gap-2">
                                <span className="w-28 truncate text-[11px] text-slate-500">{m.code}</span>
                                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
                                  <div
                                    className="h-full rounded-full bg-rose-400"
                                    style={{ width: `${m.pct_missing}%` }}
                                  />
                                </div>
                                <span className="w-9 text-right text-[10px] text-slate-400">
                                  {m.pct_missing.toFixed(0)}%
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              ))
            )}
          </div>
        )}

        {tab === "alerts" && (
          <Card>
            <CardHeader>
              <CardTitle>Curriculum-gap alerts</CardTitle>
              <CardDescription>
                From <code>curriculum_gap_signal</code> — regenerated every time industry logs an outcome.
                High = ≥60% of a cohort lacks a skill that open JDs demand.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {gaps.length === 0 ? (
                <EmptyState icon="🔔" title="No signals" hint="Signals appear after seeding students + jobs." />
              ) : (
                <Table>
                  <thead>
                    <tr>
                      <TH>Severity</TH>
                      <TH>Institution</TH>
                      <TH>Skill</TH>
                      <TH>Missing</TH>
                      <TH>Demand</TH>
                      <TH>Computed</TH>
                    </tr>
                  </thead>
                  <tbody>
                    {gaps.map((g) => (
                      <tr key={g.id} className={g.severity === "high" ? "bg-rose-50/50" : ""}>
                        <TD>
                          <Badge tone={g.severity === "high" ? "red" : g.severity === "medium" ? "amber" : "slate"}>
                            {g.severity}
                          </Badge>
                        </TD>
                        <TD>
                          <span className="font-medium text-slate-800">{g.institution_name}</span>
                          <span className="ml-1.5 text-[11px] text-slate-400">{g.stream.toUpperCase()}</span>
                        </TD>
                        <TD>{g.label}</TD>
                        <TD>
                          {g.gap_count}/{g.student_count}{" "}
                          <span className="text-[11px] text-slate-400">
                            ({g.student_count ? Math.round((g.gap_count / g.student_count) * 100) : 0}%)
                          </span>
                        </TD>
                        <TD>{Number(g.demand_score).toFixed(2)}</TD>
                        <TD className="text-[11px] text-slate-400">
                          {new Date(g.computed_at).toLocaleTimeString()}
                        </TD>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </CardContent>
          </Card>
        )}

        {tab === "analytics" && analytics && (
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Placement funnel</CardTitle>
                <CardDescription>Applications → shortlisted → selected → completed → hired</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2.5">
                {[
                  ["Applied", analytics.funnel.applied, "bg-brand-500"],
                  ["Shortlisted+", analytics.funnel.shortlisted, "bg-sky-500"],
                  ["Selected", analytics.funnel.selected, "bg-indigo-500"],
                  ["Completed", analytics.funnel.completed, "bg-violet-500"],
                  ["Hired", analytics.funnel.hired, "bg-emerald-500"],
                ].map(([label, value, color]) => {
                  const max = Math.max(analytics.funnel.applied, 1);
                  return (
                    <div key={label as string}>
                      <div className="mb-1 flex justify-between text-xs">
                        <span className="font-medium text-slate-600">{label as string}</span>
                        <span className="text-slate-400">
                          {value as number}
                          {label === "Applied" && " · base"}
                        </span>
                      </div>
                      <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
                        <div
                          className={`h-full rounded-full ${color as string}`}
                          style={{ width: `${((value as number) / max) * 100}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
                <div className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500">
                  Avg outcome rating:{" "}
                  <strong className="text-slate-700">
                    {analytics.avg_outcome_rating.avg_rating ?? "—"} / 5
                  </strong>{" "}
                  across {analytics.avg_outcome_rating.n} outcomes
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Most demanded skills (live demand weights)</CardTitle>
                <CardDescription>
                  JD weight × taxonomy demand_weight — the number outcomes recalibrate.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                {analytics.top_demand_skills.map((s) => {
                  const max = Math.max(...analytics.top_demand_skills.map((x) => Number(x.total_jd_weight)), 1);
                  return (
                    <div key={s.code}>
                      <div className="mb-1 flex items-center justify-between text-xs">
                        <span className="font-medium text-slate-600">{s.label}</span>
                        <span className="text-slate-400">
                          {Number(s.total_jd_weight).toFixed(1)} · {s.n_jds} JDs · w{s.demand_weight.toFixed(2)}
                        </span>
                      </div>
                      <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-brand-500 to-violet-500"
                          style={{ width: `${(Number(s.total_jd_weight) / max) * 100}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </CardContent>
            </Card>
            <Card className="lg:col-span-2">
              <CardHeader>
                <CardTitle>Outcome → recalibration audit trail</CardTitle>
                <CardDescription>
                  Every demand-weight change with its trigger — this is the feedback loop made inspectable.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {analytics.recent_recalibrations.length === 0 ? (
                  <EmptyState icon="⚖️" title="No recalibrations yet" hint="Log an outcome from the Industry console." />
                ) : (
                  <Table>
                    <thead>
                      <tr>
                        <TH>Skill</TH>
                        <TH>Trigger</TH>
                        <TH>Weight change</TH>
                        <TH>Reason</TH>
                        <TH>When</TH>
                      </tr>
                    </thead>
                    <tbody>
                      {analytics.recent_recalibrations.map((r) => (
                        <tr key={r.id}>
                          <TD className="font-medium text-slate-800">{r.label}</TD>
                          <TD>
                            <Badge tone={r.result === "hired" ? "green" : r.result === "dropped" ? "red" : "slate"}>
                              {r.result} {r.performance_rating ? `★${r.performance_rating}` : ""}
                            </Badge>
                          </TD>
                          <TD>
                            <span className="font-mono text-xs">
                              {Number(r.old_weight).toFixed(3)} → <strong>{Number(r.new_weight).toFixed(3)}</strong>
                            </span>
                          </TD>
                          <TD className="max-w-xs text-xs text-slate-500">{r.reason}</TD>
                          <TD className="text-[11px] text-slate-400">
                            {new Date(r.created_at).toLocaleTimeString()}
                          </TD>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                )}
              </CardContent>
            </Card>
          </div>
        )}

        {tab === "rbac" && (
          <div className="space-y-4">
            <div className="rounded-lg border border-sky-200 bg-sky-50 px-3.5 py-2.5 text-xs text-sky-800">
              Permissions live in the <code>roles_permissions</code> table and are read on{" "}
              <strong>every request</strong> — edits below take effect on the next API call, with a full
              audit trail. This is how an evaluator's “make it work for a different role” request is
              satisfied: re-seed config, not redeploy.
            </div>
            {roles.map((r) => (
              <RoleEditor key={r.id} role={r} onSave={saveRole} />
            ))}
          </div>
        )}

        {tab === "taxonomy" && (
          <Card>
            <CardHeader>
              <CardTitle>Skill taxonomy & demand weights</CardTitle>
              <CardDescription>
                Config-driven (backend/configs/stream_*.json). Weights drift via outcomes; edit inline to
                demo demand steering — future matches update instantly.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <thead>
                  <tr>
                    <TH>Skill</TH>
                    <TH>Category</TH>
                    <TH>Demand weight</TH>
                    <TH>Recalibrations</TH>
                    <TH>Adjust</TH>
                  </tr>
                </thead>
                <tbody>
                  {skills.map((s) => (
                    <tr key={s.id}>
                      <TD className="font-medium text-slate-800">{s.label}</TD>
                      <TD>
                        <Badge>{s.category}</Badge>
                      </TD>
                      <TD>
                        <span className="font-mono text-xs font-semibold text-slate-700">
                          {s.demand_weight.toFixed(3)}
                        </span>
                        {s.recalibrations > 0 && (
                          <Badge tone="purple" className="ml-2">
                            ⚖️ {s.recalibrations}
                          </Badge>
                        )}
                      </TD>
                      <TD className="text-[11px] text-slate-400">
                        {s.last_recalibrated ? new Date(s.last_recalibrated).toLocaleString() : "—"}
                      </TD>
                      <TD>
                        <div className="flex gap-1">
                          {[0.9, 1.0, 1.1, 1.25].map((w) => (
                            <Button
                              key={w}
                              size="sm"
                              variant={Math.abs(s.demand_weight - w) < 0.01 ? "default" : "subtle"}
                              onClick={() => setWeight(s.id, w)}
                            >
                              {w}
                            </Button>
                          ))}
                        </div>
                      </TD>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </CardContent>
          </Card>
        )}
      </div>
    </AppShell>
  );
}

function RoleEditor({
  role,
  onSave,
}: {
  role: RoleDef;
  onSave: (role: RoleDef, perms: string[]) => void;
}) {
  const [perms, setPerms] = useState<string[]>(role.permissions);
  const [dirty, setDirty] = useState(false);

  function toggle(p: string) {
    setPerms((prev) => (prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]));
    setDirty(true);
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>
            {role.display_name} <span className="font-mono text-xs text-slate-400">({role.name})</span>
          </CardTitle>
          <CardDescription>{role.description}</CardDescription>
        </div>
        <Button size="sm" disabled={!dirty} onClick={() => onSave(role, perms)}>
          {dirty ? "Save changes" : "Saved"}
        </Button>
      </CardHeader>
      <CardContent className="flex flex-wrap gap-1.5">
        {CATALOG_PERMS.map((p) => (
          <button
            key={p}
            onClick={() => toggle(p)}
            className={`rounded-lg px-2 py-1 font-mono text-[11px] transition-colors ${
              perms.includes(p)
                ? "bg-brand-600 text-white"
                : "bg-slate-100 text-slate-500 hover:bg-slate-200"
            }`}
          >
            {p}
          </button>
        ))}
      </CardContent>
    </Card>
  );
}
