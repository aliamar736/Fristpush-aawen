import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { post, tokens, uploadMedia } from "../../api/client";
import type { Initiative, Paged, Payment } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Icon } from "../../components/Icon";
import { PageHeader } from "../../components/Shell";
import { Dialog, EmptyState, ErrorState, Field, Loading, StatusBadge, useAction } from "../../components/ui";
import { formatDate, money } from "../../lib/format";
import { useLoad } from "../../lib/hooks";
import { useI18n } from "../../lib/i18n";

const TABS: [string, string, string][] = [["transfers", "مطابقة التحويلات", "Transfer matching"], ["disbursements", "طلبات الصرف", "Disbursements"],
  ["refunds", "الاسترداد", "Refunds"], ["payments", "الدفعات", "Payments"], ["ledger", "السجل المالي", "Ledger"], ["reconciliation", "المطابقة العامة", "Reconciliation"]];

export default function Finance() {
  const { tr } = useI18n();
  const { config } = useAuth();
  const [sp, setSp] = useSearchParams();
  const tab = sp.get("tab") ?? "transfers";
  return (
    <div>
      <PageHeader title={tr("المساهمات والصرف", "Contributions & spending")} />
      <div className={`banner ${config?.payments.accepting_real_money ? "ok" : "warn"}`} style={{ marginBottom: 12 }}>
        <Icon name="shield" size={20} /><span>{tr("وضع الدفع", "Payment mode")}: <b>{({ simulated: tr("محاكاة", "Simulated"), disabled: tr("معطّل", "Disabled"), live: tr("حقيقي", "Live") } as Record<string, string>)[config?.payments.mode ?? ""] ?? config?.payments.mode}</b> — {config?.payments.message}
          {config?.payments.missing && ` (${tr("ينقص", "missing")}: ${config.payments.missing.join(", ")})`}</span>
      </div>
      <div className="tabs" role="tablist">{TABS.map(([k, a, e]) => <button key={k} role="tab" aria-selected={tab === k} onClick={() => setSp({ tab: k })}>{tr(a, e)}</button>)}</div>
      {tab === "transfers" && <Transfers />}
      {tab === "disbursements" && <Disbursements />}
      {tab === "refunds" && <Refunds />}
      {tab === "payments" && <Payments />}
      {tab === "ledger" && <Ledger />}
      {tab === "reconciliation" && <Reconciliation />}
    </div>
  );
}

function Transfers() {
  const { tr, lang } = useI18n();
  const { hasRole } = useAuth();
  const { data, error, loading, reload } = useLoad<{ id: number; pledge: number; initiative: string; amount: string; claimed_reference: string; image: string; created_at: string }[]>("/finance/transfer-proofs/");
  const [sel, setSel] = useState<number | null>(null);
  const [f, setF] = useState({ bank_reference: "", amount: "", note: "" });
  const { busy, run } = useAction();
  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorState error={error} onRetry={reload} />;
  return (
    <>
      <p className="small muted">{tr("صورة الإيصال ليست دفعة. طابق كل إثبات مع كشف الحساب المصرفي قبل تسجيله.", "A screenshot isn't a payment — match it against the bank statement first.")}</p>
      {data!.length === 0 ? <EmptyState icon="check" title={tr("لا إثباتات بانتظار المطابقة", "Nothing to match")} /> : (
        <div className="table-wrap"><table className="data"><thead><tr><th>{tr("المبادرة", "Initiative")}</th><th>{tr("المبلغ المتعهد", "Pledged")}</th><th>{tr("المرجع المذكور", "Claimed ref")}</th><th>{tr("الإيصال", "Receipt")}</th><th /></tr></thead>
          <tbody>{data!.map((t) => <tr key={t.id}><td>{t.initiative}<div className="xs muted">{formatDate(t.created_at, lang, true)}</div></td><td className="num">{money(t.amount, lang)}</td><td dir="ltr">{t.claimed_reference || "—"}</td>
            <td><a href={t.image} target="_blank" rel="noreferrer">{tr("عرض", "View")}</a></td>
            <td>{hasRole("accountant") && <button className="btn small" onClick={() => { setSel(t.id); setF({ bank_reference: t.claimed_reference, amount: t.amount, note: "" }); }}>{tr("طابق", "Match")}</button>}</td></tr>)}</tbody></table></div>
      )}
      {sel && (
        <Dialog title={tr("مطابقة مع كشف الحساب", "Match with bank statement")} onClose={() => setSel(null)}>
          <Field id="br" label={tr("رقم العملية في كشف الحساب", "Statement reference")}><input id="br" className="input" dir="ltr" value={f.bank_reference} onChange={(e) => setF({ ...f, bank_reference: e.target.value })} /></Field>
          <Field id="ba" label={tr("المبلغ الوارد فعلًا", "Amount actually received")}><input id="ba" className="input" dir="ltr" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></Field>
          <Field id="bn" label={tr("ملاحظة", "Note")}><input id="bn" className="input" value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} /></Field>
          <div className="row">
            <button className="btn teal" disabled={busy || !f.bank_reference} onClick={() => run(() => post(`/finance/transfer-proofs/${sel}/match/`, { ...f, matched: true }), tr("طوبق وسُجّل في السجل المالي", "Matched & booked")).then((r) => { if (r) { setSel(null); reload(); } })}>{tr("مطابق — سجّل الدفعة", "Matched — book it")}</button>
            <button className="btn danger" disabled={busy} onClick={() => run(() => post(`/finance/transfer-proofs/${sel}/match/`, { matched: false, note: f.note }), tr("رُفض الإثبات", "Rejected")).then((r) => { if (r) { setSel(null); reload(); } })}>{tr("غير موجود في الكشف", "Not on statement")}</button>
          </div>
        </Dialog>
      )}
    </>
  );
}

type Disb = { id: number; initiative: number; initiative_title: string; amount: string; purpose: string; payee_name: string; status: string; status_label: string; requested_by: number; approved_by: number | null; decision_note: string; paid_at: string | null; payment_reference: string };

function Disbursements() {
  const { tr, lang } = useI18n();
  const { hasRole, me } = useAuth();
  const { data, error, loading, reload } = useLoad<Paged<Disb>>("/finance/disbursements/?page_size=200");
  const inis = useLoad<Paged<Initiative>>("/initiatives/?page_size=200");
  const [req, setReq] = useState(false);
  const [pay, setPay] = useState<Disb | null>(null);
  const [f, setF] = useState({ initiative: "", amount: "", purpose: "", payee_name: "" });
  const [p, setP] = useState({ payment_reference: "", public_result: "" });
  const [file, setFile] = useState<File | null>(null);
  const { busy, run } = useAction();
  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorState error={error} onRetry={reload} />;
  return (
    <>
      <div className="row between"><p className="small muted" style={{ margin: 0 }}>{tr("الطلب ← اعتماد المراجع المالي (غير الطالب) ← تنفيذ المحاسب (غير المعتمد) مع إيصال.", "Request → financial auditor approval → accountant payment with receipt.")}</p>
        <button className="btn small" onClick={() => setReq(true)}>{tr("طلب صرف", "Request disbursement")}</button></div>
      <div className="table-wrap" style={{ marginTop: 8 }}><table className="data"><thead><tr><th>{tr("المبادرة", "Initiative")}</th><th>{tr("المبلغ", "Amount")}</th><th>{tr("الغرض / المستفيد", "Purpose / payee")}</th><th>{tr("الحالة", "Status")}</th><th /></tr></thead>
        <tbody>{data!.results.map((d) => <tr key={d.id}><td>{d.initiative_title}</td><td className="num">{money(d.amount, lang)}</td><td>{d.purpose}<div className="xs muted">{d.payee_name}</div></td>
          <td><StatusBadge status={d.status === "paid" ? "succeeded" : d.status} label={d.status_label} />{d.decision_note && <div className="xs muted">{d.decision_note}</div>}</td>
          <td className="row">
            {d.status === "requested" && hasRole("financial_auditor") && d.requested_by !== me?.id && <>
              <button className="btn small teal" disabled={busy} onClick={() => run(() => post(`/finance/disbursements/${d.id}/decide/`, { approve: true }), tr("اعتُمد", "Approved")).then(reload)}>{tr("اعتمد", "Approve")}</button>
              <button className="btn small ghost" disabled={busy} onClick={() => { const n = window.prompt(tr("سبب الرفض", "Reason")); if (n) run(() => post(`/finance/disbursements/${d.id}/decide/`, { approve: false, note: n }), tr("رُفض", "Rejected")).then(reload); }}>{tr("ارفض", "Reject")}</button></>}
            {d.status === "approved" && hasRole("accountant") && d.approved_by !== me?.id && <button className="btn small" onClick={() => setPay(d)}>{tr("نفّذ الصرف", "Pay")}</button>}
          </td></tr>)}</tbody></table></div>
      {req && (
        <Dialog title={tr("طلب صرف", "Request disbursement")} onClose={() => setReq(false)}>
          <Field id="di" label={tr("المبادرة", "Initiative")}><select id="di" className="input" value={f.initiative} onChange={(e) => setF({ ...f, initiative: e.target.value })}><option value="">—</option>{inis.data?.results.map((i) => <option key={i.id} value={i.id}>{i.title}</option>)}</select></Field>
          <Field id="da" label={tr("المبلغ", "Amount")}><input id="da" className="input" dir="ltr" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></Field>
          <Field id="dp" label={tr("الغرض", "Purpose")}><input id="dp" className="input" value={f.purpose} onChange={(e) => setF({ ...f, purpose: e.target.value })} /></Field>
          <Field id="dy" label={tr("المستفيد (مورد/مقاول)", "Payee")}><input id="dy" className="input" value={f.payee_name} onChange={(e) => setF({ ...f, payee_name: e.target.value })} /></Field>
          <button className="btn block" disabled={busy} onClick={() => run(() => post("/finance/disbursements/", f), tr("أُرسل الطلب للاعتماد", "Submitted")).then((r) => { if (r) { setReq(false); reload(); } })}>{tr("أرسل", "Submit")}</button>
        </Dialog>
      )}
      {pay && (
        <Dialog title={`${tr("تنفيذ صرف", "Pay")} ${money(pay.amount, lang)}`} onClose={() => setPay(null)}>
          <Field id="pr" label={tr("مرجع الصرف (صك/تحويل)", "Payment reference")}><input id="pr" className="input" dir="ltr" value={p.payment_reference} onChange={(e) => setP({ ...p, payment_reference: e.target.value })} /></Field>
          <Field id="pu" label={tr("النتيجة المنشورة للعامة", "Public result")}><input id="pu" className="input" value={p.public_result} onChange={(e) => setP({ ...p, public_result: e.target.value })} /></Field>
          <label className="btn ghost"><Icon name="doc" size={20} />{file ? file.name : tr("الإيصال أو الفاتورة (مطلوب)", "Receipt (required)")}<input type="file" accept="image/*,application/pdf" className="sr-only" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></label>
          <button className="btn block teal" style={{ marginTop: 12 }} disabled={busy || !file || !p.payment_reference} onClick={() => run(async () => post(`/finance/disbursements/${pay.id}/pay/`, { ...p, receipt: await uploadMedia(file!, "document") }), tr("سُجّل الصرف", "Paid")).then((r) => { if (r) { setPay(null); reload(); } })}>{tr("سجّل الصرف", "Record payment")}</button>
        </Dialog>
      )}
    </>
  );
}

function Refunds() {
  const { tr, lang } = useI18n();
  const { hasRole, me } = useAuth();
  const { data, error, loading, reload } = useLoad<{ id: number; payment: number; amount: string; reason: string; status: string; initiative: string; provider: string; requested_by: number }[]>("/finance/refunds/");
  const { busy, run } = useAction();
  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorState error={error} onRetry={reload} />;
  return data!.length === 0 ? <EmptyState icon="refresh" title={tr("لا طلبات استرداد", "No refunds")}>{tr("يبدأ الاسترداد من تبويب «الدفعات».", "Start a refund from Payments.")}</EmptyState> : (
    <div className="table-wrap"><table className="data"><thead><tr><th>{tr("المبادرة", "Initiative")}</th><th>{tr("المبلغ", "Amount")}</th><th>{tr("السبب", "Reason")}</th><th>{tr("الحالة", "Status")}</th><th /></tr></thead>
      <tbody>{data!.map((r) => <tr key={r.id}><td>{r.initiative}</td><td className="num">{money(r.amount, lang)}</td><td>{r.reason}</td><td>{r.status}</td>
        <td className="row">{r.status === "requested" && hasRole("financial_auditor") && r.requested_by !== me?.id && <button className="btn small teal" disabled={busy} onClick={() => run(() => post(`/finance/refunds/${r.id}/approve/`, { approve: true }), tr("اعتُمد", "Approved")).then(reload)}>{tr("اعتمد", "Approve")}</button>}
          {r.status === "approved" && ["bank_transfer", "cash"].includes(r.provider) && hasRole("accountant") && <button className="btn small" disabled={busy} onClick={() => { const ref = window.prompt(tr("مرجع التحويل العكسي", "Refund reference")); if (ref) run(() => post(`/finance/refunds/${r.id}/complete/`, { reference: ref }), tr("نُفذ", "Done")).then(reload); }}>{tr("نفّذ يدويًا", "Complete manually")}</button>}</td></tr>)}</tbody></table></div>
  );
}

function Payments() {
  const { tr, lang } = useI18n();
  const { hasRole } = useAuth();
  const { data, error, loading, reload } = useLoad<Paged<Payment>>("/finance/payments/?page_size=200");
  const { busy, run } = useAction();
  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorState error={error} onRetry={reload} />;
  return (
    <div className="table-wrap"><table className="data"><thead><tr><th>#</th><th>{tr("المزود", "Provider")}</th><th>{tr("المبلغ", "Amount")}</th><th>{tr("الرسوم", "Fee")}</th><th>{tr("الحالة", "Status")}</th><th>{tr("الإيصال", "Receipt")}</th><th /></tr></thead>
      <tbody>{data!.results.map((p) => <tr key={p.id}><td>{p.id}</td><td>{p.provider}{p.is_simulated && <span className="badge demo" style={{ marginInlineStart: 4 }}>{tr("محاكي", "Sim")}</span>}</td>
        <td className="num">{money(p.amount, lang)}</td><td className="num">{p.fee}</td><td><StatusBadge status={p.status} />{p.failure_reason && <div className="xs muted">{p.failure_reason}</div>}</td><td><bdi>{p.receipt_number ?? "—"}</bdi></td>
        <td>{hasRole("accountant") && ["succeeded", "partially_refunded"].includes(p.status) && <button className="btn small ghost" disabled={busy} onClick={() => {
          const amount = window.prompt(tr("مبلغ الاسترداد", "Refund amount"), p.amount); const reason = amount && window.prompt(tr("السبب", "Reason"));
          if (amount && reason) run(() => post("/finance/refunds/", { payment: p.id, amount, reason }), tr("طُلب الاسترداد وينتظر اعتماد المراجع المالي", "Refund requested")).then(reload);
        }}>{tr("اطلب استردادًا", "Request refund")}</button>}</td></tr>)}</tbody></table></div>
  );
}

function Ledger() {
  const { tr, lang } = useI18n();
  const { data, error, loading, reload } = useLoad<{ id: number; at: string; initiative: string; type: string; direction: string; amount: string; memo: string; simulated: boolean }[]>("/finance/ledger");
  const download = async () => {
    const r = await fetch("/api/v1/finance/ledger?export=csv", { headers: { Authorization: `Bearer ${tokens.get()?.access}` } });
    const url = URL.createObjectURL(await r.blob());
    const a = document.createElement("a"); a.href = url; a.download = "aawen-ledger.csv"; a.click(); URL.revokeObjectURL(url);
  };
  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorState error={error} onRetry={reload} />;
  return (
    <>
      <div className="row between"><p className="small muted" style={{ margin: 0 }}>{tr("سجل إضافي فقط: لا يمكن تعديل أو حذف أي قيد (محمي على مستوى قاعدة البيانات).", "Append-only ledger, protected at database level.")}</p>
        <button className="btn small ghost" onClick={download}><Icon name="doc" size={18} />{tr("تصدير CSV", "Export CSV")}</button></div>
      <div className="table-wrap" style={{ marginTop: 8 }}><table className="data"><thead><tr><th>{tr("التاريخ", "Date")}</th><th>{tr("المبادرة", "Initiative")}</th><th>{tr("النوع", "Type")}</th><th>{tr("مدين/دائن", "Dr/Cr")}</th><th>{tr("المبلغ", "Amount")}</th><th>{tr("البيان", "Memo")}</th></tr></thead>
        <tbody>{data!.map((e) => <tr key={e.id}><td>{formatDate(e.at, lang, true)}</td><td>{e.initiative}</td><td>{({ collection: tr("تحصيل", "Collection"), fee: tr("رسوم", "Fee"), disbursement: tr("صرف", "Disbursement"), refund: tr("استرداد", "Refund"), adjustment: tr("تسوية", "Adjustment") } as Record<string, string>)[e.type] ?? e.type}{e.simulated && <span className="badge demo" style={{ marginInlineStart: 4 }}>{tr("محاكي", "Sim")}</span>}</td>
          <td>{e.direction === "credit" ? tr("دائن", "Cr") : tr("مدين", "Dr")}</td><td className="num">{money(e.amount, lang)}</td><td>{e.memo}</td></tr>)}</tbody></table></div>
    </>
  );
}

function Reconciliation() {
  const { tr, lang } = useI18n();
  const { data, error, loading, reload } = useLoad<{ ok: boolean; payments_confirmed_total: string; ledger_collections_total: string; pending_transfer_proofs: number; payments_needing_review: number; duplicate_webhook_deliveries: number; problems: { issue: string }[]; mode: string }>("/finance/reconciliation");
  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorState error={error} onRetry={reload} />;
  const d = data!;
  return (
    <div className="panel">
      <div className={`banner ${d.ok ? "ok" : "error"}`} style={{ marginBottom: 12 }}>{d.ok ? tr("السجل المالي متطابق مع الدفعات المؤكدة.", "Ledger matches confirmed payments.") : tr("توجد فروقات تحتاج مراجعة.", "Discrepancies found.")}</div>
      <dl className="kv">
        <dt>{tr("مجموع الدفعات المؤكدة", "Confirmed payments")}</dt><dd className="num">{money(d.payments_confirmed_total, lang)}</dd>
        <dt>{tr("مجموع قيود التحصيل", "Ledger collections")}</dt><dd className="num">{money(d.ledger_collections_total, lang)}</dd>
        <dt>{tr("إثباتات تحويل بانتظار المطابقة", "Pending transfer proofs")}</dt><dd>{d.pending_transfer_proofs}</dd>
        <dt>{tr("دفعات تحتاج مراجعة (مبلغ غير مطابق)", "Payments needing review")}</dt><dd>{d.payments_needing_review}</dd>
        <dt>{tr("إشعارات مزود مكررة (تجاهلها النظام)", "Duplicate provider notifications (ignored)")}</dt><dd>{d.duplicate_webhook_deliveries}</dd>
      </dl>
      {d.problems.length > 0 && <ul>{d.problems.map((p, i) => <li key={i}>{p.issue}</li>)}</ul>}
    </div>
  );
}
