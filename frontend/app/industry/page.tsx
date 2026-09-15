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
  Textarea,
} from "@/components/ui";
import {
  EmptyState,
  ScoreRing,
  SkillDiff,
  SyntheticTag,
  VerificationBadge,
} from "@/components/shared";
import { api } from "@/lib/api";

type Job = {
  id: string;
  title: string;
  kind: string;
  stream: string;
  status: string;
  location: string | null;
  stipend: number | null;
  salary_min: number | null;
  salary_max: number | null;
  seats: number;
  created_at: string;
  extracted_skills: { code: string; label: string; weight: number }[];
  applicant_count: number;
};

type Applicant = {
  application_id: string;
  status: string;
  applied_at: string;
  cover_note: string | null;
  student_profile_id: string;
  full_name: string;
  institution_name: string | null;
  cgpa: number | null;
  stream: string;
  degree?: string | null;
  job_description_id: string;
  job_title: string;
  job_kind: string;
  is_hired?: boolean;
  outcome_result?: string | null;
  match_id: string | null;
  score: number | null;
  semantic_score: number | null;
  taxonomy_score: number | null;
  provider: string | null;
  matched_skills: any[];
  missing_skills: any[];
  extra_skills: any[];
  literal_keyword_overlap: number | null;
  outcome_id?: string | null;
};

type Summary = {
  total: number;
  hired: number;
  waitlisted: number;
  rejected: number;
  in_process: number;
  withdrawn: number;
  by_status: Record<string, number>;
};

// Hiring buckets derived from the authoritative applications.status +
// outcomes.result. In-flight states (applied/shortlisted) stay visible as
// IN PROCESS -- never silently folded into a decision bucket.
type Bucket = "hired" | "waitlisted" | "rejected" | "in_process" | "withdrawn";

const BUCKET_META: Record<Bucket, { label: string; cls: string }> = {
  hired: { label: "HIRED", cls: "bg-emerald-100 text-emerald-800 ring-emerald-300" },
  waitlisted: { label: "WAITLISTED", cls: "bg-amber-100 text-amber-800 ring-amber-300" },
  rejected: { label: "REJECTED", cls: "bg-red-100 text-red-700 ring-red-300" },
  in_process: { label: "IN PROCESS", cls: "bg-blue-50 text-blue-700 ring-blue-200" },
  withdrawn: { label: "WITHDRAWN", cls: "bg-slate-100 text-slate-600 ring-slate-300" },
};

function bucketOf(a: Applicant): Bucket {
  if (a.is_hired || a.status === "selected") return "hired";
  if (a.status === "waitlisted") return "waitlisted";
  if (a.status === "rejected") return "rejected";
  return a.status === "withdrawn" ? "withdrawn" : "in_process";
}

function StatusChip({ bucket, note }: { bucket: Bucket; note?: string | null }) {
  const m = BUCKET_META[bucket];
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-bold ring-1 ring-inset ${m.cls}`}>
      {m.label}
      {note ? <span className="font-medium opacity-70">· {note}</span> : null}
    </span>
  );
}

function StatusCard({
  label, count, hint, tone, icon, active, onClick,
}: {
  label: string; count: number; hint: string; tone: "green" | "amber" | "red" | "blue";
  icon: string; active: boolean; onClick: () => void;
}) {
  const toneCls = {
    green: "border-emerald-200 bg-emerald-50 text-emerald-900",
    amber: "border-amber-200 bg-amber-50 text-amber-900",
    red: "border-red-200 bg-red-50 text-red-900",
    blue: "border-blue-200 bg-blue-50 text-blue-900",
  }[tone];
  return (
    <button
      onClick={onClick}
      title={`Filter candidates: ${label}`}
      className={`rounded-xl border p-4 text-left transition ${toneCls} ${
        active ? "ring-2 ring-slate-400 ring-offset-1" : "hover:shadow-sm"
      }`}
    >
      <div className="text-xs font-bold uppercase tracking-wide">{icon} {label}</div>
      <div className="mt-1 text-3xl font-extrabold">{count}</div>
      <div className="mt-0.5 text-[11px] opacity-70">{hint}</div>
    </button>
  );
}

// Only statuses the backend's /industry/applications/{id}/status accepts.
function recruitActions(a: Applicant): { label: string; status: string; variant?: string }[] {
  const b = bucketOf(a);
  if (b === "hired")
    return [
      { label: "Move to Waitlist", status: "waitlisted" },
      { label: "Reject", status: "rejected", variant: "danger" },
    ];
  if (b === "waitlisted")
    return [
      { label: "Mark as Hired", status: "selected" },
      { label: "Reject", status: "rejected", variant: "danger" },
    ];
  if (b === "rejected")
    return [
      { label: "Move to Waitlist", status: "waitlisted" },
      { label: "Mark as Hired", status: "selected" },
    ];
  if (b === "withdrawn") return [];
  return [
    { label: "Shortlist", status: "shortlisted", variant: "outline" },
    { label: "Move to Waitlist", status: "waitlisted" },
    { label: "Mark as Hired", status: "selected" },
    { label: "Reject", status: "rejected", variant: "danger" },
  ];
}

const RESULT_TONES: Record<string, "green" | "red" | "slate"> = {
  hired: "green",
  completed: "slate",
  dropped: "red",
};

export default function IndustryPage() {
  return (
    <PageGuard role="industry">
      <IndustryView />
    </PageGuard>
  );
}

function IndustryView() {
  const [tab, setTab] = useState("hiring");
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [streams, setStreams] = useState<any[]>([]);
  const [openApplicants, setOpenApplicants] = useState<string | null>(null);
  const [applicants, setApplicants] = useState<Applicant[]>([]);
  const [openDiff, setOpenDiff] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [studentSkills, setStudentSkills] = useState<any[] | null>(null);

  // hiring-status view
  const [summary, setSummary] = useState<Summary | null>(null);
  const [recruits, setRecruits] = useState<Applicant[] | null>(null);
  const [recruitFilter, setRecruitFilter] = useState("all");
  const [recruitLoading, setRecruitLoading] = useState(true);
  const [recruitError, setRecruitError] = useState<string | null>(null);

  // post-job form
  const [form, setForm] = useState({
    title: "",
    kind: "internship",
    stream: "cse",
    location: "Bengaluru",
    stipend: "20000",
    seats: "2",
    description: "",
  });
  const [lastExtraction, setLastExtraction] = useState<{
    provider?: string;
    skills: any[];
  } | null>(null);

  const loadJobs = useCallback(async () => {
    try {
      setJobs(await api<Job[]>("/industry/jobs"));
    } catch (e: any) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    loadJobs();
    api("/meta/streams").then(setStreams).catch(() => {});
  }, [loadJobs]);

  const loadRecruitment = useCallback(async () => {
    setRecruitLoading(true);
    setRecruitError(null);
    try {
      const [s, rows] = await Promise.all([
        api<Summary>("/industry/recruitment/summary"),
        api<Applicant[]>("/industry/applicants"),
      ]);
      setSummary(s);
      setRecruits(rows);
    } catch (e: any) {
      setRecruitError(e.message);
    } finally {
      setRecruitLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRecruitment();
  }, [loadRecruitment]);

  async function postJob() {
    setError(null);
    setBusy(true);
    try {
      const res = await api<any>("/industry/jobs", {
        method: "POST",
        body: JSON.stringify({
          title: form.title,
          kind: form.kind,
          stream: form.stream,
          location: form.location,
          stipend: form.stipend ? Number(form.stipend) : null,
          seats: Number(form.seats) || 1,
          description: form.description,
        }),
      });
      setLastExtraction({ provider: res.provider, skills: res.skills });
      setToast(
        `JD posted — extracted ${res.extracted_count} skills (${res.provider}); ` +
          `${res.students_matched} students ranked against it.`
      );
      setForm({ ...form, title: "", description: "" });
      await loadJobs();
      setTab("jobs");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function showApplicants(jobId: string) {
    if (openApplicants === jobId) {
      setOpenApplicants(null);
      return;
    }
    try {
      const rows = await api<Applicant[]>(`/industry/jobs/${jobId}/applicants`);
      setApplicants(rows);
      setOpenApplicants(jobId);
      setOpenDiff(null);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function setStatus(appId: string, status: string) {
    try {
      await api(`/industry/applications/${appId}/status`, {
        method: "POST",
        body: JSON.stringify({ status }),
      });
      if (openApplicants) showApplicants(openApplicants);
      loadRecruitment(); // database updated first; refresh cards + table
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function logOutcome(appId: string, result: string, rating: number | null) {
    setError(null);
    try {
      const r = await api<any>("/industry/outcomes", {
        method: "POST",
        body: JSON.stringify({
          application_id: appId,
          result,
          performance_rating: rating,
          industry_feedback: "Logged via industry console",
        }),
      });
      const changes = r.weight_changes || [];
      setToast(
        `Outcome logged → recalibration: ${changes.length} skill demand weights updated ` +
          `(${changes.map((c: any) => `${c.code} ${c.old_weight.toFixed(2)}→${c.new_weight.toFixed(2)}`).join(", ") || "no changes"}) · ` +
          `${r.curriculum_signals_regenerated} curriculum signals regenerated for the student's institution.`
      );
      if (openApplicants) showApplicants(openApplicants);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function verifySkill(studentSkillId: string) {
    try {
      const r = await api("/industry/verify-skill", {
        method: "POST",
        body: JSON.stringify({ student_skill_id: studentSkillId, note: "Verified in interview" }),
      });
      setToast(r.note);
      if (openApplicants) showApplicants(openApplicants);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function loadStudentSkills(profileId: string) {
    try {
      setStudentSkills(await api(`/industry/students/${profileId}/skills`));
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <AppShell
      title="Industry console"
      subtitle="Post roles, review explainable applicant rankings, verify skills, log outcomes."
    >
      <div className="mb-4 space-y-3">
        <ErrorNote message={error} onDismiss={() => setError(null)} />
        {toast && (
          <div className="flex items-start justify-between gap-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3.5 py-2.5 text-sm text-emerald-800">
            <span>🔁 {toast}</span>
            <button onClick={() => setToast(null)} className="text-emerald-400">✕</button>
          </div>
        )}
      </div>

      <Tabs
        tabs={[
          { key: "hiring", label: "Hiring status" },
          { key: "jobs", label: "My jobs", count: jobs.length },
          { key: "post", label: "Post a job" },
        ]}
        active={tab}
        onChange={setTab}
      />

      <div className="mt-4">
        {tab === "hiring" && (
          <div className="space-y-4">
            {recruitLoading && !summary ? (
              <Card>
                <CardContent className="flex items-center justify-center gap-3 py-10 text-sm text-slate-500">
                  <Spinner /> Loading recruitment data...
                </CardContent>
              </Card>
            ) : recruitError ? (
              <Card>
                <CardContent className="py-10 text-center">
                  <p className="text-sm font-semibold text-slate-700">Unable to load recruitment data.</p>
                  <p className="mt-1 text-xs text-slate-500">{recruitError}</p>
                  <div className="mt-3 flex justify-center">
                    <Button variant="outline" size="sm" onClick={loadRecruitment}>Try again</Button>
                  </div>
                </CardContent>
              </Card>
            ) : summary && (
              <>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <StatusCard icon="🎯" label="Hired" count={summary.hired} hint="Successfully hired"
                    tone="green" active={recruitFilter === "hired"}
                    onClick={() => setRecruitFilter(recruitFilter === "hired" ? "all" : "hired")} />
                  <StatusCard icon="⏳" label="Waitlisted" count={summary.waitlisted} hint="Waiting for decision"
                    tone="amber" active={recruitFilter === "waitlisted"}
                    onClick={() => setRecruitFilter(recruitFilter === "waitlisted" ? "all" : "waitlisted")} />
                  <StatusCard icon="✕" label="Rejected" count={summary.rejected} hint="Not selected"
                    tone="red" active={recruitFilter === "rejected"}
                    onClick={() => setRecruitFilter(recruitFilter === "rejected" ? "all" : "rejected")} />
                  <StatusCard icon="⟳" label="In process" count={summary.in_process} hint="Applied / shortlisted — decision pending"
                    tone="blue" active={recruitFilter === "in_process"}
                    onClick={() => setRecruitFilter(recruitFilter === "in_process" ? "all" : "in_process")} />
                </div>
                {summary.withdrawn > 0 && (
                  <p className="text-xs text-slate-500">{summary.withdrawn} application(s) withdrawn by students are excluded from the decision buckets.</p>
                )}

                <div className="flex flex-wrap items-center gap-2">
                  {([
                    { key: "all", label: "All", n: summary.total },
                    { key: "hired", label: "Hired", n: summary.hired },
                    { key: "waitlisted", label: "Waitlisted", n: summary.waitlisted },
                    { key: "rejected", label: "Rejected", n: summary.rejected },
                    { key: "in_process", label: "In process", n: summary.in_process },
                  ] as const).map((f) => (
                    <button
                      key={f.key}
                      onClick={() => setRecruitFilter(f.key)}
                      className={`rounded-full px-3 py-1 text-xs font-semibold ring-1 ring-inset transition ${
                        recruitFilter === f.key
                          ? "bg-slate-900 text-white ring-slate-900"
                          : "bg-white text-slate-600 ring-slate-200 hover:bg-slate-50"
                      }`}
                    >
                      {f.label} <span className="opacity-70">{f.n}</span>
                    </button>
                  ))}
                </div>

                <Card>
                  <CardContent className="pt-4">
                    {!recruits || recruits.length === 0 ? (
                      <EmptyState
                        icon="🧑‍💼"
                        title="No candidates found."
                        hint="Applicants from every job your organization has posted will appear here."
                      />
                    ) : (() => {
                      const filtered = recruits.filter(
                        (a) => recruitFilter === "all" || bucketOf(a) === recruitFilter
                      );
                      if (filtered.length === 0) {
                        const hints: Record<string, string> = {
                          hired: "No candidates have been hired yet.",
                          waitlisted: "No waitlisted candidates.",
                          rejected: "No rejected candidates.",
                          in_process: "No candidates in process right now.",
                        };
                        return <EmptyState icon="🗂️" title={hints[recruitFilter] || "No candidates found."} hint="Switch filters to see other candidates." />;
                      }
                      return (
                        <Table>
                          <thead>
                            <tr>
                              <TH>Candidate</TH>
                              <TH>Degree</TH>
                              <TH>Stream</TH>
                              <TH>Skills</TH>
                              <TH>Applied Role</TH>
                              <TH>Applied Date</TH>
                              <TH>Status</TH>
                              <TH>Actions</TH>
                            </tr>
                          </thead>
                          <tbody>
                            {filtered.map((a) => {
                              const b = bucketOf(a);
                              const matched = a.matched_skills?.length;
                              const missing = a.missing_skills?.length ?? 0;
                              return (
                                <tr key={a.application_id} className="border-t border-slate-100 align-top">
                                  <TD>
                                    <div className="font-semibold text-slate-900">{a.full_name}</div>
                                    <div className="text-xs text-slate-500">{a.institution_name || "—"}{a.cgpa != null ? ` · CGPA ${a.cgpa}` : ""}</div>
                                  </TD>
                                  <TD className="text-xs text-slate-600">{a.degree || "—"}</TD>
                                  <TD className="text-xs text-slate-600">{a.stream?.toUpperCase()}</TD>
                                  <TD className="text-xs text-slate-600">
                                    {matched != null ? (
                                      <span title={`${matched} matched / ${missing} missing`}>{matched} / {matched + missing}</span>
                                    ) : "—"}
                                  </TD>
                                  <TD>
                                    <div className="text-sm font-medium text-slate-800">{a.job_title}</div>
                                    <div className="text-xs text-slate-500">{a.job_kind}{a.score != null ? ` · match ${a.score.toFixed(0)}` : ""}</div>
                                  </TD>
                                  <TD className="text-xs text-slate-600">{new Date(a.applied_at).toLocaleDateString()}</TD>
                                  <TD><StatusChip bucket={b} note={b === "hired" && a.outcome_result === "hired" ? "outcome" : null} /></TD>
                                  <TD>
                                    <div className="flex flex-wrap gap-1">
                                      {recruitActions(a).map((act) => (
                                        <Button key={act.status} size="sm" variant={(act.variant as any) || "subtle"}
                                          onClick={() => setStatus(a.application_id, act.status)}>
                                          {act.label}
                                        </Button>
                                      ))}
                                    </div>
                                  </TD>
                                </tr>
                              );
                            })}
                          </tbody>
                        </Table>
                      );
                    })()}
                  </CardContent>
                </Card>
              </>
            )}
          </div>
        )}

        {tab === "jobs" && (
          <div className="space-y-3">
            {jobs.length === 0 ? (
              <EmptyState
                icon="🏢"
                title="No jobs posted yet (cold start)"
                hint="Post your first role — the engine extracts skills from your description instantly and ranks every student in the stream with a full explainability payload."
                action={<Button onClick={() => setTab("post")}>Post your first job</Button>}
              />
            ) : (
              jobs.map((j) => (
                <Card key={j.id}>
                  <CardContent>
                    <div className="flex flex-wrap items-center gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="font-semibold text-slate-900">{j.title}</h3>
                          <Badge tone={j.kind === "placement" ? "purple" : "brand"}>{j.kind}</Badge>
                          <Badge tone={j.status === "open" ? "green" : "slate"}>{j.status}</Badge>
                          <SyntheticTag />
                        </div>
                        <div className="mt-0.5 text-xs text-slate-500">
                          {j.stream.toUpperCase()} · {j.location || "—"} ·{" "}
                          {j.stipend ? `₹${j.stipend}/mo` : j.salary_min ? `₹${(j.salary_min / 100000).toFixed(1)}–${(j.salary_max! / 100000).toFixed(1)} LPA` : "—"}{" "}
                          · {j.seats} seats · posted {new Date(j.created_at).toLocaleDateString()}
                        </div>
                        <div className="mt-1.5 flex flex-wrap gap-1">
                          {(j.extracted_skills || []).slice(0, 8).map((s) => (
                            <span key={s.code} className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">
                              {s.label}
                            </span>
                          ))}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge tone={j.applicant_count > 0 ? "blue" : "slate"}>
                          {j.applicant_count} applicant{j.applicant_count === 1 ? "" : "s"}
                        </Badge>
                        <Button variant="outline" size="sm" onClick={() => showApplicants(j.id)}>
                          {openApplicants === j.id ? "Hide" : "Applicants"}
                        </Button>
                      </div>
                    </div>

                    {openApplicants === j.id && (
                      <div className="mt-4 border-t border-slate-100 pt-4">
                        {applicants.length === 0 ? (
                          <EmptyState icon="🧑‍💻" title="No applicants yet" hint="Students see this role ranked in their Matches tab." />
                        ) : (
                          <div className="space-y-3">
                            {applicants.map((a, rank) => (
                              <div key={a.application_id} className="rounded-xl border border-slate-200 p-3.5">
                                <div className="flex flex-wrap items-center gap-4">
                                  <div className="flex items-center gap-1">
                                    <span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-100 text-xs font-bold text-slate-500">
                                      {rank + 1}
                                    </span>
                                    <ScoreRing score={a.score || 0} size={52} />
                                  </div>
                                  <div className="min-w-0 flex-1">
                                    <div className="flex flex-wrap items-center gap-2">
                                      <span className="font-semibold text-slate-900">{a.full_name}</span>
                                      <Badge>{a.institution_name || "—"}</Badge>
                                      <Badge tone={a.status === "selected" ? "green" : a.status === "rejected" ? "red" : a.status === "shortlisted" ? "blue" : "slate"}>
                                        {a.status}
                                      </Badge>
                                      {a.outcome_id && <Badge tone="purple">outcome logged</Badge>}
                                    </div>
                                    <div className="mt-0.5 text-xs text-slate-500">
                                      CGPA {a.cgpa ?? "—"} · sem {a.semantic_score?.toFixed(0)} / tax {a.taxonomy_score?.toFixed(0)} / kw{" "}
                                      {a.literal_keyword_overlap?.toFixed(0)}% · {a.provider} ·{" "}
                                      {a.matched_skills?.length} matched / {a.missing_skills?.length} missing
                                    </div>
                                    {a.cover_note && (
                                      <div className="mt-1 rounded bg-amber-50 px-2 py-1 text-xs italic text-amber-700">
                                        “{a.cover_note}”
                                      </div>
                                    )}
                                  </div>
                                  <div className="flex flex-wrap gap-1.5">
                                    <Button size="sm" variant="outline" onClick={() => setOpenDiff(openDiff === a.application_id ? null : a.application_id)}>
                                      {openDiff === a.application_id ? "Hide diff" : "Skill diff"}
                                    </Button>
                                    {a.status === "applied" && (
                                      <Button size="sm" variant="subtle" onClick={() => setStatus(a.application_id, "shortlisted")}>
                                        Shortlist
                                      </Button>
                                    )}
                                    {a.status !== "selected" && a.status !== "rejected" && (
                                      <Button size="sm" onClick={() => setStatus(a.application_id, "selected")}>
                                        Select
                                      </Button>
                                    )}
                                    {a.status !== "rejected" && a.status !== "selected" && (
                                      <Button size="sm" variant="danger" onClick={() => setStatus(a.application_id, "rejected")}>
                                        Reject
                                      </Button>
                                    )}
                                  </div>
                                </div>

                                {openDiff === a.application_id && (
                                  <div className="mt-3 border-t border-slate-100 pt-3">
                                    <SkillDiff match={a as any} />
                                    <div className="mt-3 flex flex-wrap items-center gap-2">
                                      <Button
                                        size="sm"
                                        variant="outline"
                                        onClick={() => loadStudentSkills(a.student_profile_id)}
                                      >
                                        🔎 Load skill ledger (verify/co-sign states)
                                      </Button>
                                      {!a.outcome_id && (
                                        <>
                                          <span className="text-xs font-medium text-slate-500">Log outcome:</span>
                                          <Button size="sm" variant="success" onClick={() => logOutcome(a.application_id, "completed", 5)}>
                                            Completed ★5
                                          </Button>
                                          <Button size="sm" variant="subtle" onClick={() => logOutcome(a.application_id, "completed", 3)}>
                                            Completed ★3
                                          </Button>
                                          <Button size="sm" variant="subtle" onClick={() => logOutcome(a.application_id, "hired", 4)}>
                                            Hired ★4
                                          </Button>
                                          <Button size="sm" variant="danger" onClick={() => logOutcome(a.application_id, "dropped", 2)}>
                                            Dropped ★2
                                          </Button>
                                        </>
                                      )}
                                    </div>
                                    {studentSkills && (
                                      <div className="mt-3 rounded-lg bg-slate-50 p-3">
                                        <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                                          Verification ledger — co-signed skills can be verified by you
                                        </div>
                                        <div className="flex flex-wrap gap-1.5">
                                          {studentSkills.map((s) => (
                                            <span key={s.id} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs">
                                              {s.label} <VerificationBadge state={s.state} />
                                              {s.state === "institution_cosigned" && (
                                                <button
                                                  onClick={() => verifySkill(s.id)}
                                                  className="ml-1 rounded bg-brand-600 px-1.5 py-0.5 text-[10px] font-semibold text-white hover:bg-brand-700"
                                                >
                                                  verify
                                                </button>
                                              )}
                                            </span>
                                          ))}
                                        </div>
                                      </div>
                                    )}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </CardContent>
                </Card>
              ))
            )}
          </div>
        )}

        {tab === "post" && (
          <div className="grid gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <CardHeader>
                <CardTitle>Post a job / internship</CardTitle>
                <CardDescription>
                  Describe the work naturally — skill extraction (aliases +{" "}
                  {lastExtraction?.provider || "local embeddings"}) runs on save, then every student in the
                  stream gets ranked with a full explainability payload.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <Label>Job title</Label>
                    <Input
                      value={form.title}
                      onChange={(e) => setForm({ ...form, title: e.target.value })}
                      placeholder="e.g. Backend Engineer Intern"
                    />
                  </div>
                  <div>
                    <Label>Type</Label>
                    <Select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
                      <option value="internship">Internship</option>
                      <option value="placement">Placement (full-time)</option>
                    </Select>
                  </div>
                  <div>
                    <Label>Stream</Label>
                    <Select value={form.stream} onChange={(e) => setForm({ ...form, stream: e.target.value })}>
                      {streams.map((s) => (
                        <option key={s.key} value={s.key}>
                          {s.name}
                        </option>
                      ))}
                    </Select>
                  </div>
                  <div>
                    <Label>Location</Label>
                    <Input value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} />
                  </div>
                  <div>
                    <Label>Monthly stipend (₹, internships)</Label>
                    <Input value={form.stipend} onChange={(e) => setForm({ ...form, stipend: e.target.value })} />
                  </div>
                  <div>
                    <Label>Seats</Label>
                    <Input value={form.seats} onChange={(e) => setForm({ ...form, seats: e.target.value })} />
                  </div>
                </div>
                <div>
                  <Label>Role description (write naturally)</Label>
                  <Textarea
                    rows={7}
                    value={form.description}
                    onChange={(e) => setForm({ ...form, description: e.target.value })}
                    placeholder="e.g. You will build REST APIs in Python, write SQL against Postgres, ship Docker images to our AWS cluster…"
                  />
                </div>
                <Button onClick={postJob} disabled={busy || !form.title || form.description.length < 40}>
                  {busy ? <Spinner /> : "Post & rank students"}
                </Button>
              </CardContent>
            </Card>
            <div className="space-y-4">
                  {lastExtraction && (
                <Card>
                  <CardHeader>
                    <CardTitle>Last extraction result</CardTitle>
                    <CardDescription>Skills mapped to the taxonomy with demand weights.</CardDescription>
                  </CardHeader>
                  <CardContent className="flex flex-wrap gap-1.5">
                    {lastExtraction?.skills?.map((s: any) => (
                      <span key={s.code} className="rounded-lg border border-slate-200 bg-slate-50 px-2 py-1 text-xs text-slate-700">
                        {s.label} <span className="text-slate-400">w {s.weight?.toFixed(2)}</span>
                      </span>
                    ))}
                  </CardContent>
                </Card>
              )}
              <Card>
                <CardContent className="pt-4 text-xs leading-relaxed text-slate-500">
                  <strong className="text-slate-700">How scoring works</strong>
                  <p className="mt-1">
                    Overall = 55% semantic (pgvector cosine between local MiniLM embeddings) + 45% taxonomy
                    coverage of your JD's skills, weighted by demand. Verified skills earn full credit;
                    claimed-only skills earn 70%. Outcomes you log later reweight the taxonomy itself.
                  </p>
                </CardContent>
              </Card>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
