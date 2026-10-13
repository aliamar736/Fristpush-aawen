import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { del, get, post } from "../../api/client";
import type { Paged, Pledge, Report, Reservation } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { CATEGORY_ICON, Icon } from "../../components/Icon";
import { DemoBadge, Dialog, EmptyState, ErrorState, Field, Loading, StatusBadge, useAction } from "../../components/ui";
import { deleteDraft, listDrafts, sendDraft, type Draft } from "../../lib/drafts";
import { formatDate, money, num, timeAgo } from "../../lib/format";
import { useLoad } from "../../lib/hooks";
import { useI18n } from "../../lib/i18n";
import { uploadReceipt } from "./Initiative";

const TABS: [string, string, string][] = [
  ["reports", "بلاغاتي", "My reports"], ["drafts", "المسودات", "Drafts"], ["tasks", "مهامي", "My tasks"],
  ["contributions", "مساهماتي", "Contributions"], ["store", "حجوزاتي", "Reservations"], ["objections", "اعتراضاتي", "Objections"],
  ["account", "حسابي", "Account"],
];

export default function Impact() {
  const { tr } = useI18n();
  const { me, loading } = useAuth();
  const [sp, setSp] = useSearchParams();
  const tab = sp.get("tab") ?? "reports";
  if (loading) return <Loading />;
  return (
    <div>
      <h1>{tr("أثري", "My impact")}</h1>
      {!me && tab !== "drafts" ? (
        <EmptyState icon="me" title={tr("سجّل الدخول لمتابعة أثرك", "Sign in to see your impact")}
          action={<div className="row" style={{ justifyContent: "center" }}><Link className="btn" to="/login?next=/me">{tr("تسجيل الدخول", "Sign in")}</Link>
            <Link className="btn ghost" to="/me?tab=drafts">{tr("مسوداتي على هذا الجهاز", "Drafts on this device")}</Link></div>}>
          {tr("بلاغاتك ومهامك ومساهماتك في مكان واحد.", "Your reports, tasks and contributions in one place.")}
        </EmptyState>
      ) : (
        <>
          {me && <Summary />}
          <div className="tabs" role="tablist" aria-label={tr("أقسام أثري", "Sections")}>
            {TABS.map(([k, a, e]) => <button key={k} role="tab" aria-selected={tab === k} onClick={() => setSp({ tab: k })}>{tr(a, e)}</button>)}
            <Link to="/notifications">{tr("الإشعارات", "Notifications")}</Link>
          </div>
          <div role="tabpanel">
            {tab === "reports" && <MyReports />}
            {tab === "drafts" && <Drafts />}
            {tab === "tasks" && <MyTasks />}
            {tab === "contributions" && <MyContributions />}
            {tab === "store" && <MyReservations />}
            {tab === "objections" && <MyObjections />}
            {tab === "account" && <Account />}
          </div>
        </>
      )}
    </div>
  );
}

function Summary() {
  const { tr, lang } = useI18n();
  const reps = useLoad<Paged<Report>>("/reports/mine/?page_size=1");
  const books = useLoad<{ status: string }[]>("/bookings/mine/");
  const pledges = useLoad<Paged<Pledge>>("/pledges/?page_size=200");
  const conf = useLoad<Report[]>("/reports/confirmed/");
  const paid = (pledges.data?.results ?? []).filter((p) => p.status === "paid").reduce((s, p) => s + Number(p.amount), 0);
  return (
    <section className="hero routes-bg" aria-label={tr("ملخص المشاركة", "Participation summary")} style={{ marginBottom: 12 }}>
      <div className="grid three" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))" }}>
        <div className="stat"><b>{num(reps.data?.count ?? 0, lang)}</b><span className="small">{tr("بلاغ قدمته", "reports filed")}</span></div>
        <div className="stat"><b>{num(conf.data?.length ?? 0, lang)}</b><span className="small">{tr("مشكلة أكدتها", "confirmed")}</span></div>
        <div className="stat"><b>{num((books.data ?? []).filter((b) => b.status === "completed").length, lang)}</b><span className="small">{tr("مهمة أنجزتها", "tasks done")}</span></div>
        <div className="stat"><b className="num">{money(paid, lang)}</b><span className="small">{tr("مساهمات مؤكدة", "confirmed giving")}</span></div>
      </div>
    </section>
  );
}

function MyReports() {
  const { tr, lang } = useI18n();
  const { data, error, loading, reload } = useLoad<Paged<Report>>("/reports/mine/?page_size=100");
  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorState error={error} onRetry={reload} />;
  if (!data!.results.length) return <EmptyState icon="pin" title={tr("لم تقدم بلاغات بعد", "No reports yet")} action={<Link className="btn teal" to="/report/new">{tr("بلّغ عن مشكلة", "Report a problem")}</Link>} />;
  return (
    <ul className="list panel">
      {data!.results.map((r) => (
        <li key={r.id}><Link className="list-item" to={`/reports/${r.id}`}>
          <Icon name={CATEGORY_ICON[r.category.slug] ?? "pin"} />
          <div className="grow"><div className="row"><b>{r.category.name}</b><StatusBadge status={r.status} /><DemoBadge show={r.is_demo} /></div>
            <div className="xs muted"><bdi>{r.tracking_number}</bdi> — {tr("آخر تحديث", "updated")} {timeAgo(r.status_changed_at, lang)}</div>
            {r.status === "needs_info" && <div className="small" style={{ color: "var(--yellow-ink)" }}>{tr("مطلوب منك معلومة", "Information requested")}</div>}
          </div><Icon name="fwd" className="flip" /></Link></li>
      ))}
    </ul>
  );
}

function Drafts() {
  const { tr, lang } = useI18n();
  const [drafts, setDrafts] = useState<Draft[] | null>(null);
  const nav = useNavigate();
  const load = () => listDrafts().then(setDrafts).catch(() => setDrafts([]));
  useEffect(() => { load(); }, []);
  if (!drafts) return <Loading />;
  const pending = drafts.filter((d) => d.status !== "sent");
  if (!pending.length) return <EmptyState icon="doc" title={tr("لا توجد مسودات على هذا الجهاز", "No drafts on this device")} />;
  const label: Record<string, string> = { draft: tr("مسودة", "Draft"), queued: tr("بانتظار الاتصال", "Waiting for connection"),
    sending: tr("جارٍ الإرسال", "Sending"), failed: tr("يحتاج تعديل", "Needs changes") };
  return (
    <ul className="list panel">
      {pending.map((d) => (
        <li key={d.client_id} className="list-item">
          <Icon name="doc" />
          <div className="grow"><div className="row"><b>{d.description.slice(0, 60) || tr("بلاغ بدون وصف", "Untitled report")}</b><span className="badge s-wait">{label[d.status]}</span></div>
            <div className="xs muted">{tr("حُفظت", "Saved")} {timeAgo(new Date(d.updated_at).toISOString(), lang)} — {d.photos.length} {tr("صورة", "photos")}</div>
            {d.error && <div className="small" style={{ color: "var(--danger)" }}>{d.error}</div>}</div>
          <div className="row">
            <button className="btn small" onClick={() => nav(`/report/new?draft=${d.client_id}`)}>{tr("أكمل", "Continue")}</button>
            {d.status === "queued" && <button className="btn small ghost" onClick={async () => { await sendDraft(d); load(); }}>{tr("أعد المحاولة", "Retry")}</button>}
            <button className="btn small ghost" onClick={async () => { await deleteDraft(d.client_id); load(); }}>{tr("احذف", "Delete")}</button>
          </div>
        </li>
      ))}
    </ul>
  );
}

function MyTasks() {
  const { tr, lang } = useI18n();
  const { data, error, loading, reload } = useLoad<{ id: number; task: number; task_title: string; starts_at: string; status: string }[]>("/bookings/mine/");
  const { busy, run } = useAction();
  const [done, setDone] = useState<number | null>(null);
  const [note, setNote] = useState("");
  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorState error={error} onRetry={reload} />;
  if (!data!.length) return <EmptyState icon="hands" title={tr("لم تحجز مهام بعد", "No tasks yet")} action={<Link className="btn" to="/aawen?tab=tasks">{tr("خُذ مهمة", "Take a task")}</Link>} />;
  return (
    <>
      <ul className="list panel">
        {data!.map((b) => (
          <li key={b.id} className="list-item"><Icon name="hands" /><div className="grow">
            <div className="row"><b>{b.task_title}</b><StatusBadge status={b.status} /></div>
            <div className="xs muted">{formatDate(b.starts_at, lang, true)}</div>
            {b.status === "booked" && <div className="xs muted">{tr("يؤكد مسؤول المهمة حضورك يوم التنفيذ، ثم تضيف إثبات الإتمام.", "The lead confirms attendance; then add completion proof.")}</div>}
          </div>
            {b.status === "booked" && <button className="btn small ghost" disabled={busy} onClick={() => run(() => post(`/bookings/${b.id}/cancel/`), tr("أُلغي الحجز", "Cancelled")).then(reload)}>{tr("إلغاء", "Cancel")}</button>}
            {b.status === "attended" && <button className="btn small teal" onClick={() => setDone(b.id)}>{tr("أثبت الإتمام", "Confirm completion")}</button>}
          </li>
        ))}
      </ul>
      {done && (
        <Dialog title={tr("إثبات إتمام المهمة", "Completion proof")} onClose={() => setDone(null)}>
          <Field id="cn" label={tr("ماذا أنجزت؟", "What did you do?")}><textarea id="cn" className="input" value={note} onChange={(e) => setNote(e.target.value)} /></Field>
          <button className="btn block" disabled={busy || !note.trim()} onClick={async () => {
            const r = await run(() => post(`/bookings/${done}/complete/`, { note }), tr("شكرًا لك! سُجّل إتمام المهمة.", "Thank you!"));
            if (r) { setDone(null); reload(); }
          }}>{tr("سجّل الإتمام", "Record completion")}</button>
        </Dialog>
      )}
    </>
  );
}

function MyContributions() {
  const { tr, lang } = useI18n();
  const { data, error, loading, reload } = useLoad<Paged<Pledge>>("/pledges/?page_size=200");
  const offers = useLoad<{ id: number; need_title: string; initiative: number; status: string; message: string }[] | Paged<{ id: number; need_title: string; initiative: number; status: string; message: string }>>("/help-offers/?mine=1");
  const { busy, run } = useAction();
  const [proof, setProof] = useState<Pledge | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [ref, setRef] = useState("");
  const nav = useNavigate();
  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorState error={error} onRetry={reload} />;
  const offerList = offers.data ? ("results" in offers.data ? offers.data.results : offers.data) : [];
  return (
    <div className="stack">
      {!data!.results.length && !offerList.length && <EmptyState icon="give" title={tr("لا مساهمات بعد", "No contributions yet")} action={<Link className="btn" to="/contribute">{tr("ساهم", "Contribute")}</Link>} />}
      {data!.results.length > 0 && (
        <ul className="list panel">
          {data!.results.map((p) => {
            const lastPay = p.payments[p.payments.length - 1];
            return (
              <li key={p.id} className="list-item"><Icon name="give" /><div className="grow">
                <div className="row"><b className="num">{money(p.amount, lang)}</b><StatusBadge status={p.status} label={p.status_label} />{lastPay?.is_simulated && <span className="badge demo">{tr("محاكي", "Simulated")}</span>}</div>
                <div className="xs muted"><Link to={`/initiatives/${p.initiative}`}>{p.initiative_title}</Link> — {formatDate(p.created_at, lang)}{p.organization_name && ` — ${p.organization_name}`}</div>
                {lastPay?.receipt_number && <div className="xs">{tr("إيصال", "Receipt")} <bdi>{lastPay.receipt_number}</bdi></div>}
                {lastPay?.status === "failed" && <div className="small" style={{ color: "var(--danger)" }}>{tr("فشلت آخر محاولة دفع", "Last payment failed")}: {lastPay.failure_reason}</div>}
                {p.transfer_proofs.some((t) => t.status === "pending") && <div className="small" style={{ color: "var(--yellow-ink)" }}>{tr("إثبات التحويل بانتظار مطابقة المحاسب — لم يُحتسب بعد", "Transfer proof awaiting reconciliation")}</div>}
              </div>
                <div className="row">
                  {["pledged", "awaiting_payment"].includes(p.status) && p.method === "online" && (
                    <button className="btn small teal" disabled={busy} onClick={async () => {
                      const pay = await run(() => post<{ provider_payment_id: string; is_simulated: boolean; checkout_url: string }>(`/pledges/${p.id}/pay/`));
                      if (pay?.is_simulated) nav(`/contribute/simulator/${pay.provider_payment_id}`);
                      else if (pay?.checkout_url) window.location.href = pay.checkout_url;
                    }}>{tr("ادفع", "Pay")}</button>)}
                  {["pledged", "awaiting_payment"].includes(p.status) && p.method === "bank_transfer" && (
                    <button className="btn small" onClick={() => setProof(p)}>{tr("ارفع إيصال التحويل", "Upload receipt")}</button>)}
                  {["pledged", "awaiting_payment"].includes(p.status) && (
                    <button className="btn small ghost" disabled={busy} onClick={() => run(() => post(`/pledges/${p.id}/cancel/`), tr("أُلغي التعهد", "Pledge cancelled")).then(reload)}>{tr("إلغاء التعهد", "Cancel")}</button>)}
                </div>
              </li>
            );
          })}
        </ul>
      )}
      {offerList.length > 0 && (
        <>
          <h2>{tr("عروض المساعدة العينية والخدمية", "In-kind & service offers")}</h2>
          <ul className="list panel">{offerList.map((o) => (
            <li key={o.id} className="list-item"><Icon name="box" /><div className="grow"><div className="row"><b>{o.need_title}</b>
              <StatusBadge status={o.status} label={{ offered: tr("معروض", "Offered"), accepted: tr("مقبول ومحجوز", "Accepted"), fulfilled: tr("مستلم", "Received"), declined: tr("معتذر عنه", "Declined"), withdrawn: tr("مسحوب", "Withdrawn") }[o.status]} /></div>
              <div className="small muted">{o.message}</div></div></li>
          ))}</ul>
        </>
      )}
      {proof && (
        <Dialog title={tr("إيصال التحويل المصرفي", "Bank transfer receipt")} onClose={() => setProof(null)}>
          <p className="small muted">{tr("صورة الإيصال وحدها لا تؤكد الدفع. يطابقها المحاسب مع كشف الحساب ثم يصلك إشعار.", "A screenshot alone doesn't confirm payment; an accountant reconciles it.")}</p>
          <Field id="rf" label={tr("رقم العملية (إن وجد)", "Transaction reference")}><input id="rf" className="input" dir="ltr" value={ref} onChange={(e) => setRef(e.target.value)} /></Field>
          <label className="btn ghost"><Icon name="camera" size={20} />{file ? file.name : tr("اختر صورة الإيصال", "Choose receipt image")}
            <input type="file" accept="image/*,application/pdf" className="sr-only" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></label>
          <button className="btn block" style={{ marginTop: 12 }} disabled={busy || !file} onClick={async () => {
            const r = await run(() => uploadReceipt(proof.id, file!, ref), tr("استلمنا الإيصال وهو بانتظار المطابقة.", "Receipt received."));
            if (r !== undefined) { setProof(null); reload(); }
          }}>{tr("ارفع", "Upload")}</button>
        </Dialog>
      )}
    </div>
  );
}

function MyReservations() {
  const { tr, lang } = useI18n();
  const { data, error, loading, reload } = useLoad<Reservation[]>("/reservations/mine/");
  const { busy, run } = useAction();
  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorState error={error} onRetry={reload} />;
  if (!data!.length) return <EmptyState icon="store" title={tr("لا حجوزات", "No reservations")} action={<Link className="btn" to="/aawen?tab=store">{tr("مخزن الخير", "Goodwill store")}</Link>} />;
  return (
    <ul className="list panel">
      {data!.map((r) => (
        <li key={r.id} className="list-item"><Icon name="store" /><div className="grow">
          <div className="row"><b>{r.resource_title}</b><StatusBadge status={r.status} label={{ reserved: tr("محجوز — بانتظار الاستلام", "Reserved"), picked_up: tr("مستلم", "Picked up"), returned: tr("مُرجع", "Returned"), cancelled: tr("ملغى", "Cancelled"), overdue: tr("متأخر الإرجاع", "Overdue") }[r.status]} /></div>
          <div className="xs muted">{r.quantity} — {r.pickup_location}{r.due_return_at && ` — ${tr("الإرجاع قبل", "return by")} ${formatDate(r.due_return_at, lang)}`}</div>
        </div>{r.status === "reserved" && <button className="btn small ghost" disabled={busy} onClick={() => run(() => post(`/reservations/${r.id}/cancel/`), tr("أُلغي الحجز", "Cancelled")).then(reload)}>{tr("إلغاء", "Cancel")}</button>}</li>
      ))}
    </ul>
  );
}

function MyObjections() {
  const { tr, lang } = useI18n();
  const { data, error, loading, reload } = useLoad<Paged<{ id: number; report: number; report_tracking: string; reason: string; status: string; decision_note: string; created_at: string }>>("/objections/?mine=1");
  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorState error={error} onRetry={reload} />;
  if (!data!.results.length) return <EmptyState icon="vote" title={tr("لا اعتراضات", "No objections")}>{tr("إذا أُغلق بلاغ والمشكلة باقية، اعترض من صفحة البلاغ.", "Object from the report page if a closed problem persists.")}</EmptyState>;
  return (
    <ul className="list panel">{data!.results.map((o) => (
      <li key={o.id}><Link className="list-item" to={`/reports/${o.report}`}><Icon name="vote" /><div className="grow">
        <div className="row"><b><bdi>{o.report_tracking}</bdi></b><StatusBadge status={o.status === "open" ? "under_review" : o.status === "accepted" ? "resolved" : "rejected"} label={{ open: tr("قيد المراجعة", "Under review"), accepted: tr("مقبول", "Accepted"), rejected: tr("مرفوض", "Rejected") }[o.status]} /></div>
        <div className="small">{o.reason}</div>{o.decision_note && <div className="xs muted">{tr("قرار المراجعة", "Decision")}: {o.decision_note}</div>}
        <div className="xs muted">{formatDate(o.created_at, lang)}</div></div></Link></li>
    ))}</ul>
  );
}

function Account() {
  const { tr, lang, setLang } = useI18n();
  const { me, logout, refreshMe } = useAuth();
  const nav = useNavigate();
  const { busy, run } = useAction();
  const [sessions, setSessions] = useState<{ jti: string; created_at: string }[]>([]);
  const [confirmDel, setConfirmDel] = useState(false);
  useEffect(() => { get<typeof sessions>("/auth/sessions").then(setSessions).catch(() => {}); }, []);
  if (!me) return null;
  return (
    <div className="stack" style={{ maxWidth: 640 }}>
      <div className="panel">
        <h2>{tr("الحساب", "Account")}</h2>
        <dl className="kv"><dt>{tr("الهاتف", "Phone")}</dt><dd dir="ltr" style={{ textAlign: "start" }}>{me.phone}</dd>
          <dt>{tr("الاسم", "Name")}</dt><dd>{me.display_name || "—"}</dd>
          <dt>{tr("الأدوار", "Roles")}</dt><dd>{me.roles.map((r) => r.role_label + (r.area_name ? ` (${r.area_name})` : "") + (r.agency_name ? ` (${r.agency_name})` : "")).join("، ") || tr("مواطن", "Citizen")}</dd></dl>
        <div className="row" style={{ marginTop: 10 }}>
          <button className="btn ghost small" onClick={() => setLang(lang === "ar" ? "en" : "ar")}><Icon name="globe" size={18} />{lang === "ar" ? "English" : "العربية"}</button>
          <button className="btn ghost small" onClick={() => logout().then(() => nav("/"))}><Icon name="logout" size={18} className="flip" />{tr("تسجيل الخروج", "Sign out")}</button>
        </div>
      </div>
      <div className="panel">
        <h2>{tr("الأجهزة المسجّلة", "Signed-in devices")}</h2>
        <p className="small muted">{num(sessions.length, lang)} {tr("جلسة نشطة", "active sessions")}</p>
        <button className="btn ghost small" disabled={busy} onClick={async () => {
          await run(() => del("/auth/sessions"), tr("أُنهيت كل الجلسات. سجّل الدخول من جديد.", "All sessions ended."));
          await logout(); nav("/login");
        }}>{tr("سجّل الخروج من كل الأجهزة", "Sign out everywhere")}</button>
      </div>
      <div className="panel">
        <h2>{tr("حذف الحساب", "Delete account")}</h2>
        {me.pending_deletion ? (
          <>
            <p className="small">{tr("سيُحذف حسابك في", "Your account will be deleted on")} {formatDate(me.pending_deletion, lang)}.</p>
            <button className="btn ghost small" disabled={busy} onClick={() => run(() => del("/me/deletion"), tr("أُلغي طلب الحذف", "Deletion cancelled")).then(refreshMe)}>{tr("ألغِ طلب الحذف", "Cancel deletion")}</button>
          </>
        ) : (
          <>
            <p className="small muted">{tr("نحذف بياناتك الشخصية بعد 7 أيام. تبقى البلاغات العامة بلا هوية، وتبقى السجلات المالية لأغراض المحاسبة دون بياناتك.",
              "Personal data is removed after 7 days; public reports remain anonymous.")}</p>
            <button className="btn danger small" onClick={() => setConfirmDel(true)}>{tr("اطلب حذف حسابي", "Request account deletion")}</button>
          </>
        )}
      </div>
      {confirmDel && (
        <Dialog title={tr("تأكيد حذف الحساب", "Confirm deletion")} onClose={() => setConfirmDel(false)}>
          <p>{tr("يمكنك إلغاء الطلب خلال 7 أيام.", "You can cancel within 7 days.")}</p>
          <button className="btn danger block" disabled={busy} onClick={async () => { await run(() => post("/me/deletion"), tr("سُجّل طلب الحذف", "Deletion requested")); setConfirmDel(false); refreshMe(); }}>{tr("نعم، احذف حسابي", "Yes, delete my account")}</button>
        </Dialog>
      )}
    </div>
  );
}
