import { useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { get, patch, post } from "../../api/client";
import type { Initiative, Paged, Report } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { AuthAudio, AuthImg } from "../../components/AuthMedia";
import { PageHeader } from "../../components/Shell";
import { DemoBadge, Dialog, EmptyState, ErrorState, Field, Loading, StatusBadge, useAction } from "../../components/ui";
import { formatDate, num, timeAgo } from "../../lib/format";
import { useLoad } from "../../lib/hooks";
import { useI18n } from "../../lib/i18n";

export function ReportTable({ rows, base = "/staff/reports" }: { rows: Report[]; base?: string }) {
  const { tr, lang } = useI18n();
  const nav = useNavigate();
  if (!rows.length) return <EmptyState icon="check" title={tr("القائمة فارغة", "Queue is empty")}>{tr("لا شيء يحتاج إجراء هنا الآن.", "Nothing needs action here right now.")}</EmptyState>;
  return (
    <div className="table-wrap">
      <table className="data">
        <thead><tr><th>{tr("رقم المتابعة", "Tracking")}</th><th>{tr("الفئة", "Category")}</th><th>{tr("الحالة", "Status")}</th><th>{tr("المنطقة", "Area")}</th>
          <th>{tr("الجهة", "Agency")}</th><th>{tr("الأولوية", "Priority")}</th><th>{tr("أُرسل", "Submitted")}</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="clickable" onClick={() => nav(`${base}/${r.id}`)}>
              <td><Link to={`${base}/${r.id}`} onClick={(e) => e.stopPropagation()}><bdi>{r.tracking_number}</bdi></Link> <DemoBadge show={r.is_demo} /></td>
              <td>{r.category.name}</td>
              <td><StatusBadge status={r.status} />{r.routing_status === "needs_review" && <span className="badge s-wait" style={{ marginInlineStart: 4 }}>{tr("توجيه", "Routing")}</span>}</td>
              <td>{r.area_name ?? "—"}</td><td>{r.agency_name ?? "—"}</td>
              <td className="num">{Math.round(r.priority_score)}</td><td>{timeAgo(r.submitted_at, lang)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Dashboard() {
  const { tr, lang } = useI18n();
  const { data, error, loading, reload } = useLoad<{ by_status: Record<string, number>; by_category: { category__name_ar: string; n: number }[]; routing_review: number; total: number; demo: number }>("/reports/stats/");
  if (loading && !data) return <Loading lines={6} />;
  if (error && !data) return <ErrorState error={error} onRetry={reload} />;
  const s = data!;
  const q = (k: string) => s.by_status[k] ?? 0;
  const cards: [string, number, string][] = [
    [tr("بانتظار المراجعة", "Awaiting review"), q("submitted") + q("under_review") + q("reopened"), "/staff/queue?queue=review"],
    [tr("توجيه يحتاج قرار", "Routing decisions"), s.routing_review, "/staff/queue?queue=routing"],
    [tr("جاهزة للإحالة", "Ready to refer"), q("verified"), "/staff/queue?queue=to_refer"],
    [tr("إنجاز بانتظار التحقق", "Done, verify"), q("done_pending_verification"), "/staff/queue?queue=verify_done"],
    [tr("اعتراضات", "Disputed"), q("disputed"), "/staff/queue?queue=disputed"],
    [tr("إحالات بلا استلام", "No acknowledgement"), q("referred"), "/staff/queue?queue=stale"],
  ];
  return (
    <div>
      <PageHeader title={tr("نظرة عامة", "Overview")} />
      {s.demo > 0 && <div className="banner warn" style={{ marginBottom: 12 }}>{tr(`هذه البيئة تحتوي ${s.demo} بلاغًا تجريبيًا مُعلّمًا (بيانات عرض).`, `${s.demo} demo reports present.`)}</div>}
      <div className="grid three">
        {cards.map(([l, n, to]) => (
          <Link key={to} to={to} className="panel stat" style={{ textDecoration: "none", color: "inherit" }}><b>{num(n, lang)}</b><span className="small muted">{l}</span></Link>
        ))}
      </div>
      <div className="section"><h2>{tr("حسب الفئة", "By category")}</h2></div>
      <div className="table-wrap"><table className="data"><tbody>
        {s.by_category.map((c) => <tr key={c.category__name_ar}><td>{c.category__name_ar}</td><td className="num">{num(c.n, lang)}</td>
          <td style={{ width: "60%" }}><div className="progress"><span style={{ width: `${(c.n / Math.max(1, s.total)) * 100}%` }} /></div></td></tr>)}
      </tbody></table></div>
    </div>
  );
}

const QUEUES: [string, string, string][] = [["review", "المراجعة", "Review"], ["routing", "التوجيه", "Routing"], ["to_refer", "للإحالة", "To refer"],
  ["verify_done", "تحقق الإنجاز", "Verify done"], ["disputed", "الاعتراضات", "Disputes"], ["stale", "إحالات متأخرة", "Stale referrals"], ["active", "كل المفتوحة", "All open"]];

export function Queue() {
  const { tr } = useI18n();
  const [sp, setSp] = useSearchParams();
  const q = sp.get("queue") ?? "review";
  const { data, error, loading, reload } = useLoad<Paged<Report>>(`/reports/queue/?queue=${q}&page_size=100`, [q]);
  const objections = useLoad<Paged<{ id: number; report: number; report_tracking: string; reason: string; status: string }>>(q === "disputed" ? "/objections/" : null, [q]);
  const { busy, run } = useAction();
  const [decide, setDecide] = useState<{ id: number; accept: boolean } | null>(null);
  const [note, setNote] = useState("");
  return (
    <div>
      <PageHeader title={tr("قوائم العمل", "Work queues")} />
      <div className="tabs" role="tablist">{QUEUES.map(([k, a, e]) => <button key={k} role="tab" aria-selected={q === k} onClick={() => setSp({ queue: k })}>{tr(a, e)}</button>)}</div>
      {q === "stale" && <p className="small muted">{tr("الإحالات التي لم تؤكد الجهة استلامها. لا تُغلق بمرور الوقت — تابع مع الجهة أو سجّل استلامًا خارج البوابة بدليل.", "Referrals without acknowledgement — never auto-closed.")}</p>}
      {q === "disputed" && (objections.data?.results.filter((o) => o.status === "open").length ?? 0) > 0 && (
        <div className="panel" style={{ marginBottom: 12 }}>
          <h2>{tr("اعتراضات مفتوحة", "Open objections")}</h2>
          <ul className="list">{objections.data!.results.filter((o) => o.status === "open").map((o) => (
            <li key={o.id} className="list-item"><div className="grow"><Link to={`/staff/reports/${o.report}`}><bdi>{o.report_tracking}</bdi></Link><div className="small">{o.reason}</div></div>
              <button className="btn small" onClick={() => setDecide({ id: o.id, accept: true })}>{tr("قبول وإعادة فتح", "Accept & reopen")}</button>
              <button className="btn small ghost" onClick={() => setDecide({ id: o.id, accept: false })}>{tr("رفض", "Reject")}</button></li>))}</ul>
        </div>
      )}
      {loading && !data ? <Loading /> : error && !data ? <ErrorState error={error} onRetry={reload} /> : <ReportTable rows={data!.results} />}
      {decide && (
        <Dialog title={decide.accept ? tr("قبول الاعتراض", "Accept objection") : tr("رفض الاعتراض", "Reject objection")} onClose={() => setDecide(null)}>
          <Field id="dn" label={tr("نتيجة المراجعة (تُرسل للمعترض)", "Review result")}><textarea id="dn" className="input" value={note} onChange={(e) => setNote(e.target.value)} /></Field>
          <button className="btn block" disabled={busy || !note.trim()} onClick={async () => {
            const r = await run(() => post(`/objections/${decide.id}/decide/`, { accept: decide.accept, note }), tr("سُجّل القرار", "Decision recorded"));
            if (r) { setDecide(null); setNote(""); reload(); objections.reload(); }
          }}>{tr("تأكيد", "Confirm")}</button>
        </Dialog>
      )}
    </div>
  );
}

type Media = { uid: string; kind: string; status: string; sensitive_flags: string[]; created_at: string; url: string; transcript: string };

function BlurTool({ m, onDone }: { m: Media; onDone: () => void }) {
  const { tr } = useI18n();
  const { busy, run } = useAction();
  const [boxes, setBoxes] = useState<{ x: number; y: number; w: number; h: number }[]>([]);
  const start = useRef<{ x: number; y: number } | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const rel = (e: React.PointerEvent) => {
    const b = ref.current!.getBoundingClientRect();
    return { x: Math.min(1, Math.max(0, (e.clientX - b.left) / b.width)), y: Math.min(1, Math.max(0, (e.clientY - b.top) / b.height)) };
  };
  const decide = (decision: string, extra: Record<string, unknown> = {}) =>
    run(() => post(`/admin/moderation/${m.uid}/decide/`, { decision, regions: boxes, ...extra }), tr("حُفظ القرار", "Saved")).then((r) => r && onDone());
  return (
    <div className="panel">
      <div className="row between"><span className="xs muted">{formatDate(m.created_at)}</span>
        {m.sensitive_flags.includes("possible_injured_person") && <span className="badge s-bad">{tr("احتمال وجود مصاب", "Possible injured person")}</span>}</div>
      {m.kind === "image" ? (
        <>
          <p className="xs muted">{tr("اسحب على الصورة لتحديد مناطق الطمس (وجوه، مصابون، لوحات سيارات، أرقام).", "Drag to mark areas to blur.")}</p>
          <div ref={ref} className="blur-canvas" onPointerDown={(e) => { start.current = rel(e); }}
            onPointerUp={(e) => { const s = start.current; start.current = null; if (!s) return; const p = rel(e);
              const box = { x: Math.min(s.x, p.x), y: Math.min(s.y, p.y), w: Math.abs(p.x - s.x), h: Math.abs(p.y - s.y) };
              if (box.w > 0.01 && box.h > 0.01) setBoxes((b) => [...b, box]); }}>
            <AuthImg src={`${m.url}?original=1`} alt={tr("وسائط بانتظار المراجعة", "Media awaiting review")} draggable={false} />
            {boxes.map((b, i) => <div key={i} className="box" style={{ left: `${b.x * 100}%`, top: `${b.y * 100}%`, width: `${b.w * 100}%`, height: `${b.h * 100}%` }} />)}
          </div>
        </>
      ) : <AuthAudio src={`${m.url}?original=1`} />}
      <div className="row" style={{ marginTop: 8 }}>
        {boxes.length > 0 && <button className="btn small teal" disabled={busy} onClick={() => decide("blur")}>{tr(`اطمس ${boxes.length} منطقة وانشر`, `Blur ${boxes.length} & publish`)}</button>}
        {boxes.length > 0 && <button className="btn small ghost" onClick={() => setBoxes([])}>{tr("مسح التحديد", "Clear")}</button>}
        {boxes.length === 0 && <button className="btn small" disabled={busy} onClick={() => decide("approve", { confirm_no_injured: m.sensitive_flags.includes("possible_injured_person") ? window.confirm(tr("أتؤكد أن الصورة لا تُظهر مصابين أو بيانات شخصية؟", "Confirm no injured people or personal data?")) : undefined })}>{tr("انشر كما هي", "Publish as is")}</button>}
        <button className="btn small danger" disabled={busy} onClick={() => decide("reject")}>{tr("لا تُنشر", "Don't publish")}</button>
      </div>
    </div>
  );
}

export function Moderation() {
  const { tr } = useI18n();
  const { data, error, loading, reload } = useLoad<Paged<Media>>("/admin/moderation/?page_size=50");
  return (
    <div>
      <PageHeader title={tr("مراجعة الوسائط", "Media review")} />
      <p className="small muted" style={{ maxWidth: "70ch" }}>{tr("لا يرى الجمهور أي صورة أو تسجيل قبل اعتماده هنا. يُمنع نشر صور المصابين والبيانات الشخصية؛ اطمسها أو ارفض النشر.",
        "Nothing is public before approval here. Blur or reject injured people and personal data.")}</p>
      {loading && !data ? <Loading /> : error && !data ? <ErrorState error={error} onRetry={reload} /> :
        data!.results.length === 0 ? <EmptyState icon="check" title={tr("لا وسائط بانتظار المراجعة", "Nothing to review")} /> :
          <div className="grid two">{data!.results.map((m) => <BlurTool key={m.uid} m={m} onDone={reload} />)}</div>}
    </div>
  );
}

export function Followups() {
  const { tr, lang } = useI18n();
  const [st, setSt] = useState("due");
  const { data, error, loading, reload } = useLoad<Paged<{ id: number; report: number; tracking_number: string; category: string; area: string; round: number; due_at: string; status: string }>>(`/followups/?status=${st}`, [st]);
  const { busy, run } = useAction();
  const [ret, setRet] = useState<number | null>(null);
  const [note, setNote] = useState("");
  return (
    <div>
      <PageHeader title={tr("المراجعات اللاحقة", "Follow-up checks")} />
      <p className="small muted">{tr("بعد مدة قابلة للضبط من الحل، نتأكد أن الإصلاح ما زال قائمًا.", "After a configurable period we check the fix still holds.")}</p>
      <div className="tabs">{[["due", "مستحقة", "Due"], ["pending", "كل المعلقة", "Pending"], ["all", "الكل", "All"]].map(([k, a, e]) => <button key={k} aria-selected={st === k} role="tab" onClick={() => setSt(k)}>{tr(a, e)}</button>)}</div>
      {loading && !data ? <Loading /> : error && !data ? <ErrorState error={error} onRetry={reload} /> : data!.results.length === 0 ? <EmptyState icon="clock" title={tr("لا مراجعات", "Nothing due")} /> : (
        <div className="table-wrap"><table className="data"><thead><tr><th>{tr("البلاغ", "Report")}</th><th>{tr("المنطقة", "Area")}</th><th>{tr("الموعد", "Due")}</th><th>{tr("الحالة", "Status")}</th><th /></tr></thead>
          <tbody>{data!.results.map((f) => (
            <tr key={f.id}><td><Link to={`/staff/reports/${f.report}`}><bdi>{f.tracking_number}</bdi></Link> — {f.category}</td><td>{f.area}</td><td>{formatDate(f.due_at, lang)}</td><td>{f.status}</td>
              <td>{f.status === "pending" && <div className="row">
                <button className="btn small" disabled={busy} onClick={() => run(() => post(`/followups/${f.id}/complete/`, { ok: true, note: "" }), tr("الحل مستمر", "Fix holds")).then(reload)}>{tr("الحل مستمر", "Still fixed")}</button>
                <button className="btn small ghost" onClick={() => setRet(f.id)}>{tr("المشكلة رجعت", "Came back")}</button></div>}</td></tr>))}</tbody></table></div>
      )}
      {ret && (
        <Dialog title={tr("المشكلة رجعت", "Came back")} onClose={() => setRet(null)}>
          <p className="small muted">{tr("يحتاج دليلًا مصورًا حديثًا؛ استخدم صفحة البلاغ لإرفاقه، أو اكتب الملاحظة هنا ثم أرفق الصورة من الواجهة الميدانية.", "Requires recent photo evidence.")}</p>
          <Field id="rn" label={tr("ما الذي رجع؟", "What came back?")}><textarea id="rn" className="input" value={note} onChange={(e) => setNote(e.target.value)} /></Field>
          <Link className="btn block" to={`/reports/${data!.results.find((x) => x.id === ret)?.report}`}>{tr("افتح البلاغ لإرفاق الدليل", "Open report to attach evidence")}</Link>
        </Dialog>
      )}
    </div>
  );
}

export function Bundles() {
  const { tr, lang } = useI18n();
  const { data, error, loading, reload } = useLoad<Paged<{ id: number; title: string; kind: string; status: string; scheduled_for: string | null; reports_detail: { id: number; tracking_number: string; status: string; category: string }[]; is_demo: boolean }>>("/bundles/");
  const areas = useLoad<Paged<{ id: number; name_ar: string }>>("/areas/?page_size=200");
  const [open, setOpen] = useState(false);
  const [area, setArea] = useState("");
  const [cands, setCands] = useState<Report[]>([]);
  const [chosen, setChosen] = useState<number[]>([]);
  const [title, setTitle] = useState("");
  const [when, setWhen] = useState("");
  const { busy, run } = useAction();
  const loadCands = async (a: string) => { setArea(a); setChosen([]); setCands(await get<Report[]>(`/bundles/candidates/?area=${a}`).catch(() => [])); };
  return (
    <div>
      <PageHeader title={tr("حزم الحل للحومة", "Neighbourhood bundles")}><button className="btn small" onClick={() => setOpen(true)}>{tr("حزمة جديدة", "New bundle")}</button></PageHeader>
      <p className="small muted">{tr("اجمع بلاغات متقاربة في زيارة أو حملة واحدة. كل بلاغ يحتفظ بحالته ويُغلق وحده بعد التحقق.", "Group nearby reports into one visit; each keeps its own status.")}</p>
      {loading && !data ? <Loading /> : error && !data ? <ErrorState error={error} onRetry={reload} /> : data!.results.length === 0 ? <EmptyState icon="layers" title={tr("لا حزم بعد", "No bundles")} /> : (
        <div className="grid two">{data!.results.map((b) => (
          <div key={b.id} className="panel"><div className="row"><b>{b.title}</b><span className="badge plain">{b.kind === "visit" ? tr("زيارة", "Visit") : tr("حملة", "Campaign")}</span><DemoBadge show={b.is_demo} /></div>
            <div className="xs muted">{b.scheduled_for ? formatDate(b.scheduled_for, lang, true) : tr("بدون موعد", "Unscheduled")}</div>
            <ul className="small">{b.reports_detail.map((r) => <li key={r.id}><Link to={`/staff/reports/${r.id}`}><bdi>{r.tracking_number}</bdi></Link> {r.category} <StatusBadge status={r.status} /></li>)}</ul></div>))}</div>
      )}
      {open && (
        <Dialog title={tr("حزمة جديدة", "New bundle")} onClose={() => setOpen(false)}>
          <Field id="bt" label={tr("العنوان", "Title")}><input id="bt" className="input" value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
          <Field id="bw" label={tr("موعد الزيارة", "Visit date")}><input id="bw" type="datetime-local" className="input" value={when} onChange={(e) => setWhen(e.target.value)} /></Field>
          <Field id="ba" label={tr("المنطقة", "Area")}><select id="ba" className="input" value={area} onChange={(e) => loadCands(e.target.value)}><option value="">—</option>{areas.data?.results.map((a) => <option key={a.id} value={a.id}>{a.name_ar}</option>)}</select></Field>
          <div style={{ maxHeight: 240, overflow: "auto" }}>{cands.map((r) => (
            <label key={r.id} className="row small" style={{ padding: 4 }}><input type="checkbox" checked={chosen.includes(r.id)} onChange={() => setChosen((c) => c.includes(r.id) ? c.filter((x) => x !== r.id) : [...c, r.id])} />
              <bdi>{r.tracking_number}</bdi> {r.category.name} <StatusBadge status={r.status} /></label>))}</div>
          <button className="btn block" disabled={busy || !title || !chosen.length} onClick={async () => {
            const r = await run(() => post("/bundles/", { title, kind: "visit", area: area || null, reports: chosen, scheduled_for: when ? new Date(when).toISOString() : null }), tr("أُنشئت الحزمة", "Created"));
            if (r) { setOpen(false); reload(); }
          }}>{tr("أنشئ الحزمة", "Create bundle")}</button>
        </Dialog>
      )}
    </div>
  );
}

export function InitiativesAdmin() {
  const { tr } = useI18n();
  const { data, error, loading, reload } = useLoad<Paged<Initiative>>("/initiatives/?status=pending_approval&page_size=100");
  const all = useLoad<Paged<Initiative>>("/initiatives/?page_size=100");
  const { busy, run } = useAction();
  return (
    <div>
      <PageHeader title={tr("اعتماد المبادرات", "Initiative approval")} />
      <p className="small muted">{tr("لا تستقبل المبادرة أي مساهمة قبل اعتمادها من منسق غير مسؤولها.", "Initiatives can't receive contributions before independent approval.")}</p>
      {loading && !data ? <Loading /> : error && !data ? <ErrorState error={error} onRetry={reload} /> : data!.results.length === 0 ? <EmptyState icon="check" title={tr("لا مبادرات بانتظار الاعتماد", "Nothing pending")} /> : (
        <div className="grid two">{data!.results.map((i) => (
          <div key={i.id} className="panel"><b>{i.title}</b> <DemoBadge show={i.is_demo} /><p className="small">{i.summary}</p><p className="xs muted">{i.area_name} — {i.manager_name}</p>
            <div className="row"><button className="btn small teal" disabled={busy} onClick={() => run(() => post(`/initiatives/${i.id}/decide/`, { approve: true }), tr("اعتُمدت", "Approved")).then(() => { reload(); all.reload(); })}>{tr("اعتمد", "Approve")}</button>
              <button className="btn small ghost" disabled={busy} onClick={() => run(() => post(`/initiatives/${i.id}/decide/`, { approve: false, note: window.prompt(tr("سبب الإرجاع", "Reason")) ?? "" }), tr("أُعيدت للتعديل", "Returned")).then(reload)}>{tr("أعدها للتعديل", "Return")}</button></div></div>))}</div>
      )}
      <div className="section"><h2>{tr("كل المبادرات", "All initiatives")}</h2></div>
      <div className="table-wrap"><table className="data"><tbody>{all.data?.results.map((i) => <tr key={i.id}><td><Link to={`/initiatives/${i.id}`}>{i.title}</Link></td><td><StatusBadge status={i.status} label={i.status_label} /></td><td>{i.area_name}</td></tr>)}</tbody></table></div>
    </div>
  );
}

export function ProposalsAdmin() {
  const { tr } = useI18n();
  const { data, error, loading, reload } = useLoad<Paged<{ id: number; title: string; description: string; estimated_cost: string | null; status: string; status_label: string; feasibility_ok: boolean | null; permit_ok: boolean | null; cost_verified: string | null; maintenance_plan: string; votes_count: number }>>("/proposals/?page_size=100");
  const [sel, setSel] = useState<number | null>(null);
  const [f, setF] = useState({ feasibility_ok: false, permit_ok: false, cost_verified: "", maintenance_plan: "", review_note: "" });
  const { busy, run } = useAction();
  const decide = (decision: string) => run(() => post(`/proposals/${sel}/review/`, { decision, ...f, cost_verified: f.cost_verified || null }), tr("حُفظت المراجعة", "Saved")).then((r) => { if (r) { setSel(null); reload(); } });
  return (
    <div>
      <PageHeader title={tr("مراجعة اقتراحات الحومة", "Proposal review")} />
      {loading && !data ? <Loading /> : error && !data ? <ErrorState error={error} onRetry={reload} /> : (
        <div className="table-wrap"><table className="data"><thead><tr><th>{tr("الاقتراح", "Proposal")}</th><th>{tr("الحالة", "Status")}</th><th>{tr("التكلفة", "Cost")}</th><th>{tr("الأصوات", "Votes")}</th><th /></tr></thead>
          <tbody>{data!.results.map((p) => <tr key={p.id}><td><b>{p.title}</b><div className="xs muted">{p.description}</div></td><td>{p.status_label}</td><td className="num">{p.cost_verified ?? p.estimated_cost ?? "—"}</td><td className="num">{p.votes_count}</td>
            <td><button className="btn small" onClick={() => { setSel(p.id); setF({ feasibility_ok: !!p.feasibility_ok, permit_ok: !!p.permit_ok, cost_verified: p.cost_verified ?? p.estimated_cost ?? "", maintenance_plan: p.maintenance_plan, review_note: "" }); }}>{tr("راجع", "Review")}</button></td></tr>)}</tbody></table></div>
      )}
      {sel && (
        <Dialog title={tr("مراجعة الاقتراح", "Review")} onClose={() => setSel(null)}>
          <label className="row"><input type="checkbox" checked={f.feasibility_ok} onChange={(e) => setF({ ...f, feasibility_ok: e.target.checked })} />{tr("الجدوى الفنية مؤكدة", "Feasible")}</label>
          <label className="row"><input type="checkbox" checked={f.permit_ok} onChange={(e) => setF({ ...f, permit_ok: e.target.checked })} />{tr("الإذن متاح من الجهة", "Permit available")}</label>
          <Field id="cv" label={tr("التكلفة بعد المراجعة (د.ل)", "Verified cost")}><input id="cv" className="input" dir="ltr" value={f.cost_verified} onChange={(e) => setF({ ...f, cost_verified: e.target.value })} /></Field>
          <Field id="mp" label={tr("خطة الصيانة ومسؤولها", "Maintenance plan")}><input id="mp" className="input" value={f.maintenance_plan} onChange={(e) => setF({ ...f, maintenance_plan: e.target.value })} /></Field>
          <Field id="rn" label={tr("ملاحظات للمقترح", "Notes")}><textarea id="rn" className="input" value={f.review_note} onChange={(e) => setF({ ...f, review_note: e.target.value })} /></Field>
          <div className="row"><button className="btn teal" disabled={busy} onClick={() => decide("eligible")}>{tr("مؤهل للتصويت", "Eligible")}</button>
            <button className="btn ghost" disabled={busy} onClick={() => decide("needs_changes")}>{tr("يحتاج تعديل", "Needs changes")}</button>
            <button className="btn danger" disabled={busy} onClick={() => decide("rejected")}>{tr("غير مؤهل", "Reject")}</button></div>
        </Dialog>
      )}
    </div>
  );
}

export function Coverage() {
  const { tr, lang } = useI18n();
  const { hasRole } = useAuth();
  const { data, error, loading, reload } = useLoad<{ median_reports_90d: number; note: string; areas: { area_id: number; area: string; population: number | null; reports_90d: number; reports_per_1000: number | null; last_report_at: string | null; open_surveys: number; low_participation: boolean; boundary_source: string }[] }>("/coverage");
  const surveys = useLoad<Paged<{ id: number; area_name: string; ambassador_name: string; due_at: string; status: string; findings_note: string }>>("/surveys/");
  const [assign, setAssign] = useState<number | null>(null);
  const [amb, setAmb] = useState("");
  const [ambs, setAmbs] = useState<{ id: number; display_name: string }[]>([]);
  const [instr, setInstr] = useState("");
  const { busy, run } = useAction();
  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorState error={error} onRetry={reload} />;
  const openAssign = async (id: number) => { setAssign(id); setAmbs((await get<Paged<{ id: number; display_name: string }>>("/admin/users/?role=ambassador").catch(() => ({ results: [] } as never))).results ?? []); };
  return (
    <div>
      <PageHeader title={tr("تغطية المناطق الأقل مشاركة", "Coverage of low-participation areas")} />
      <p className="small muted">{data!.note}</p>
      <div className="table-wrap"><table className="data"><thead><tr><th>{tr("المنطقة", "Area")}</th><th>{tr("بلاغات 90 يومًا", "Reports (90d)")}</th><th>{tr("لكل 1000 ساكن", "per 1,000")}</th><th>{tr("آخر بلاغ", "Last report")}</th><th>{tr("مسوح جارية", "Open surveys")}</th><th /></tr></thead>
        <tbody>{data!.areas.map((a) => (
          <tr key={a.area_id}><td>{a.area} {a.low_participation && <span className="badge s-wait">{tr("نقص بيانات", "Data gap")}</span>}</td><td className="num">{num(a.reports_90d, lang)}</td><td className="num">{a.reports_per_1000 ?? "—"}</td>
            <td>{a.last_report_at ? timeAgo(a.last_report_at, lang) : tr("لا يوجد", "None")}</td><td className="num">{a.open_surveys}</td>
            <td>{hasRole("coordinator") && <button className="btn small" onClick={() => openAssign(a.area_id)}>{tr("كلّف سفيرًا بمسح", "Assign survey")}</button>}</td></tr>))}</tbody></table></div>
      <div className="section"><h2>{tr("تكليفات المسح الميداني", "Field survey assignments")}</h2></div>
      {(surveys.data?.results.length ?? 0) === 0 ? <p className="muted">—</p> : (
        <ul className="list panel">{surveys.data!.results.map((s) => <li key={s.id} className="list-item"><div className="grow"><b>{s.area_name}</b> — {s.ambassador_name}<div className="xs muted">{tr("قبل", "Due")} {formatDate(s.due_at, lang)} — {s.status}</div>{s.findings_note && <div className="small">{s.findings_note}</div>}</div></li>)}</ul>
      )}
      {assign && (
        <Dialog title={tr("تكليف مسح ميداني", "Assign a survey")} onClose={() => setAssign(null)}>
          <Field id="am" label={tr("السفير", "Ambassador")}><select id="am" className="input" value={amb} onChange={(e) => setAmb(e.target.value)}><option value="">—</option>{ambs.map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}</select></Field>
          <Field id="in" label={tr("التعليمات", "Instructions")}><textarea id="in" className="input" value={instr} onChange={(e) => setInstr(e.target.value)} /></Field>
          <button className="btn block" disabled={busy || !amb} onClick={async () => {
            const r = await run(() => post("/surveys/", { area: assign, ambassador: Number(amb), instructions: instr, due_at: new Date(Date.now() + 7 * 86400e3).toISOString() }), tr("أُرسل التكليف", "Assigned"));
            if (r) { setAssign(null); surveys.reload(); reload(); }
          }}>{tr("كلّف", "Assign")}</button>
        </Dialog>
      )}
    </div>
  );
}

export function Directory() {
  const { tr, lang } = useI18n();
  const care = useLoad<Paged<{ id: number; name: string; host_type: string; area_name: string; verified_at: string | null; services: string[]; hours: string }>>("/care-points/?page_size=200");
  const dir = useLoad<Paged<{ id: number; name: string; service: string; phone: string; verified_at: string | null; active: boolean }>>("/service-directory/?page_size=200");
  const { busy, run } = useAction();
  return (
    <div>
      <PageHeader title={tr("الدليل ونقاط العناية", "Directory & care points")} />
      <h2>{tr("نقاط العناية", "Care points")}</h2>
      <div className="table-wrap"><table className="data"><tbody>{care.data?.results.map((c) => (
        <tr key={c.id}><td><b>{c.name}</b> <span className="xs muted">{c.host_type}</span><div className="xs">{c.services.join("، ")}</div></td><td>{c.area_name}</td>
          <td>{c.verified_at ? `${tr("تحقق", "verified")} ${timeAgo(c.verified_at, lang)}` : <span className="badge s-wait">{tr("غير موثق", "Unverified")}</span>}</td>
          <td><button className="btn small" disabled={busy} onClick={() => run(() => post(`/care-points/${c.id}/verify/`), tr("سُجّل التحقق", "Verified")).then(care.reload)}>{tr("سجّل التحقق اليوم", "Verify today")}</button></td></tr>))}</tbody></table></div>
      <div className="section"><h2>{tr("دليل الخدمات", "Service directory")}</h2></div>
      <div className="table-wrap"><table className="data"><tbody>{dir.data?.results.map((d) => (
        <tr key={d.id}><td><b>{d.name}</b> — {d.service}</td><td dir="ltr">{d.phone}</td><td>{d.verified_at ? timeAgo(d.verified_at, lang) : tr("غير موثق", "Unverified")}</td>
          <td><button className="btn small" disabled={busy} onClick={() => run(() => post(`/service-directory/${d.id}/verify/`), tr("سُجّل التحقق", "Verified")).then(dir.reload)}>{tr("تحقق", "Verify")}</button>
            <button className="btn small ghost" disabled={busy} onClick={() => run(() => patch(`/service-directory/${d.id}/`, { active: !d.active })).then(dir.reload)}>{d.active ? tr("أخفِ", "Hide") : tr("أظهر", "Show")}</button></td></tr>))}</tbody></table></div>
    </div>
  );
}
