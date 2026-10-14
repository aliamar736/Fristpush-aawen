import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { get, post, uploadMedia } from "../../api/client";
import type { Paged, Report } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Icon } from "../../components/Icon";
import { AuthAudio, AuthImg } from "../../components/AuthMedia";
import { MapView } from "../../components/MapView";
import { PageHeader } from "../../components/Shell";
import { DemoBadge, Dialog, ErrorState, Field, Loading, STATUS_LABEL, StatusBadge, useAction } from "../../components/ui";
import { formatDate } from "../../lib/format";
import { useLoad } from "../../lib/hooks";
import { compressImage } from "../../lib/image";
import { useI18n } from "../../lib/i18n";
import { StatusPath } from "../citizen/ReportDetail";

const NEEDS_REASON = new Set(["needs_info", "waiting_resource", "unresolvable", "disputed", "reopened"]);
const FLAG_LABEL: Record<string, string> = { phone_number: "رقم هاتف", national_id: "رقم وطني", email: "بريد", vehicle_plate: "لوحة سيارة",
  possible_injury: "إشارة لمصابين", personal_name: "اسم شخص" };

/** Staff / agency / field view of one report: all transitions are validated again by the server. */
export default function ReportWorkbench() {
  const { id } = useParams();
  const { tr, lang } = useI18n();
  const { hasRole } = useAuth();
  const { data: r, error, loading, reload } = useLoad<Report>(`/reports/${id}/`, [id]);
  const agencies = useLoad<Paged<{ id: number; name: string; is_linked: boolean }>>("/agencies/?page_size=200");
  const { busy, run } = useAction();
  const [target, setTarget] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [agency, setAgency] = useState<string>("");
  const [proofOpen, setProofOpen] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [assignOpen, setAssignOpen] = useState(false);
  const [userQ, setUserQ] = useState("");
  const [users, setUsers] = useState<{ id: number; display_name: string; phone: string }[]>([]);
  if (loading && !r) return <Loading lines={8} />;
  if (error && !r) return <ErrorState error={error} onRetry={reload} />;
  if (!r) return null;
  const actions = (r.actions ?? []).filter((a) => !["disputed", "reopened"].includes(a) || r.status !== "resolved");
  const doTransition = async () => {
    const res = await run(() => post(`/reports/${r.id}/transition/`, { to: target, reason, note, agency: agency || undefined }),
      tr("حُدّثت الحالة", "Status updated"));
    if (res) { setTarget(null); setReason(""); setNote(""); reload(); }
  };
  const doProof = async () => {
    const res = await run(async () => {
      const ids: string[] = [];
      for (const f of files) ids.push(await uploadMedia(await compressImage(f), "image"));
      return post(`/reports/${r.id}/proof/`, { note, media: ids });
    }, tr("أُرسل إثبات الإنجاز. ينتظر تأكيدًا مستقلًا.", "Proof submitted; awaiting independent confirmation."));
    if (res) { setProofOpen(false); setFiles([]); setNote(""); reload(); }
  };
  const canProof = ["in_progress", "waiting_resource"].includes(r.status) && (r.viewer?.kinds ?? []).some((k) => ["agency", "coordinator", "field"].includes(k));
  const searchUsers = async (q: string) => {
    setUserQ(q);
    if (q.length < 2) return setUsers([]);
    try { setUsers((await get<Paged<{ id: number; display_name: string; phone: string }>>(`/admin/users/?q=${encodeURIComponent(q)}`)).results); } catch { setUsers([]); }
  };
  return (
    <div>
      <PageHeader title={`${r.category.name} — ${r.tracking_number ?? ""}`} back=""><DemoBadge show={r.is_demo} /></PageHeader>
      <div className="row" style={{ marginBottom: 12 }}>
        <StatusBadge status={r.status} />
        <span className="badge plain">{tr("أولوية", "Priority")} {Math.round(r.priority_score)}</span>
        {r.routing_status === "needs_review" && <span className="badge s-wait">{tr("التوجيه يحتاج مراجعة", "Routing needs review")}</span>}
        {r.escalated_at && <span className="badge s-bad">{tr("مُصعّد: الجهة لم تؤكد الاستلام", "Escalated: no acknowledgement")}</span>}
        <Link to={`/reports/${r.id}`} className="small">{tr("كما يراه الجمهور", "Public view")}</Link>
      </div>
      {(r.sensitive_flags?.length ?? 0) > 0 && (
        <div className="banner warn" style={{ marginBottom: 12 }}><Icon name="shield" size={20} />
          <span>{tr("الوصف يحتوي على بيانات حساسة تُحجب تلقائيًا في العرض العام:", "Sensitive data detected (masked publicly):")} {r.sensitive_flags!.map((f) => FLAG_LABEL[f] ?? f).join("، ")}</span></div>
      )}
      <div className="grid two">
        <div className="stack">
          <div className="panel">
            <h2>{tr("الإجراءات المتاحة لك", "Your actions")}</h2>
            {actions.length === 0 && !canProof ? <p className="muted small">{tr("لا يوجد إجراء متاح لدورك في هذه الحالة.", "No action available for your role at this stage.")}</p> : (
              <div className="row">
                {actions.filter((a) => a !== "done_pending_verification").map((a) => (
                  <button key={a} className={`btn small ${a === "unresolvable" ? "danger" : a === "resolved" ? "teal" : ""}`} onClick={() => { setTarget(a); setAgency(String(r.agency ?? "")); }}>
                    {tr(...(STATUS_LABEL[a] ?? [a, a]))}
                  </button>
                ))}
                {canProof && <button className="btn small teal" onClick={() => setProofOpen(true)}><Icon name="camera" size={18} />{tr("أنجزت — أرفق الإثبات", "Done — attach proof")}</button>}
              </div>
            )}
            {r.status === "done_pending_verification" && (
              <p className="small" style={{ marginTop: 8 }}>{tr("تأكيدات مستقلة:", "Independent checks:")} {r.completion?.checks.fixed} {tr("تم الإصلاح", "fixed")}، {r.completion?.checks.not_fixed} {tr("لم يُصلح", "not fixed")}، {r.completion?.checks.partial} {tr("جزئي", "partial")}.
                {" "}{tr("الاعتماد يحتاج تأكيدًا مستقلًا واحدًا على الأقل، ومع التعارض تُكتب نتيجة المراجعة.", "Needs at least one independent confirmation; conflicts need a review note.")}</p>
            )}
            {(hasRole("coordinator") || hasRole("agency_staff")) && (
              <button className="btn small ghost" style={{ marginTop: 8 }} onClick={() => setAssignOpen(true)}>{tr("تعيين فريق ميداني / مسؤول متابعة", "Assign field team / follow-up owner")}</button>
            )}
          </div>
          <div className="panel">
            <h2>{tr("التفاصيل", "Details")}</h2>
            <p>{r.raw_description || <span className="muted">{tr("بدون وصف", "No description")}</span>}</p>
            <dl className="kv small">
              <dt>{tr("المبلّغ", "Reporter")}</dt><dd>{r.reporter_name ?? "—"} <span className="xs muted">({tr("لا يظهر للعامة", "never public")})</span></dd>
              <dt>{tr("وقت الرصد", "Observed")}</dt><dd>{formatDate(r.observed_at, lang, true)}</dd>
              <dt>{tr("وقت الإرسال", "Submitted")}</dt><dd>{formatDate(r.submitted_at, lang, true)}</dd>
              <dt>{tr("المنطقة", "Area")}</dt><dd>{r.area_name ?? tr("خارج المناطق", "Outside areas")}</dd>
              <dt>{tr("الجهة", "Agency")}</dt><dd>{r.agency_name ?? "—"}</dd>
              <dt>{tr("التوجيه", "Routing")}</dt><dd>{r.routing_status} {r.routing_notes && `— ${r.routing_notes}`}</dd>
              <dt>{tr("الخطورة", "Danger")}</dt><dd>{r.danger_level}/3</dd>
              <dt>{tr("مكونات الأولوية", "Priority breakdown")}</dt><dd className="xs">{Object.entries(r.priority_breakdown ?? {}).map(([k, v]) => `${k}: ${v}`).join(" | ")}</dd>
            </dl>
            {(r.routing_candidates?.length ?? 0) > 1 && (
              <div style={{ marginTop: 8 }}><b className="small">{tr("مرشحو التوجيه (حالة حدودية)", "Routing candidates")}</b>
                <ul className="small">{r.routing_candidates!.map((c) => <li key={c.area_id}>{c.area} → {c.agency ?? tr("لا قاعدة", "no rule")}</li>)}</ul></div>
            )}
          </div>
          <div className="panel">
            <h2>{tr("الوسائط", "Media")}</h2>
            {(r.all_media?.length ?? 0) === 0 ? <p className="muted small">{tr("لا وسائط", "None")}</p> : (
              <div className="photo-grid">{r.all_media!.map((m) => (
                <figure key={m.uid} style={{ margin: 0 }}>
                  {m.kind === "image" ? <AuthImg src={`${m.url}?original=1`} alt={m.role} />
                    : <AuthAudio src={`${m.url}?original=1`} />}
                  <figcaption className="xs muted">{m.role} — {m.status === "approved" ? tr("منشور", "public") : m.status === "rejected" ? tr("مرفوض", "rejected") : tr("بانتظار المراجعة", "pending")}</figcaption>
                </figure>))}</div>
            )}
            <Link className="small" to="/staff/moderation">{tr("مراجعة الوسائط والطمس", "Review & blur media")}</Link>
          </div>
        </div>
        <div className="stack">
          <div className="mini-map"><MapView label={tr("موقع البلاغ", "Location")} cluster={false} center={[r.lat, r.lng]} zoom={16}
            markers={[{ id: r.id, lat: r.lat, lng: r.lng, color: "#0B6E64", label: r.category.name }]} /></div>
          <div className="panel"><h2>{tr("المسار", "Journey")}</h2><StatusPath r={r} /></div>
          <div className="panel"><h2>{tr("سجل داخلي", "Internal log")}</h2>
            {(r.internal_events?.length ?? 0) === 0 ? <p className="muted small">—</p> :
              <ul className="small">{r.internal_events!.map((e, i) => <li key={i}>{formatDate(e.at, lang, true)} — {e.kind} {e.note}</li>)}</ul>}
          </div>
        </div>
      </div>

      {target && (
        <Dialog title={tr(...(STATUS_LABEL[target] ?? [target, target]))} onClose={() => setTarget(null)}>
          {target === "referred" && (
            <Field id="ag" label={tr("الجهة المختصة", "Agency")} hint={tr("مقترحة من دليل الاختصاص. غيّرها في الحالات الحدودية.", "Suggested by the routing directory.")}>
              <select id="ag" className="input" value={agency} onChange={(e) => setAgency(e.target.value)}>
                <option value="">—</option>{agencies.data?.results.map((a) => <option key={a.id} value={a.id}>{a.name}{a.is_linked ? "" : tr(" (غير مرتبطة بالبوابة)", " (not on portal)")}</option>)}
              </select></Field>
          )}
          {NEEDS_REASON.has(target) && (
            <Field id="rs" label={target === "needs_info" ? tr("ما المعلومة المطلوبة من المبلّغ؟", "What info is needed?") : tr("السبب", "Reason")}>
              <textarea id="rs" className="input" value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
          )}
          <Field id="nt" label={target === "acknowledged" && !(r.viewer?.kinds ?? []).includes("agency") ? tr("كيف أكدت الجهة الاستلام؟ (مطلوب)", "How did the agency confirm? (required)")
            : target === "resolved" ? tr("نتيجة المراجعة (مطلوبة عند تعارض التأكيدات)", "Review note (required on conflicting checks)") : tr("ملاحظة (اختياري)", "Note (optional)")}>
            <textarea id="nt" className="input" value={note} onChange={(e) => setNote(e.target.value)} /></Field>
          <button className="btn block" disabled={busy} onClick={doTransition}>{tr("تأكيد", "Confirm")}</button>
        </Dialog>
      )}
      {proofOpen && (
        <Dialog title={tr("إثبات الإنجاز", "Completion proof")} onClose={() => setProofOpen(false)}>
          <Field id="pn" label={tr("ماذا أُنجز؟", "What was done?")}><textarea id="pn" className="input" value={note} onChange={(e) => setNote(e.target.value)} /></Field>
          <label className="btn ghost"><Icon name="camera" size={20} />{files.length ? `${files.length} ${tr("صورة", "photo(s)")}` : tr("صور بعد الإنجاز (مطلوبة)", "After photos (required)")}
            <input type="file" accept="image/*" multiple capture="environment" className="sr-only" onChange={(e) => setFiles(Array.from(e.target.files ?? []))} /></label>
          <button className="btn block teal" style={{ marginTop: 12 }} disabled={busy || !files.length || !note.trim()} onClick={doProof}>{tr("أرسل الإثبات", "Submit proof")}</button>
        </Dialog>
      )}
      {assignOpen && (
        <Dialog title={tr("تعيين", "Assign")} onClose={() => setAssignOpen(false)}>
          <Field id="uq" label={tr("ابحث عن مستخدم بالاسم أو الهاتف", "Search user by name or phone")}><input id="uq" className="input" value={userQ} onChange={(e) => searchUsers(e.target.value)} /></Field>
          <ul className="list">{users.map((u) => (
            <li key={u.id} className="list-item"><span className="grow">{u.display_name || u.phone}</span>
              <button className="btn small" disabled={busy} onClick={() => run(() => post(`/reports/${r.id}/assign/`, { field_assignee: u.id }), tr("عُيّن الفريق الميداني", "Assigned")).then(reload)}>{tr("ميداني", "Field")}</button>
              {hasRole("coordinator") && <button className="btn small ghost" disabled={busy} onClick={() => run(() => post(`/reports/${r.id}/assign/`, { follow_up_owner: u.id }), tr("عُيّن مسؤول المتابعة", "Assigned")).then(reload)}>{tr("متابعة", "Follow-up")}</button>}
            </li>))}</ul>
        </Dialog>
      )}
    </div>
  );
}
