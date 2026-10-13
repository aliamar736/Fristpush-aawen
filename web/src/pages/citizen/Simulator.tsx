import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { post } from "../../api/client";
import { PageHeader } from "../../components/Shell";
import { useAction } from "../../components/ui";
import { useI18n } from "../../lib/i18n";

/** Development-only stand-in for a payment gateway's hosted checkout. Clearly labelled; no money moves. */
export default function Simulator() {
  const { pid } = useParams();
  const { tr } = useI18n();
  const nav = useNavigate();
  const { busy, run } = useAction();
  const [result, setResult] = useState<string | null>(null);
  const go = async (outcome: "success" | "failure", deliveries = 1) => {
    const r = await run(() => post<{ results: string[] }>(`/finance/simulator/${pid}`, { outcome, deliveries }));
    if (r) setResult(r.results.join("، "));
  };
  return (
    <div style={{ maxWidth: 520, margin: "0 auto" }}>
      <PageHeader title={tr("محاكي الدفع", "Payment simulator")} back="" />
      <div className="banner warn" role="note" style={{ marginBottom: 12 }}>
        {tr("هذه صفحة محاكاة لبيئة التطوير. لا تُخصم أي أموال، والقيود الناتجة معلّمة «محاكي» في السجل المالي.",
          "Development simulator. No money moves; resulting ledger entries are flagged as simulated.")}
      </div>
      <div className="panel stack">
        <p className="small muted" dir="ltr">{pid}</p>
        <button className="btn teal block" disabled={busy} onClick={() => go("success")}>{tr("محاكاة دفع ناجح", "Simulate success")}</button>
        <button className="btn ghost block" disabled={busy} onClick={() => go("success", 3)}>{tr("نجاح مع تكرار الإشعار 3 مرات", "Success with 3 duplicate webhooks")}</button>
        <button className="btn danger block" disabled={busy} onClick={() => go("failure")}>{tr("محاكاة فشل الدفع", "Simulate failure")}</button>
        {result && <div className="banner info" role="status">{tr("نتيجة معالجة الإشعارات:", "Webhook results:")} {result}</div>}
        {result && <button className="btn block" onClick={() => nav("/me?tab=contributions")}>{tr("إلى مساهماتي", "My contributions")}</button>}
      </div>
    </div>
  );
}
