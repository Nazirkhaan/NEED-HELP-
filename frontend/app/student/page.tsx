"use client";

import { useCallback, useEffect, useState } from "react";
import { AppShell, PageGuard } from "@/components/app-shell";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
  ErrorNote,
  Input,
  Label,
  Progress,
  Select,
  Spinner,
  Table,
  TD,
  Textarea,
  TH,
  Tabs,
} from "@/components/ui";
import {
  ConsentNotice,
  EmptyState,
  ScoreRing,
  SkillDiff,
  SyntheticTag,
  VerificationBadge,
} from "@/components/shared";
import { api, apiForm } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { pct } from "@/lib/utils";

type SkillRow = {
  id: string;
  skill_id: string;
  state: string;
  extracted_from_resume: boolean;
  code: string;
  label: string;
  category: string;
  demand_weight: number;
};

type Match = {
  match_id: string;
  job_description_id: string;
  title: string;
  kind: string;
  location: string;
  stipend: number | null;
  salary_min: number | null;
  salary_max: number | null;
  organization_name: string;
  score: number;
  semantic_score: number;
  taxonomy_score: number;
  provider: string;
  literal_keyword_overlap: number;
  matched_skills: any[];
  missing_skills: any[];
  extra_skills: any[];
  application_id: string | null;
  application_status: string | null;
};

type Gap = {
  role: string;
  readiness_pct: number;
  matched_skills: { skill_id: string; label: string; student_state: string; weight: number }[];
  missing_skills: { skill_id: string; label: string; weight: number }[];
  learning_path: {
    skill_id: string;
    label: string;
    priority_weight: number;
    est_hours: number;
    resources: { title: string; provider: string; url: string; duration_hours: number }[];
  }[];
  total_learning_hours: number;
};

export default function StudentPage() {
  return (
    <PageGuard role="student">
      <StudentView />
    </PageGuard>
  );
}

function StudentView() {
  const { user, refresh } = useAuth();
  const [tab, setTab] = useState("profile");
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const [profile, setProfile] = useState<any>(null);
  const [skills, setSkills] = useState<SkillRow[]>([]);
  const [streams, setStreams] = useState<{ key: string; name: string }[]>([]);
  const [roles, setRoles] = useState<string[]>([]);
  const [allSkills, setAllSkills] = useState<{ id: string; label: string; category: string }[]>([]);
  const [matches, setMatches] = useState<Match[]>([]);
  const [applications, setApplications] = useState<any[]>([]);
  const [gap, setGap] = useState<Gap | null>(null);
  const [gapRole, setGapRole] = useState("");
  const [provider, setProvider] = useState("");
  const [busy, setBusy] = useState(false);
  const [openMatch, setOpenMatch] = useState<string | null>(null);

  // profile form state
  const [resumeText, setResumeText] = useState("");
  const [stream, setStream] = useState("cse");
  const [cgpa, setCgpa] = useState("");
  const [gradYear, setGradYear] = useState("2026");
  const [file, setFile] = useState<File | null>(null);

  const loadProfile = useCallback(async () => {
    try {
      const res = await api<{ profile: any; skills: SkillRow[] }>("/student/profile");
      setProfile(res.profile);
      setSkills(res.skills);
      setStream(res.profile.stream);
      setResumeText(res.profile.resume_text || "");
      setCgpa(res.profile.cgpa ? String(res.profile.cgpa) : "");
      setGradYear(res.profile.graduation_year ? String(res.profile.graduation_year) : "2026");
    } catch (e: any) {
      if (e.status === 404) setProfile(null);
      else setError(e.message);
    }
  }, []);

  const loadMatches = useCallback(async () => {
    try {
      setMatches(await api<Match[]>("/student/matches"));
    } catch (e: any) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    api<{ key: string; name: string; target_roles: string[] }[]>("/meta/streams")
      .then((s) => {
        setStreams(s);
        if (s[0]) setRoles(s[0].target_roles);
      })
      .catch(() => {});
    api<{ provider: string }>("/meta/provider").then((r) => setProvider(r.provider)).catch(() => {});
  }, []);

  useEffect(() => {
    if (user) loadProfile();
  }, [user, loadProfile]);

  useEffect(() => {
    api<{ id: string; label: string; category: string }[]>(`/meta/skills?stream=${stream}`)
      .then(setAllSkills)
      .catch(() => {});
  }, [stream]);

  useEffect(() => {
    if (profile?.extraction_status === "extracted") {
      loadMatches();
      api("/student/applications").then(setApplications).catch(() => {});
      api(`/student/target-roles`)
        .then((r: any) => {
          setRoles(r.map((x: any) => x.name));
          if (r[0]) setGapRole(r[0].name);
        })
        .catch(() => {});
    }
  }, [profile?.extraction_status, loadMatches]);

  const loadGap = useCallback(async (role: string) => {
    if (!role) return;
    try {
      setGap(await api<Gap>(`/student/gap?role=${encodeURIComponent(role)}`));
    } catch (e: any) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    if (tab === "gap" && gapRole) loadGap(gapRole);
  }, [tab, gapRole, loadGap]);

  async function saveProfile() {
    setError(null);
    setBusy(true);
    try {
      const form = new FormData();
      form.append("resume_text", resumeText);
      form.append("stream", stream);
      if (cgpa) form.append("cgpa", cgpa);
      if (gradYear) form.append("graduation_year", gradYear);
      if (file) form.append("file", file);
      const res = await apiForm<{ matches_computed: number; extracted_count: number }>(
        "/student/profile",
        form
      );
      await loadProfile();
      await loadMatches();
      setToast(
        `Extracted ${res.extracted_count} skills · ${res.matches_computed} matches computed.`
      );
      setTab("skills");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function claimSkill(skillId: string) {
    try {
      await api("/student/skills", {
        method: "POST",
        body: JSON.stringify({ skill_id: skillId }),
      });
      await loadProfile();
      await loadMatches();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function removeSkill(id: string) {
    try {
      await api(`/student/skills/${id}`, { method: "DELETE" });
      await loadProfile();
      await loadMatches();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function apply(jobId: string) {
    setError(null);
    try {
      await api("/student/applications", {
        method: "POST",
        body: JSON.stringify({ job_description_id: jobId }),
      });
      await loadMatches();
      setApplications(await api("/student/applications"));
      setToast("Application submitted — the employer now sees your explainable profile.");
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function grantConsent() {
    try {
      await api("/student/consent", {
        method: "POST",
        body: JSON.stringify({ granted: true }),
      });
      await refresh();
    } catch (e: any) {
      setError(e.message);
    }
  }

  const consentGiven = user?.consent_given;
  const counts = {
    verified: skills.filter((s) => s.state === "verified").length,
    cosigned: skills.filter((s) => s.state === "institution_cosigned").length,
    claimed: skills.filter((s) => s.state === "claimed").length,
  };

  return (
    <AppShell
      title="Student workspace"
      subtitle="Upload once — get skill extraction, target-role gap, and explainable job matches."
    >
      <div className="mb-4 space-y-3">
        <ErrorNote message={error} onDismiss={() => setError(null)} />
        {toast && (
          <div className="flex items-center justify-between rounded-lg border border-emerald-200 bg-emerald-50 px-3.5 py-2.5 text-sm text-emerald-800">
            <span>✅ {toast}</span>
            <button onClick={() => setToast(null)} className="text-emerald-400">✕</button>
          </div>
        )}
        <ConsentNotice granted={!!consentGiven} />
        {!consentGiven && (
          <Button onClick={grantConsent} size="sm">
            🛡️ Grant DPDP consent
          </Button>
        )}
      </div>

      <Tabs
        tabs={[
          { key: "profile", label: "1 · Profile" },
          { key: "skills", label: "2 · Skills", count: skills.length },
          { key: "gap", label: "3 · Gap & learning" },
          { key: "matches", label: "4 · Matches", count: matches.length },
          { key: "applications", label: "5 · Applications", count: applications.length },
        ]}
        active={tab}
        onChange={setTab}
      />

      <div className="mt-4">
        {tab === "profile" && (
          <div className="grid gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader>
                <CardTitle>Resume / profile</CardTitle>
                <CardDescription>
                  Paste text or upload .pdf/.txt — skills are extracted locally
                  (taxonomy aliases + {provider === "fastembed" ? "MiniLM embeddings" : "TF-IDF"}), never by a live LLM.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <div>
                  <Label>Resume text</Label>
                  <Textarea
                    rows={10}
                    value={resumeText}
                    onChange={(e) => setResumeText(e.target.value)}
                    placeholder="Paste your resume text here…"
                    disabled={!consentGiven}
                  />
                </div>
                <div className="grid gap-3 sm:grid-cols-3">
                  <div>
                    <Label>Stream</Label>
                    <Select value={stream} onChange={(e) => setStream(e.target.value)}>
                      {streams.map((s) => (
                        <option key={s.key} value={s.key}>
                          {s.name}
                        </option>
                      ))}
                    </Select>
                  </div>
                  <div>
                    <Label>CGPA</Label>
                    <Input value={cgpa} onChange={(e) => setCgpa(e.target.value)} placeholder="8.2" disabled={!consentGiven} />
                  </div>
                  <div>
                    <Label>Graduation year</Label>
                    <Input value={gradYear} onChange={(e) => setGradYear(e.target.value)} disabled={!consentGiven} />
                  </div>
                </div>
                <div>
                  <Label>…or upload a file (.pdf, .txt)</Label>
                  <input
                    type="file"
                    accept=".pdf,.txt,.md"
                    onChange={(e) => setFile(e.target.files?.[0] || null)}
                    className="block w-full text-xs text-slate-500 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-100 file:px-3 file:py-2 file:text-xs file:font-medium"
                    disabled={!consentGiven}
                  />
                </div>
                <Button onClick={saveProfile} disabled={busy || !consentGiven}>
                  {busy ? <Spinner /> : profile ? "Re-process profile" : "Save & extract skills"}
                </Button>
              </CardContent>
            </Card>
            <div className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>Status</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  <Row k="Extraction" v={profile?.extraction_status || "not uploaded"} />
                  <Row k="Institution" v={profile?.institution_name || "—"} />
                  <Row k="Stream" v={profile?.stream || stream} />
                  <Row k="Skills claimed" v={String(skills.length)} />
                  <div className="flex gap-1.5 pt-1">
                    <Badge tone="green">● {counts.verified} verified</Badge>
                    <Badge tone="blue">◔ {counts.cosigned} co-signed</Badge>
                    <Badge tone="amber">○ {counts.claimed} claimed</Badge>
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="pt-4 text-xs leading-relaxed text-slate-500">
                  <SyntheticTag className="mb-2" />
                  <p>
                    Your institution name and the demo dataset are synthetic.
                    Verification states come from real role actions: TPO co-signs,
                    industry verifies.
                  </p>
                </CardContent>
              </Card>
            </div>
          </div>
        )}

        {tab === "skills" && (
          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Your skills & verification state</CardTitle>
                <CardDescription>
                  Claimed ≠ verified everywhere in the portal — badges drive match credit too.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {skills.length === 0 ? (
                  <EmptyState
                    icon="🧩"
                    title="No skills yet"
                    hint="Upload your resume in step 1 — extraction will claim skills for you — or add them manually from the catalogue."
                  />
                ) : (
                  <div className="space-y-1.5">
                    {skills.map((s) => (
                      <div
                        key={s.id}
                        className="flex items-center justify-between rounded-lg border border-slate-100 px-3 py-2"
                      >
                        <div>
                          <div className="text-sm font-medium text-slate-800">{s.label}</div>
                          <div className="text-[11px] text-slate-400">
                            {s.category} · demand weight {s.demand_weight?.toFixed(2)}
                            {s.extracted_from_resume && " · from resume"}
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <VerificationBadge state={s.state} />
                          {s.state === "claimed" && (
                            <Button variant="ghost" size="sm" onClick={() => removeSkill(s.id)}>
                              remove
                            </Button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Claim a skill manually</CardTitle>
                <CardDescription>From the {stream.toUpperCase()} taxonomy (config-driven).</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="max-h-96 space-y-1 overflow-y-auto pr-1">
                  {allSkills
                    .filter((a) => !skills.some((s) => s.skill_id === a.id))
                    .map((a) => (
                      <div
                        key={a.id}
                        className="flex items-center justify-between rounded-lg border border-slate-100 px-3 py-1.5"
                      >
                        <div>
                          <span className="text-sm text-slate-700">{a.label}</span>
                          <span className="ml-2 text-[11px] text-slate-400">{a.category}</span>
                        </div>
                        <Button variant="subtle" size="sm" onClick={() => claimSkill(a.id)}>
                          claim
                        </Button>
                      </div>
                    ))}
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {tab === "gap" && (
          <div className="space-y-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle>Skill gap vs target role</CardTitle>
                  <CardDescription>Weights come from the stream config + recalibrated demand.</CardDescription>
                </div>
                <div className="flex w-72 items-center gap-2">
                  <Select value={gapRole} onChange={(e) => setGapRole(e.target.value)}>
                    {roles.map((r) => (
                      <option key={r}>{r}</option>
                    ))}
                  </Select>
                  <Button size="sm" variant="outline" onClick={() => loadGap(gapRole)}>
                    Compute
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                {!gap ? (
                  <EmptyState
                    icon="🎯"
                    title="Pick a target role"
                    hint="Choose a role and hit Compute — readiness is demand-weighted and accounts for verification state."
                  />
                ) : (
                  <div className="space-y-4">
                    <div className="flex flex-wrap items-center gap-4">
                      <ScoreRing score={gap.readiness_pct} size={84} />
                      <div className="flex-1">
                        <div className="text-sm font-semibold text-slate-800">
                          {gap.role} readiness
                        </div>
                        <Progress
                          value={gap.readiness_pct}
                          className="mt-2 max-w-md"
                          barClassName={
                            gap.readiness_pct >= 65
                              ? "bg-emerald-500"
                              : gap.readiness_pct >= 40
                              ? "bg-amber-500"
                              : "bg-rose-500"
                          }
                        />
                        <div className="mt-1.5 flex flex-wrap gap-1.5">
                          {gap.matched_skills.map((m) => (
                            <span key={m.skill_id} className="inline-flex items-center gap-1 rounded-lg bg-emerald-50 px-2 py-0.5 text-xs text-emerald-700">
                              {m.label} <VerificationBadge state={m.student_state} />
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                    <div>
                      <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                        Recommended learning path ({gap.total_learning_hours}h total)
                      </h4>
                      {gap.learning_path.length === 0 ? (
                        <div className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
                          🎉 No gaps — you cover every required skill for this role.
                        </div>
                      ) : (
                        <div className="space-y-2">
                          {gap.learning_path.map((p, i) => (
                            <div key={p.skill_id} className="rounded-lg border border-slate-200 p-3">
                              <div className="flex items-center gap-2">
                                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-brand-100 text-[11px] font-bold text-brand-700">
                                  {i + 1}
                                </span>
                                <span className="text-sm font-medium text-slate-800">{p.label}</span>
                                <Badge tone="red">priority {p.priority_weight.toFixed(1)}</Badge>
                                <span className="ml-auto text-[11px] text-slate-400">~{p.est_hours}h</span>
                              </div>
                              <div className="mt-2 flex flex-wrap gap-1.5">
                                {p.resources.map((r) => (
                                  <a
                                    key={r.url}
                                    href={r.url}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="inline-flex items-center gap-1 rounded-lg bg-slate-100 px-2 py-1 text-xs text-slate-700 hover:bg-slate-200"
                                  >
                                    📚 {r.title} <span className="text-slate-400">· {r.provider}</span>
                                  </a>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}

        {tab === "matches" && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-xs text-slate-500">
                Score = 55% semantic (pgvector cosine) + 45% taxonomy coverage (verification-weighted).
              </p>
              <Button
                size="sm"
                variant="outline"
                onClick={async () => {
                  const r = await api("/student/matches/refresh", { method: "POST" });
                  await loadMatches();
                  setToast(`Recomputed ${r.matches_computed} matches.`);
                }}
              >
                ↻ Refresh matches
              </Button>
            </div>
            {matches.length === 0 ? (
              <EmptyState
                icon="🧭"
                title="No matches yet"
                hint="Upload your resume (step 1) so the engine can rank open jobs semantically. Cold-start is expected until then."
              />
            ) : (
              matches.map((m) => (
                <Card key={m.match_id}>
                  <CardContent>
                    <div className="flex flex-wrap items-center gap-4">
                      <ScoreRing score={m.score} />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="font-semibold text-slate-900">{m.title}</h3>
                          <Badge tone={m.kind === "placement" ? "purple" : "brand"}>{m.kind}</Badge>
                          <SyntheticTag />
                        </div>
                        <div className="mt-0.5 text-xs text-slate-500">
                          {m.organization_name} · {m.location} ·{" "}
                          {m.stipend ? `₹${m.stipend}/mo` : m.salary_min ? `₹${(m.salary_min / 100000).toFixed(1)}–${(m.salary_max! / 100000).toFixed(1)} LPA` : "—"}
                          {" · "}
                          semantic {m.semantic_score.toFixed(0)} / taxonomy {m.taxonomy_score.toFixed(0)} / keywords {pct(m.literal_keyword_overlap)}
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => setOpenMatch(openMatch === m.match_id ? null : m.match_id)}
                        >
                          {openMatch === m.match_id ? "Hide" : "Why?"}
                        </Button>
                        {m.application_id ? (
                          <Badge tone="green">applied · {m.application_status}</Badge>
                        ) : (
                          <Button size="sm" onClick={() => apply(m.job_description_id)}>
                            Apply
                          </Button>
                        )}
                      </div>
                    </div>
                    {openMatch === m.match_id && (
                      <div className="mt-4 border-t border-slate-100 pt-4">
                        <SkillDiff match={m} />
                      </div>
                    )}
                  </CardContent>
                </Card>
              ))
            )}
          </div>
        )}

        {tab === "applications" && (
          <Card>
            <CardContent>
              {applications.length === 0 ? (
                <EmptyState
                  icon="📨"
                  title="No applications yet"
                  hint="Apply from the Matches tab — outcomes logged by industry will recalibrate skill demand weights."
                />
              ) : (
                <Table>
                  <thead>
                    <tr>
                      <TH>Role</TH>
                      <TH>Organization</TH>
                      <TH>Match</TH>
                      <TH>Status</TH>
                      <TH>Applied</TH>
                    </tr>
                  </thead>
                  <tbody>
                    {applications.map((a) => (
                      <tr key={a.id}>
                        <TD>
                          <span className="font-medium text-slate-800">{a.title}</span>
                          <div className="text-[11px] text-slate-400">{a.kind}</div>
                        </TD>
                        <TD>{a.organization_name}</TD>
                        <TD>{a.score != null ? a.score.toFixed(1) : "—"}</TD>
                        <TD>
                          <Badge
                            tone={
                              a.status === "selected" ? "green" : a.status === "rejected" ? "red" : "blue"
                            }
                          >
                            {a.status}
                          </Badge>
                        </TD>
                        <TD className="text-xs text-slate-400">
                          {new Date(a.applied_at).toLocaleDateString()}
                        </TD>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </AppShell>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-xs text-slate-400">{k}</span>
      <span className="text-xs font-medium text-slate-700">{v}</span>
    </div>
  );
}
