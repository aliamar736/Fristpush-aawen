import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { post } from "../../api/client";
import type { Notification, Paged, Report } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { CATEGORY_ICON, Icon } from "../../components/Icon";
import { MapView } from "../../components/MapView";
import { PageHeader } from "../../components/Shell";
import { DemoBadge, Dialog, EmptyState, ErrorState, Field, Loading, StatusBadge, useAction } from "../../components/ui";
import { formatDate, money, num, timeAgo } from "../../lib/format";
import { useLoad } from "../../lib/hooks";
import { useI18n } from "../../lib/i18n";

export function Notifications() {
  const { tr, lang } = useI18n();
  const nav = useNavigate();
  const { data, error, loading, reload } = useLoad<Paged<Notification>>("/notifications/?page_size=100");
  const { run } = useAction();
  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorState error={error} onRetry={reload} />;
  const open = (n: Notification) => {
    post("/notifications/mark-read/", { ids: [n.id] }).catch(() => {});
    if (n.data.report_id) nav(`/reports/${n.data.report_id}`);
    else if (n.data.initiative_id) nav(`/initiatives/${n.data.initiative_id}`);
    else if (n.data.pledge_id) nav("/me?tab=contributions");
  };
  return (
    <div style={{ maxWidth: 720, margin: "0 auto" }}>
      <PageHeader title={tr("الإشعارات", "Notifications")} back="">
        <button className="btn small ghost" onClick={() => run(() => post("/notifications/mark-read/", {})).then(reload)}>{tr("علّم الكل كمقروء", "Mark all read")}</button>
      </PageHeader>
      {data!.results.length === 0 ? <EmptyState icon="bell" title={tr("لا إشعارات", "No notifications")}>{tr("ستصلك هنا تحديثات بلاغاتك ومهامك ومساهماتك.", "Updates on your reports, tasks and contributions appear here.")}</EmptyState> : (
        <ul className="list panel">
          {data!.results.map((n) => (
            <li key={n.id}><button className="list-item" style={{ width: "100%", background: "none", border: 0, textAlign: "start", cursor: "pointer" }} onClick={() => open(n)}>
              <Icon name="bell" />
              <div className="grow"><div className="title" style={{ fontWeight: n.read_at ? 500 : 700 }}>{n.title}</div>
                {n.body && <div className="small muted">{n.body}</div>}<div className="xs muted">{timeAgo(n.created_at, lang)}</div></div>
              {!n.read_at && <span className="badge s-wait">{tr("جديد", "New")}</span>}
            </button></li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function PlaceProfile() {
  const { tr, lang } = useI18n();
  const [sp] = useSearchParams();
  const lat = Number(sp.get("lat")), lng = Number(sp.get("lng"));
  const { data, error, loading, reload } = useLoad<{ radius_m: number; total_reports: number; recurrences: number; open: number;
    by_category: Record<string, number>; reports: Report[]; initiatives: { id: number; title: string; status: string }[] }>(`/places/profile?lat=${lat}&lng=${lng}`, [lat, lng]);
  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorState error={error} onRetry={reload} />;
  const d = data!;
  return (
    <div style={{ maxWidth: 820, margin: "0 auto" }}>
      <PageHeader title={tr("ملف المكان", "Place history")} back="" />
      <p className="muted small">{tr(`كل ما سُجّل ضمن ${d.radius_m} مترًا من هذه النقطة.`, `Everything recorded within ${d.radius_m} m.`)}</p>
      <div className="grid three">
        <div className="panel stat"><b>{num(d.total_reports, lang)}</b><span className="small muted">{tr("بلاغ", "reports")}</span></div>
        <div className="panel stat"><b>{num(d.open, lang)}</b><span className="small muted">{tr("مفتوح", "open")}</span></div>
        <div className="panel stat"><b>{num(d.recurrences, lang)}</b><span className="small muted">{tr("مرة رجعت فيها مشكلة", "recurrences")}</span></div>
      </div>
      <div className="mini-map" style={{ margin: "12px 0" }}><MapView label={tr("خريطة المكان", "Place map")} cluster={false} center={[lat, lng]} zoom={17}
        markers={d.reports.map((r) => ({ id: r.id, lat: r.lat, lng: r.lng, color: r.status === "resolved" ? "#123F46" : "#0B6E64", label: r.category.name }))} /></div>
      <h2>{tr("السجل", "History")}</h2>
      {d.reports.length === 0 ? <p className="muted">{tr("لا شيء مسجل هنا.", "Nothing recorded here.")}</p> : (
        <ul className="list panel">{d.reports.map((r) => (
          <li key={r.id}><Link className="list-item" to={`/reports/${r.id}`}><Icon name={CATEGORY_ICON[r.category.slug] ?? "pin"} />
            <div className="grow"><div className="row"><b>{r.category.name}</b><StatusBadge status={r.status} /><DemoBadge show={r.is_demo} /></div>
              <div className="xs muted">{formatDate(r.submitted_at, lang)}{r.reopen_count ? ` — ${tr("رجعت", "returned")} ${r.reopen_count}` : ""}</div></div></Link></li>
        ))}</ul>
      )}
      {d.initiatives.length > 0 && <><h2 style={{ marginTop: 16 }}>{tr("أعمال مرتبطة", "Related work")}</h2>
        <ul className="list panel">{d.initiatives.map((i) => <li key={i.id}><Link className="list-item" to={`/initiatives/${i.id}`}><Icon name="people" /><span className="grow">{i.title}</span></Link></li>)}</ul></>}
    </div>
  );
}

type Proposal = { id: number; cycle: number | null; title: string; description: string; estimated_cost: string | null; cost_verified: string | null;
  status: string; status_label: string; votes_count: number; voted: boolean; maintenance_plan: string; is_demo: boolean };
type Cycle = { id: number; title: string; budget_amount: string; budget_source: string; voting_closes: string; is_voting_open: boolean; is_demo: boolean };

export function Proposals() {
  const { tr, lang } = useI18n();
  const { me } = useAuth();
  const cycles = useLoad<Paged<Cycle>>("/budget-cycles/");
  const props = useLoad<Paged<Proposal>>("/proposals/?page_size=100");
  const { busy, run } = useAction();
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ title: "", description: "", estimated_cost: "" });
  if ((cycles.loading || props.loading) && !props.data) return <Loading />;
  if (props.error && !props.data) return <ErrorState error={props.error} onRetry={props.reload} />;
  const cycle = cycles.data?.results.find((c) => c.is_voting_open) ?? cycles.data?.results[0];
  const mine = props.data!.results.filter((p) => p.cycle === cycle?.id && p.voted).reduce((s, p) => s + Number(p.cost_verified ?? 0), 0);
  return (
    <div style={{ maxWidth: 820, margin: "0 auto" }}>
      <PageHeader title={tr("اقتراحات الحومة", "Neighbourhood proposals")} back="">
        {me && <button className="btn small" onClick={() => setOpen(true)}><Icon name="plus" size={18} />{tr("اقترح", "Propose")}</button>}
      </PageHeader>
      <p className="muted small" style={{ maxWidth: "62ch" }}>{tr("يُراجع كل اقتراح للجدوى والإذن والتكلفة وخطة الصيانة قبل أن يصبح مؤهلًا للتصويت ضمن ميزانية معلنة.",
        "Each proposal is checked for feasibility, permits, cost and maintenance before it can be voted on within a declared budget.")}</p>
      {cycle && (
        <div className="panel" style={{ marginBottom: 12 }}>
          <div className="row between"><b>{cycle.title}</b><DemoBadge show={cycle.is_demo} /></div>
          <div className="small">{tr("الميزانية المعلنة", "Declared budget")}: <b className="num">{money(cycle.budget_amount, lang)}</b> — {cycle.budget_source}</div>
          {cycle.is_voting_open && <div className="small">{tr("التصويت مفتوح حتى", "Voting open until")} {formatDate(cycle.voting_closes, lang)} — {tr("مجموع تكلفة اختياراتك", "your selections total")}: <b className="num">{money(mine, lang)}</b></div>}
        </div>
      )}
      {props.data!.results.length === 0 ? <EmptyState icon="vote" title={tr("لا اقتراحات بعد", "No proposals yet")} /> : (
        <ul className="list panel">{props.data!.results.map((p) => (
          <li key={p.id} className="list-item"><Icon name="vote" /><div className="grow">
            <div className="row"><b>{p.title}</b><StatusBadge status={p.status === "eligible" ? "eligible" : p.status === "rejected" ? "rejected" : "under_review"} label={p.status_label} /><DemoBadge show={p.is_demo} /></div>
            <div className="small">{p.description}</div>
            <div className="xs muted">{p.cost_verified ? `${tr("التكلفة المراجعة", "Verified cost")}: ${money(p.cost_verified, lang)}` : p.estimated_cost ? `${tr("تقدير المقترح", "Estimate")}: ${money(p.estimated_cost, lang)}` : ""}
              {p.maintenance_plan && ` — ${tr("الصيانة", "Maintenance")}: ${p.maintenance_plan}`} — {num(p.votes_count, lang)} {tr("صوت", "votes")}</div>
          </div>
            {p.status === "eligible" && cycle?.is_voting_open && p.cycle === cycle.id && me && (p.voted ? <span className="badge s-done">{tr("صوّتّ", "Voted")}</span> :
              <button className="btn small teal" disabled={busy} onClick={() => run(() => post(`/proposals/${p.id}/vote/`), tr("سُجّل صوتك", "Vote recorded")).then(props.reload)}>{tr("صوّت", "Vote")}</button>)}
          </li>
        ))}</ul>
      )}
      {open && (
        <Dialog title={tr("اقتراح جديد", "New proposal")} onClose={() => setOpen(false)}>
          <Field id="pt" label={tr("العنوان", "Title")}><input id="pt" className="input" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
          <Field id="pd" label={tr("ما الفكرة وما المشكلة التي تحلها؟", "What is it and what problem does it solve?")}><textarea id="pd" className="input" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
          <Field id="pc" label={tr("تكلفة تقديرية (اختياري)", "Estimated cost (optional)")}><input id="pc" className="input" inputMode="decimal" dir="ltr" value={f.estimated_cost} onChange={(e) => setF({ ...f, estimated_cost: e.target.value })} /></Field>
          <button className="btn block" disabled={busy || !f.title || !f.description} onClick={async () => {
            const r = await run(() => post("/proposals/", { ...f, cycle: cycle?.id ?? null, estimated_cost: f.estimated_cost || null }), tr("أُرسل اقتراحك للمراجعة", "Submitted for review"));
            if (r) { setOpen(false); props.reload(); }
          }}>{tr("أرسل للمراجعة", "Submit for review")}</button>
        </Dialog>
      )}
    </div>
  );
}
