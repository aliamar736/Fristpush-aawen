import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { post, uploadMedia } from "../../api/client";
import type { Report } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { CATEGORY_ICON, Icon } from "../../components/Icon";
import { MapView } from "../../components/MapView";
import { PageHeader } from "../../components/Shell";
import { DemoBadge, Dialog, ErrorState, Field, Loading, STATUS_LABEL, StaleNote, StatusBadge, useAction } from "../../components/ui";
import { formatDate, timeAgo } from "../../lib/format";
import { useLoad } from "../../lib/hooks";
import { compressImage } from "../../lib/image";
import { useI18n } from "../../lib/i18n";

const HAPPY_PATH = ["submitted", "under_review", "verified", "referred", "acknowledged", "in_progress", "done_pending_verification", "resolved"];

export function StatusPath({ r }: { r: Report }) {
  const { tr, lang } = useI18n();
  const events = (r.events ?? []).filter((e) => e.kind === "status" || e.kind === "escalation" || e.kind === "recurrence" || e.kind === "bundle");
  const idx = HAPPY_PATH.indexOf(r.status);
  const future = idx >= 0 ? HAPPY_PATH.slice(idx + 1) : [];
  return (
    <ol className="path" aria-label={tr("مسار البلاغ", "Report journey")}>
      {events.map((e, i) => {
        const isNow = i === events.length - 1 && e.kind === "status";
        const label = e.kind === "status" ? (STATUS_LABEL[e.to_status] ? tr(...STATUS_LABEL[e.to_status]) : e.to_label)
          : e.kind === "escalation" ? tr("رُفع للمنسق للمتابعة", "Escalated to coordinator")
          : e.kind === "recurrence" ? tr("بلّغ أحد السكان أن المشكلة رجعت", "Reported as returned") : tr("ضُمّ لحزمة حل", "Added to a bundle");
        return (
          <li key={e.id} className={isNow ? "now" : ""} aria-current={isNow ? "step" : undefined}>
            <div style={{ fontWeight: isNow ? 700 : 600 }}>{label}</div>
            <div className="when">{e.actor && `${e.actor} — `}<time dateTime={e.at}>{formatDate(e.at, lang, true)}</time></div>
            {e.note && <div className="small">{e.note}</div>}
          </li>
        );
      })}
      {future.map((s) => (
        <li key={s} className="future"><div>{tr(...STATUS_LABEL[s])}</div></li>
      ))}
    </ol>
  );
}

export default function ReportDetail() {
  const { id } = useParams();
  const { tr, lang } = useI18n();
  const { me } = useAuth();
  const { data: r, error, loading, reload, stale, savedAt } = useLoad<Report>(`/reports/${id}/`, [id]);
  const { busy, run } = useAction();
  const [dlg, setDlg] = useState<null | "object" | "recur" | "check" | "info">(null);
  const [text, setText] = useState("");
  const [verdict, setVerdict] = useState("fixed");
  const [photo, setPhoto] = useState<Blob | null>(null);

  if (loading && !r) return <Loading lines={6} />;
  if (error && !r) return <ErrorState error={error} onRetry={reload} />;
  if (!r) return null;
  const v = r.viewer ?? { authenticated: false };
  const closeDlg = () => { setDlg(null); setText(""); setPhoto(null); };
  const withPhoto = async () => (photo ? [await uploadMedia(await compressImage(photo), "image")] : []);
  const loginLink = `/login?next=/reports/${r.id}`;

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    const res = await run(fn, ok);
    if (res !== undefined) { closeDlg(); reload(); }
  };

  return (
    <div style={{ maxWidth: 820, margin: "0 auto" }}>
      <PageHeader title={r.category.name} back="">
        <DemoBadge show={r.is_demo} />
      </PageHeader>
      <StaleNote stale={stale} savedAt={savedAt} />
      <div className="row" style={{ marginBottom: 12 }}>
        <StatusBadge status={r.status} />
        <span className="small muted">{tr("رقم المتابعة", "Tracking no.")} <bdi className="num" style={{ color: "var(--petrol)", fontWeight: 600 }}>{r.tracking_number ?? "—"}</bdi></span>
        {r.area_name && <span className="small muted">— {r.area_name}</span>}
      </div>

      {r.status === "needs_info" && v.is_owner && (
        <div className="banner warn" role="alert" style={{ marginBottom: 12 }}>
          <Icon name="alert" size={20} /><div><b>{tr("فريق المراجعة يحتاج معلومة منك:", "Reviewers need more information:")}</b> {r.needs_info_question}
            <div><button className="btn small" style={{ marginTop: 6 }} onClick={() => setDlg("info")}>{tr("أضف المعلومات", "Add information")}</button></div></div>
        </div>
      )}
      {r.status === "referred" && r.referral && !r.referral.acknowledged_at && (
        <div className="banner info" style={{ marginBottom: 12 }}>
          <Icon name="clock" size={20} /><span>{tr("أُحيل إلى", "Referred to")} <b>{r.referral.agency}</b> {timeAgo(r.referral.referred_at, lang)}. {tr("لم تؤكد الجهة الاستلام بعد — البلاغ يبقى مفتوحًا ولا يُغلق بمرور الوقت.", "The agency hasn't acknowledged yet — the report stays open.")}</span>
        </div>
      )}
      {r.status === "unresolvable" && r.status_reason && (
        <div className="banner error" style={{ marginBottom: 12 }}><b>{tr("سبب تعذر الحل:", "Reason:")}</b> {r.status_reason}</div>
      )}

      <div className="grid two">
        <div className="stack">
          <div className="panel">
            <h2>{tr("التفاصيل", "Details")}</h2>
            {r.description ? <p>{r.description}</p> : <p className="muted small">{tr("يظهر الوصف للعامة بعد مراجعته وحجب أي بيانات شخصية.", "The description appears after review.")}</p>}
            <dl className="kv small">
              <dt>{tr("وقت الرصد", "Observed")}</dt><dd>{formatDate(r.observed_at, lang, true)}</dd>
              <dt>{tr("وقت الإرسال", "Submitted")}</dt><dd>{formatDate(r.submitted_at, lang, true)}</dd>
              {r.landmark_text && (<><dt>{tr("معلم قريب", "Landmark")}</dt><dd>{r.landmark_text}</dd></>)}
              <dt>{tr("الجهة المختصة", "Responsible agency")}</dt><dd>{r.agency_name ?? tr("يحدد بعد المراجعة", "To be determined")}</dd>
              <dt>{tr("أكد وجودها", "Confirmed by")}</dt><dd>{r.confirmations_count} {tr("من السكان", "residents")}</dd>
              {r.reopen_count > 0 && (<><dt>{tr("رجعت", "Returned")}</dt><dd>{r.reopen_count} {tr("مرة بعد الإصلاح", "time(s) after a fix")}</dd></>)}
            </dl>
          </div>
          {r.media.length > 0 && (
            <div className="panel">
              <h2>{tr("الصور والأدلة", "Photos & evidence")}</h2>
              <div className="photo-grid">
                {r.media.filter((m) => m.kind === "image").map((m) => (
                  <a key={m.uid} href={m.url} target="_blank" rel="noreferrer">
                    <img src={m.url} alt={m.role === "completion_proof" ? tr("صورة إثبات الإنجاز", "Completion proof") : tr("صورة من البلاغ", "Report photo")} loading="lazy" />
                  </a>
                ))}
              </div>
            </div>
          )}
          <div className="mini-map"><MapView label={tr("موقع البلاغ", "Report location")} cluster={false} center={[r.lat, r.lng]} zoom={16}
            markers={[{ id: r.id, lat: r.lat, lng: r.lng, color: "#0B6E64", label: r.category.name }]} /></div>
          <Link to={`/place?lat=${r.lat}&lng=${r.lng}`} className="small">{tr("ملف المكان: كل ما حدث في هذا الموقع", "Place history")}</Link>
        </div>

        <div className="stack">
          <div className="panel">
            <h2>{tr("مسار المعالجة", "Progress")}</h2>
            <StatusPath r={r} />
          </div>
          <div className="panel stack">
            <h2>{tr("شارك في المتابعة", "Take part")}</h2>
            {!me && <p className="small"><Link to={loginLink}>{tr("سجّل الدخول", "Sign in")}</Link> {tr("لتأكيد المشكلة أو الاعتراض أو التحقق من الإصلاح.", "to confirm, object or verify the fix.")}</p>}
            {me && !v.is_owner && ["submitted", "under_review", "verified", "referred", "acknowledged", "in_progress", "waiting_resource", "reopened"].includes(r.status) && (
              v.confirmed ? <p className="small muted"><Icon name="check" size={18} /> {tr("أكدت وجود هذه المشكلة.", "You confirmed this problem.")}</p>
                : <button className="btn teal" disabled={busy} onClick={() => act(() => post(`/reports/${r.id}/confirm/`), tr("شكرًا، سُجّل تأكيدك.", "Confirmed."))}>
                    {tr("المشكلة موجودة، أؤكدها", "I see it too — confirm")}</button>
            )}
            {me && r.status === "done_pending_verification" && !v.is_executor && !v.checked && (
              <button className="btn" onClick={() => setDlg("check")}>{tr("هل اتصلحت فعلًا؟ أكّد", "Was it really fixed? Verify")}</button>
            )}
            {me && r.status === "done_pending_verification" && v.checked && <p className="small muted">{tr("سجلنا تحققك. ينتظر الآن مراجعة الفريق.", "Your check is recorded.")}</p>}
            {me && r.status === "resolved" && (
              <>
                <button className="btn ghost" onClick={() => setDlg("object")}>{tr("أعترض على الإغلاق", "Object to the closure")}</button>
                <button className="btn ghost" onClick={() => setDlg("recur")}>{tr("المشكلة رجعت", "The problem came back")}</button>
              </>
            )}
            {r.status === "disputed" && <p className="small">{tr("يوجد اعتراض قيد المراجعة على هذا الإغلاق.", "An objection is under review.")}</p>}
            {r.completion && r.status === "done_pending_verification" && (
              <p className="xs muted">{tr("تأكيدات مستقلة:", "Independent checks:")} {r.completion.checks.fixed} {tr("تم الإصلاح", "fixed")}، {r.completion.checks.not_fixed} {tr("لم يُصلح", "not fixed")}</p>
            )}
          </div>
        </div>
      </div>

      {dlg === "object" && (
        <Dialog title={tr("الاعتراض على الإغلاق", "Object to closure")} onClose={closeDlg}>
          <Field id="obj" label={tr("لماذا تعترض؟", "Why do you object?")}><textarea id="obj" className="input" value={text} onChange={(e) => setText(e.target.value)} /></Field>
          <button className="btn block" disabled={busy || !text.trim()} onClick={() => act(() => post(`/reports/${r.id}/object/`, { reason: text }), tr("وصل اعتراضك وسيراجعه الفريق.", "Objection submitted."))}>{tr("أرسل الاعتراض", "Submit objection")}</button>
        </Dialog>
      )}
      {dlg === "recur" && (
        <Dialog title={tr("المشكلة رجعت", "The problem came back")} onClose={closeDlg}>
          <p className="small muted">{tr("سنربط بلاغك بالإصلاح السابق ونعيد فتحه. نحتاج صورة حديثة كدليل.", "We'll link this to the previous fix. A recent photo is required.")}</p>
          <Field id="rec" label={tr("ماذا رجع؟", "What came back?")}><textarea id="rec" className="input" value={text} onChange={(e) => setText(e.target.value)} /></Field>
          <label className="btn ghost"><Icon name="camera" size={20} />{photo ? tr("تم اختيار صورة", "Photo selected") : tr("أرفق صورة حديثة", "Attach a recent photo")}
            <input type="file" accept="image/*" capture="environment" className="sr-only" onChange={(e) => setPhoto(e.target.files?.[0] ?? null)} /></label>
          <button className="btn block" style={{ marginTop: 12 }} disabled={busy || !text.trim() || !photo}
            onClick={() => act(async () => post(`/reports/${r.id}/recurrence/`, { note: text, media: await withPhoto() }), tr("أعيد فتح البلاغ.", "Report reopened."))}>{tr("أعد فتح البلاغ", "Reopen report")}</button>
        </Dialog>
      )}
      {dlg === "check" && (
        <Dialog title={tr("تحقق من الإصلاح", "Verify the fix")} onClose={closeDlg}>
          <div className="chips" role="radiogroup" style={{ marginBottom: 12 }}>
            {[["fixed", "تم الإصلاح", "Fixed"], ["partial", "إصلاح جزئي", "Partly fixed"], ["not_fixed", "لم يُصلح", "Not fixed"]].map(([k, a, e]) => (
              <button key={k} role="radio" className="chip" aria-checked={verdict === k} onClick={() => setVerdict(k)}>{tr(a, e)}</button>
            ))}
          </div>
          <Field id="chk" label={tr("ملاحظة (اختياري)", "Note (optional)")}><textarea id="chk" className="input" value={text} onChange={(e) => setText(e.target.value)} /></Field>
          <label className="btn ghost"><Icon name="camera" size={20} />{photo ? tr("تم اختيار صورة", "Photo selected") : tr("صورة (اختياري)", "Photo (optional)")}
            <input type="file" accept="image/*" capture="environment" className="sr-only" onChange={(e) => setPhoto(e.target.files?.[0] ?? null)} /></label>
          <button className="btn block" style={{ marginTop: 12 }} disabled={busy}
            onClick={() => act(async () => post(`/reports/${r.id}/check/`, { verdict, note: text, media: await withPhoto() }), tr("شكرًا، سُجّل تحققك.", "Thanks."))}>{tr("سجّل تحققي", "Record my check")}</button>
        </Dialog>
      )}
      {dlg === "info" && (
        <Dialog title={tr("إضافة معلومات", "Add information")} onClose={closeDlg}>
          <Field id="inf" label={r.needs_info_question || tr("المعلومات", "Information")}><textarea id="inf" className="input" value={text} onChange={(e) => setText(e.target.value)} /></Field>
          <label className="btn ghost"><Icon name="camera" size={20} />{photo ? tr("تم اختيار صورة", "Photo selected") : tr("صورة (اختياري)", "Photo (optional)")}
            <input type="file" accept="image/*" className="sr-only" onChange={(e) => setPhoto(e.target.files?.[0] ?? null)} /></label>
          <button className="btn block" style={{ marginTop: 12 }} disabled={busy || !text.trim()}
            onClick={() => act(async () => post(`/reports/${r.id}/add-info/`, { note: text, media: await withPhoto() }), tr("أُرسلت المعلومات.", "Sent."))}>{tr("أرسل", "Send")}</button>
        </Dialog>
      )}
      <p className="xs muted" style={{ marginTop: 16 }}>{tr("آخر تحديث", "Last update")} {timeAgo(r.status_changed_at, lang)} — <Icon name={CATEGORY_ICON[r.category.slug] ?? "pin"} size={14} /> {r.category.name}</p>
    </div>
  );
}
