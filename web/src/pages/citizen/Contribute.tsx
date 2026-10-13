import { useState } from "react";
import { Link } from "react-router-dom";

import type { Initiative, Need, Paged } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Icon } from "../../components/Icon";
import { DemoBadge, EmptyState, ErrorState, Loading } from "../../components/ui";
import { useLoad } from "../../lib/hooks";
import { useI18n } from "../../lib/i18n";
import { PledgeDialog } from "./Initiative";

export default function Contribute() {
  const { tr } = useI18n();
  const { me, config } = useAuth();
  const inis = useLoad<Paged<Initiative>>("/initiatives/?page_size=100");
  const [pledge, setPledge] = useState<{ ini: Initiative; need: Need | null } | null>(null);
  if (inis.loading && !inis.data) return <Loading lines={5} />;
  if (inis.error && !inis.data) return <ErrorState error={inis.error} onRetry={inis.reload} />;
  const accepting = inis.data!.results.filter((i) => ["approved", "active"].includes(i.status));
  const needs = accepting.flatMap((i) => i.needs.filter((n) => n.status !== "met" && n.status !== "cancelled").map((n) => ({ i, n })));
  const ask = (ini: Initiative, need: Need | null) => (me ? setPledge({ ini, need }) : (window.location.href = "/login?next=/contribute"));
  return (
    <div>
      <h1>{tr("ساهم", "Contribute")}</h1>
      <p className="muted" style={{ maxWidth: "62ch" }}>{tr("كل مساهمة مربوطة بمبادرة معتمدة واحتياج محدد، وتُنشر المصروفات ونتائجها. لا توجد محافظ أو تحويلات بين الأفراد.",
        "Every contribution is tied to an approved initiative and a specific need. Spending and results are published. No person-to-person transfers.")}</p>
      {config && !config.payments.accepting_real_money && (
        <div className="banner warn" style={{ marginBottom: 12 }}><Icon name="shield" size={20} /><span>{config.payments.message}</span></div>
      )}
      <div className="section"><h2>{tr("احتياجات المشاريع", "Project needs")}</h2></div>
      {needs.length === 0 ? <EmptyState icon="give" title={tr("لا احتياجات مفتوحة الآن", "No open needs")} /> : (
        <ul className="list panel">
          {needs.map(({ i, n }) => (
            <li key={n.id} className="list-item">
              <Icon name={n.kind === "funding" ? "give" : n.kind === "service" ? "hands" : "box"} />
              <div className="grow">
                <div className="row"><b>{n.title}</b><span className="badge plain">{n.kind_label}</span>{n.is_blocking && <span className="badge s-wait">{tr("يعطّل المبادرة", "Blocking")}</span>}<DemoBadge show={i.is_demo} /></div>
                <div className="xs muted"><Link to={`/initiatives/${i.id}`}>{i.title}</Link> — {Number(n.quantity_fulfilled)}/{Number(n.quantity_needed)} {n.unit}</div>
              </div>
              {n.kind === "funding" ? <button className="btn small teal" onClick={() => ask(i, n)}>{tr("ساهم ماليًا", "Give money")}</button>
                : <Link className="btn small" to={`/initiatives/${i.id}#need-${n.id}`}>{n.kind === "service" ? tr("قدّم خدمة", "Offer service") : tr("قدّم عينيًا", "Give in kind")}</Link>}
            </li>
          ))}
        </ul>
      )}
      <div className="section"><h2>{tr("مساهمات الشركات والجهات", "Company contributions")}</h2></div>
      <div className="panel small">
        <p>{tr("يمكن للشركات المساهمة باسمها في احتياج محدد (تمويل أو خدمة أو مواد). اكتب اسم الشركة عند التعهد ليظهر في سجل المبادرة بعد تأكيد الدفع.",
          "Companies can contribute under their name to a specific need.")}</p>
      </div>
      <div className="section"><h2>{tr("السياسات", "Policies")}</h2></div>
      <dl className="panel kv small">
        <dt>{tr("الإلغاء", "Cancellation")}</dt><dd>{config?.finance_policies.cancellation}</dd>
        <dt>{tr("الفائض", "Surplus")}</dt><dd>{config?.finance_policies.surplus}</dd>
        <dt>{tr("عدم اكتمال التمويل", "Under-funding")}</dt><dd>{config?.finance_policies.underfunding}</dd>
      </dl>
      {pledge && <PledgeDialog ini={pledge.ini} need={pledge.need} onClose={() => { setPledge(null); inis.reload(); }} />}
    </div>
  );
}
