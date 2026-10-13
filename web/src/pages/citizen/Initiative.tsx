import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { post, uploadMedia } from "../../api/client";
import type { Initiative, Need, Paged, Pledge, Task } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Icon } from "../../components/Icon";
import { PageHeader } from "../../components/Shell";
import { DemoBadge, Dialog, EmptyState, ErrorState, Field, Loading, StatusBadge, useAction } from "../../components/ui";
import { formatDate, money, uuid } from "../../lib/format";
import { useLoad } from "../../lib/hooks";
import { compressImage } from "../../lib/image";
import { useI18n } from "../../lib/i18n";
import { TaskCard } from "./Aawen";

export function PledgeDialog({ ini, need, onClose }: { ini: Pick<Initiative, "id" | "title">; need?: Need | null; onClose: () => void }) {
  const { tr } = useI18n();
  const { config } = useAuth();
  const nav = useNavigate();
  const { busy, run } = useAction();
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState<"online" | "bank_transfer">(config?.payments.mode === "disabled" ? "bank_transfer" : "online");
  const [org, setOrg] = useState("");
  const [cid] = useState(uuid);
  const submit = async () => {
    const p = await run(() => post<Pledge>("/pledges/", { initiative: ini.id, need: need?.id ?? null, amount, method, organization_name: org, client_id: cid },
      { idempotencyKey: cid }), tr("سُجّل تعهدك. التعهد ليس دفعة؛ تُحسب المساهمة عند تأكيد الدفع.", "Pledge recorded."));
    if (!p) return;
    if (method === "online") {
      const pay = await run(() => post<{ provider_payment_id: string; checkout_url: string; is_simulated: boolean }>(`/pledges/${p.id}/pay/`));
      if (pay?.is_simulated) return nav(`/contribute/simulator/${pay.provider_payment_id}?pledge=${p.id}`);
      if (pay?.checkout_url) return (window.location.href = pay.checkout_url);
    }
    nav("/me?tab=contributions");
  };
  return (
    <Dialog title={`${tr("ساهم في", "Contribute to")}: ${ini.title}`} onClose={onClose}>
      <div className={`banner ${config?.payments.accepting_real_money ? "info" : "warn"}`} style={{ marginBottom: 12 }}>
        <Icon name="shield" size={20} /><span>{config?.payments.message || tr("المساهمات تذهب للمبادرة المعتمدة فقط، وتُنشر المصروفات ونتائجها.", "Contributions go to the approved initiative only.")}</span>
      </div>
      {need && <p className="small">{tr("لاحتياج", "For need")}: <b>{need.title}</b></p>}
      <Field id="amt" label={tr("المبلغ بالدينار الليبي", "Amount (LYD)")}>
        <input id="amt" className="input num" inputMode="decimal" dir="ltr" value={amount} onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ""))} />
      </Field>
      <fieldset className="field" style={{ border: 0, padding: 0 }}>
        <legend className="label">{tr("طريقة الدفع", "Payment method")}</legend>
        <div className="chips" role="radiogroup">
          <button role="radio" className="chip" aria-checked={method === "online"} disabled={config?.payments.mode === "disabled"} onClick={() => setMethod("online")}>
            {tr("دفع إلكتروني", "Online")}{config?.payments.mode === "simulated" ? tr(" (محاكي)", " (simulator)") : ""}</button>
          <button role="radio" className="chip" aria-checked={method === "bank_transfer"} onClick={() => setMethod("bank_transfer")}>{tr("تحويل مصرفي", "Bank transfer")}</button>
        </div>
        {method === "bank_transfer" && <span className="hint">{tr("بعد التحويل ارفع صورة الإيصال من «أثري». لا تُعد المساهمة مؤكدة حتى يطابقها المحاسب مع كشف الحساب.", "Upload the receipt afterwards; it counts once an accountant matches it.")}</span>}
      </fieldset>
      <Field id="org" label={tr("باسم شركة أو جهة (اختياري)", "On behalf of a company (optional)")}><input id="org" className="input" value={org} onChange={(e) => setOrg(e.target.value)} /></Field>
      <button className="btn teal block" disabled={busy || !(Number(amount) > 0)} onClick={submit}>{tr("سجّل التعهد", "Make the pledge")}</button>
    </Dialog>
  );
}

export default function InitiativeDetail() {
  const { id } = useParams();
  const { tr, lang } = useI18n();
  const { me } = useAuth();
  const { data: ini, error, loading, reload } = useLoad<Initiative>(`/initiatives/${id}/`, [id]);
  const tasks = useLoad<Paged<Task>>(`/tasks/?initiative=${id}&all=1`, [id]);
  const ledger = useLoad<{ id: number; amount: string; purpose: string; payee: string; paid_at: string; result: string; has_receipt: boolean }[]>(`/initiatives/${id}/ledger/`, [id]);
  const [pledgeFor, setPledgeFor] = useState<Need | null | undefined>(undefined);
  const [offerFor, setOfferFor] = useState<Need | null>(null);
  const [msg, setMsg] = useState("");
  const { busy, run } = useAction();
  if (loading && !ini) return <Loading lines={6} />;
  if (error && !ini) return <ErrorState error={error} onRetry={reload} />;
  if (!ini) return null;
  const accepting = ["approved", "active"].includes(ini.status);
  const f = ini.finance;
  const pct = f && Number(f.funding_target) > 0 ? Math.min(100, (Number(f.collected) / Number(f.funding_target)) * 100) : 0;
  return (
    <div style={{ maxWidth: 900, margin: "0 auto" }}>
      <PageHeader title={ini.title} back=""><DemoBadge show={ini.is_demo} /></PageHeader>
      <div className="row" style={{ marginBottom: 12 }}><StatusBadge status={ini.status} label={ini.status_label} /><span className="small muted">{ini.area_name} — {tr("المسؤول", "Lead")}: {ini.manager_name}</span></div>
      <p style={{ maxWidth: "65ch" }}>{ini.summary}</p>
      {ini.description && <p className="muted" style={{ maxWidth: "65ch" }}>{ini.description}</p>}
      {!accepting && <div className="banner warn">{tr("هذه المبادرة غير معتمدة لاستقبال المساهمات حاليًا.", "Not currently accepting contributions.")}</div>}

      <div className="grid two" style={{ marginTop: 12 }}>
        <section className="panel" aria-labelledby="needs-h">
          <h2 id="needs-h">{tr("الاحتياجات", "Needs")}</h2>
          {ini.needs.length === 0 ? <p className="muted">{tr("لا احتياجات معلنة.", "No needs listed.")}</p> : (
            <ul className="list">
              {ini.needs.map((n) => (
                <li key={n.id} id={`need-${n.id}`} className="list-item">
                  <Icon name={n.is_blocking ? "alert" : "box"} />
                  <div className="grow">
                    <div className="row"><b>{n.title}</b>{n.is_blocking && n.status !== "met" && <span className="badge s-wait">{tr("يعطّل المبادرة", "Blocking")}</span>}<StatusBadge status={n.status} /></div>
                    <div className="xs muted">{n.kind_label} — {Number(n.quantity_fulfilled)}/{Number(n.quantity_needed)} {n.unit}</div>
                  </div>
                  {accepting && n.status !== "met" && (n.kind === "funding"
                    ? <button className="btn small teal" onClick={() => (me ? setPledgeFor(n) : (window.location.href = `/login?next=/initiatives/${ini.id}`))}>{tr("ساهم", "Contribute")}</button>
                    : <button className="btn small" onClick={() => (me ? setOfferFor(n) : (window.location.href = `/login?next=/initiatives/${ini.id}`))}>{tr("عندي هذا", "I can help")}</button>)}
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="panel" aria-labelledby="fin-h">
          <h2 id="fin-h">{tr("التمويل والشفافية", "Funding & transparency")}</h2>
          {f && (
            <>
              <div className="progress" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} aria-label={tr("نسبة التمويل المؤكد", "Confirmed funding")}><span style={{ width: `${pct}%` }} /></div>
              <dl className="kv small" style={{ marginTop: 10 }}>
                <dt>{tr("الهدف", "Target")}</dt><dd className="num">{money(f.funding_target, lang)}</dd>
                <dt>{tr("مؤكد مستلم", "Confirmed received")}</dt><dd className="num">{money(f.collected, lang)}</dd>
                <dt>{tr("تعهدات", "Pledged")}</dt><dd className="num">{money(f.pledged_total, lang)}</dd>
                <dt>{tr("مصروف", "Spent")}</dt><dd className="num">{money(f.disbursed, lang)}</dd>
                <dt>{tr("مسترد", "Refunded")}</dt><dd className="num">{money(f.refunded, lang)}</dd>
                <dt>{tr("الرصيد", "Balance")}</dt><dd className="num"><b>{money(f.balance, lang)}</b></dd>
              </dl>
              {f.simulated_entries > 0 && <p className="xs" style={{ color: "var(--yellow-ink)" }}>{tr("يتضمن قيودًا من محاكي الدفع (ليست أموالًا حقيقية).", "Includes simulator entries (not real money).")}</p>}
            </>
          )}
          {accepting && <button className="btn teal" onClick={() => (me ? setPledgeFor(null) : (window.location.href = `/login?next=/initiatives/${ini.id}`))}>{tr("ساهم ماليًا", "Contribute money")}</button>}
          <h3 style={{ marginTop: 16 }}>{tr("سجل المصروفات والنتائج", "Spending & results")}</h3>
          {(ledger.data?.length ?? 0) === 0 ? <p className="muted small">{tr("لا مصروفات بعد.", "No spending yet.")}</p> : (
            <ul className="list">{ledger.data!.map((d) => (
              <li key={d.id} className="list-item"><Icon name="doc" /><div className="grow"><div className="title num">{money(d.amount, lang)} — {d.purpose}</div>
                <div className="xs muted">{d.payee} — {formatDate(d.paid_at, lang)}{d.has_receipt ? ` — ${tr("بإيصال", "receipt on file")}` : ""}</div>
                {d.result && <div className="small">{tr("النتيجة", "Result")}: {d.result}</div>}</div></li>
            ))}</ul>
          )}
        </section>
      </div>

      <div className="section"><h2>{tr("مهام المبادرة", "Tasks")}</h2></div>
      {(tasks.data?.results.length ?? 0) === 0 ? <EmptyState icon="hands" title={tr("لا مهام معلنة بعد", "No tasks yet")} /> :
        <div className="grid two">{tasks.data!.results.map((t) => <TaskCard key={t.id} t={t} onChange={tasks.reload} />)}</div>}
      {ini.results_summary && <><div className="section"><h2>{tr("ماذا أنجزت المبادرة", "Results")}</h2></div><p>{ini.results_summary}</p></>}

      {pledgeFor !== undefined && <PledgeDialog ini={ini} need={pledgeFor} onClose={() => { setPledgeFor(undefined); reload(); }} />}
      {offerFor && (
        <Dialog title={`${tr("عرض مساعدة", "Offer help")}: ${offerFor.title}`} onClose={() => setOfferFor(null)}>
          <p className="small muted">{tr("يصل عرضك لمسؤول المبادرة. يقبله ويحجزه، ثم يسجّل الاستلام.", "The lead accepts, reserves and then records receipt.")}</p>
          <Field id="om" label={tr("ماذا تقدر تقدّم ومتى؟", "What can you offer, and when?")}><textarea id="om" className="input" value={msg} onChange={(e) => setMsg(e.target.value)} /></Field>
          <button className="btn block" disabled={busy || !msg.trim()} onClick={async () => {
            const r = await run(() => post(`/needs/${offerFor.id}/offer/`, { message: msg, kind: offerFor.kind === "service" ? "service" : "in_kind" }), tr("وصل عرضك لمسؤول المبادرة.", "Offer sent."));
            if (r) { setOfferFor(null); setMsg(""); reload(); }
          }}>{tr("أرسل العرض", "Send offer")}</button>
        </Dialog>
      )}
      <p className="xs muted" style={{ marginTop: 24 }}><Link to="/contribute">{tr("سياسات المساهمة والإلغاء والفائض", "Contribution policies")}</Link></p>
    </div>
  );
}

export async function uploadReceipt(pledgeId: number, file: Blob, ref: string) {
  const uid = await uploadMedia(await compressImage(file), "document");
  return post(`/pledges/${pledgeId}/transfer-proof/`, { media: uid, claimed_reference: ref });
}
