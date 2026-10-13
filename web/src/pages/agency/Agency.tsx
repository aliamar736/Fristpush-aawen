import { useState } from "react";
import { Link } from "react-router-dom";

import { post } from "../../api/client";
import type { Area, Paged, Report } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { CATEGORY_ICON, Icon } from "../../components/Icon";
import { PageHeader } from "../../components/Shell";
import { DemoBadge, Dialog, EmptyState, ErrorState, Field, Loading, StatusBadge, useAction } from "../../components/ui";
import { formatDate, timeAgo } from "../../lib/format";
import { useLoad } from "../../lib/hooks";
import { useI18n } from "../../lib/i18n";
import { ReportTable } from "../admin/Operations";

const FILTERS: [string, string, string][] = [["referred", "محالة — بانتظار تأكيد الاستلام", "Awaiting acknowledgement"],
  ["acknowledged,in_progress,waiting_resource", "قيد العمل", "In progress"], ["done_pending_verification", "بانتظار التحقق", "Awaiting verification"],
  ["resolved,unresolvable", "مغلقة", "Closed"]];

export function AgencyInbox() {
  const { tr } = useI18n();
  const { me } = useAuth();
  const [st, setSt] = useState(FILTERS[0][0]);
  const { data, error, loading, reload } = useLoad<Paged<Report>>(`/reports/agency/?status=${st}&page_size=100`, [st]);
  const agencies = me?.roles.filter((r) => r.role === "agency_staff").map((r) => r.agency_name).join("، ");
  return (
    <div>
      <PageHeader title={tr("البلاغات المحالة لجهتكم", "Reports referred to your agency")} />
      <p className="small muted">{agencies} — {tr("تأكيد الاستلام خطوة منفصلة عن الإحالة ويظهر للمواطن. أرفق صور الإنجاز ليتحقق منه طرف مستقل.", "Acknowledgement is separate from referral and visible to citizens.")}</p>
      <div className="tabs" role="tablist">{FILTERS.map(([k, a, e]) => <button key={k} role="tab" aria-selected={st === k} onClick={() => setSt(k)}>{tr(a, e)}</button>)}</div>
      {loading && !data ? <Loading /> : error && !data ? <ErrorState error={error} onRetry={reload} /> : <ReportTable rows={data!.results} base="/agency/reports" />}
    </div>
  );
}

export function AgencyAnnouncements() {
  const { tr, lang } = useI18n();
  const { me } = useAuth();
  const mine = useLoad<Paged<{ id: number; title: string; body: string; starts_at: string; ends_at: string | null; agency_name: string; published: boolean }>>("/announcements/?mine=1");
  const areas = useLoad<Paged<Area>>("/areas/?page_size=300");
  const myAgencies = (me?.roles ?? []).filter((r) => r.role === "agency_staff" && r.agency);
  const [f, setF] = useState<{ agency: string; title: string; body: string; areas: number[]; ends_at: string } | null>(null);
  const { busy, run } = useAction();
  return (
    <div>
      <PageHeader title={tr("تنبيهات الجهة للسكان", "Agency notices")}><button className="btn small" onClick={() => setF({ agency: String(myAgencies[0]?.agency ?? ""), title: "", body: "", areas: [], ends_at: "" })}>{tr("تنبيه جديد", "New notice")}</button></PageHeader>
      <p className="small muted">{tr("أعمال مجدولة، انقطاعات، إغلاقات — تظهر في «حومتي» للمناطق المختارة.", "Scheduled works, outages, closures — shown in the selected areas.")}</p>
      {mine.loading && !mine.data ? <Loading /> : (mine.data?.results.length ?? 0) === 0 ? <EmptyState icon="bell" title={tr("لم تنشروا تنبيهات بعد", "No notices yet")} /> : (
        <ul className="list panel">{mine.data!.results.map((a) => <li key={a.id} className="list-item"><Icon name="bell" /><div className="grow"><b>{a.title}</b><div className="small">{a.body}</div>
          <div className="xs muted">{formatDate(a.starts_at, lang)} {a.ends_at && `← ${formatDate(a.ends_at, lang)}`}</div></div></li>)}</ul>
      )}
      {f && (
        <Dialog title={tr("تنبيه جديد", "New notice")} onClose={() => setF(null)}>
          {myAgencies.length > 1 && <Field id="aa" label={tr("الجهة", "Agency")}><select id="aa" className="input" value={f.agency} onChange={(e) => setF({ ...f, agency: e.target.value })}>{myAgencies.map((r) => <option key={r.id} value={r.agency!}>{r.agency_name}</option>)}</select></Field>}
          <Field id="at" label={tr("العنوان", "Title")}><input id="at" className="input" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
          <Field id="ab" label={tr("التفاصيل", "Details")}><textarea id="ab" className="input" value={f.body} onChange={(e) => setF({ ...f, body: e.target.value })} /></Field>
          <Field id="ae" label={tr("ينتهي في", "Ends at")}><input id="ae" type="datetime-local" className="input" value={f.ends_at} onChange={(e) => setF({ ...f, ends_at: e.target.value })} /></Field>
          <fieldset style={{ border: 0, padding: 0 }}><legend className="label"><b>{tr("المناطق", "Areas")}</b></legend>
            <div className="chips">{areas.data?.results.map((a) => <button key={a.id} className="chip" aria-pressed={f.areas.includes(a.id)} onClick={() => setF({ ...f, areas: f.areas.includes(a.id) ? f.areas.filter((x) => x !== a.id) : [...f.areas, a.id] })}>{a.name_ar}</button>)}</div></fieldset>
          <button className="btn block" style={{ marginTop: 12 }} disabled={busy || !f.title || !f.agency} onClick={() => run(() => post("/announcements/", { agency: Number(f.agency), title: f.title, body: f.body, areas: f.areas, ends_at: f.ends_at ? new Date(f.ends_at).toISOString() : null }), tr("نُشر التنبيه", "Published")).then((r) => { if (r) { setF(null); mine.reload(); } })}>{tr("انشر", "Publish")}</button>
        </Dialog>
      )}
    </div>
  );
}

export function FieldTasks() {
  const { tr, lang } = useI18n();
  const { data, error, loading, reload, stale } = useLoad<Report[]>("/reports/field/");
  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorState error={error} onRetry={reload} />;
  return (
    <div style={{ maxWidth: 720 }}>
      <PageHeader title={tr("مهامي الميدانية", "My field tasks")} />
      {stale && <div className="banner warn">{tr("نسخة محفوظة — قد لا تكون محدّثة.", "Saved copy — may be outdated.")}</div>}
      {data!.length === 0 ? <EmptyState icon="check" title={tr("لا مهام ميدانية مسندة لك", "No field tasks assigned")} /> : (
        <ul className="list panel">{data!.map((r) => (
          <li key={r.id}><Link className="list-item" to={`/field/reports/${r.id}`}>
            <Icon name={CATEGORY_ICON[r.category.slug] ?? "pin"} />
            <div className="grow"><div className="row"><b>{r.category.name}</b><StatusBadge status={r.status} /><DemoBadge show={r.is_demo} /></div>
              <div className="small">{r.landmark_text || r.area_name}</div>
              <div className="xs muted"><bdi>{r.tracking_number}</bdi> — {timeAgo(r.status_changed_at, lang)}</div></div>
            <a className="btn small ghost" href={`https://www.openstreetmap.org/?mlat=${r.lat}&mlon=${r.lng}#map=18/${r.lat}/${r.lng}`} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>{tr("الموقع", "Map")}</a>
          </Link></li>))}</ul>
      )}
    </div>
  );
}
