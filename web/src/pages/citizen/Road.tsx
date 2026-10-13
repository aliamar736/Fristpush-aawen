import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { post } from "../../api/client";
import type { RoadAlert } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Icon } from "../../components/Icon";
import { MapView, TRIPOLI } from "../../components/MapView";
import { PageHeader } from "../../components/Shell";
import { DemoBadge, ErrorState, Field, Loading, useAction } from "../../components/ui";
import { formatDate, timeAgo, toLocalInput, uuid } from "../../lib/format";
import { useLoad } from "../../lib/hooks";
import { useI18n } from "../../lib/i18n";

const TYPES: [string, string, string, string][] = [
  ["accident", "حادث", "Accident", "car"], ["closure", "إغلاق", "Closure", "cone"],
  ["obstacle", "عائق على الطريق", "Obstacle", "alert"], ["congestion", "ازدحام", "Congestion", "road"],
];

export function RoadNew() {
  const { tr, lang } = useI18n();
  const { me, config } = useAuth();
  const nav = useNavigate();
  const { busy, run } = useAction();
  const [type, setType] = useState("accident");
  const [pos, setPos] = useState<{ lat?: number; lng?: number }>({});
  const [desc, setDesc] = useState("");
  const [obs, setObs] = useState(toLocalInput(new Date()));
  const [cid] = useState(uuid);
  if (!me) return <div className="state"><h2>{tr("سجّل الدخول لإرسال تنبيه طريق", "Sign in to post a road alert")}</h2><Link className="btn" to="/login?next=/road/new">{tr("تسجيل الدخول", "Sign in")}</Link></div>;
  const send = async () => {
    const r = await run(() => post<RoadAlert>("/road-alerts/", { type, ...pos, description: desc, observed_at: new Date(obs).toISOString(), client_id: cid }, { idempotencyKey: cid }));
    if (r) nav(`/road/${r.id}`, { replace: true, state: { notice: r.notice } });
  };
  return (
    <div style={{ maxWidth: 640, margin: "0 auto" }}>
      <PageHeader title={tr("تنبيه طريق", "Road alert")} back="/map" />
      <div className="banner error" role="note" style={{ marginBottom: 12 }}>
        <Icon name="phone" size={20} /><span><b>{tr("هذا ليس طلب نجدة.", "This is not an emergency call.")}</b> {lang === "en" ? config?.emergency_notice.en : config?.emergency_notice.ar}</span>
      </div>
      <div className="panel">
        <div role="radiogroup" aria-label={tr("نوع التنبيه", "Alert type")} className="choice-grid" style={{ marginBottom: 12 }}>
          {TYPES.map(([k, a, e, ic]) => (
            <button key={k} role="radio" aria-checked={type === k} className="choice" onClick={() => setType(k)}><Icon name={ic} className="ico" /><b>{k === "congestion" ? tr("ازدحام مبلّغ عنه", "Reported congestion") : tr(a, e)}</b></button>
          ))}
        </div>
        <div className="mini-map"><MapView label={tr("موقع التنبيه", "Alert location")} cluster={false} center={pos.lat ? [pos.lat, pos.lng!] : TRIPOLI}
          picker={{ ...pos, onChange: (lat, lng) => setPos({ lat, lng }) }} /></div>
        <button className="btn ghost small" style={{ margin: "8px 0" }} onClick={() => navigator.geolocation?.getCurrentPosition((p) => setPos({ lat: p.coords.latitude, lng: p.coords.longitude }))}>
          <Icon name="locate" size={18} />{tr("موقعي الحالي", "My location")}</button>
        <Field id="ob" label={tr("متى رأيته؟", "When did you see it?")} hint={tr("إذا كان الرصد قديمًا لن يُنشر كحدث مباشر.", "Old sightings are not shown as live.")}>
          <input id="ob" type="datetime-local" className="input" value={obs} max={toLocalInput(new Date())} onChange={(e) => setObs(e.target.value)} />
        </Field>
        <Field id="d" label={tr("تفاصيل قصيرة (اختياري)", "Short details (optional)")} hint={tr("لا تذكر أسماء أو لوحات سيارات. لا تصوّر المصابين.", "No names, plates or photos of injured people.")}>
          <input id="d" className="input" value={desc} onChange={(e) => setDesc(e.target.value)} maxLength={500} />
        </Field>
        <button className="btn teal block" disabled={busy || pos.lat == null} onClick={send}>{tr("انشر التنبيه", "Post alert")}</button>
      </div>
    </div>
  );
}

export function RoadDetail() {
  const { id } = useParams();
  const { tr, lang } = useI18n();
  const { me } = useAuth();
  const { data: a, error, loading, reload } = useLoad<RoadAlert>(`/road-alerts/${id}/`, [id]);
  const { busy, run } = useAction();
  if (loading && !a) return <Loading />;
  if (error && !a) return <ErrorState error={error} onRetry={reload} />;
  if (!a) return null;
  const vote = (v: string) => run(() => post(`/road-alerts/${a.id}/vote/`, { vote: v }), tr("شكرًا، سُجّل رأيك.", "Thanks.")).then(reload);
  return (
    <div style={{ maxWidth: 640, margin: "0 auto" }}>
      <PageHeader title={a.type_label} back="/map"><DemoBadge show={a.is_demo} /></PageHeader>
      {a.status === "historical" && <div className="banner warn" style={{ marginBottom: 12 }}>{tr("وصل هذا البلاغ متأخرًا عن وقت الرصد، فسُجّل في السجل ولم يُنشر كحدث مباشر.", "Arrived late — recorded but not shown as live.")}</div>}
      <div className="panel">
        <div className="row"><span className={`badge ${a.is_live ? "s-work" : "s-new"}`}>{a.is_live ? tr("قائم الآن", "Live") : a.status_label}</span>
          <span className="badge s-wait">{a.verification_label}</span><span className="badge plain">{tr("المصدر", "Source")}: {a.source_label}</span></div>
        {a.description && <p style={{ marginTop: 8 }}>{a.description}</p>}
        <dl className="kv small" style={{ marginTop: 8 }}>
          <dt>{tr("وقت الرصد", "Seen at")}</dt><dd>{formatDate(a.observed_at, lang, true)}</dd>
          <dt>{tr("آخر تأكيد", "Last confirmed")}</dt><dd>{timeAgo(a.last_confirmed_at, lang)}</dd>
          <dt>{tr("صالح حتى", "Valid until")}</dt><dd>{formatDate(a.expires_at, lang, true)}</dd>
          <dt>{tr("ما زال موجود", "Still there")}</dt><dd>{a.still_there_count}</dd>
          <dt>{tr("الطريق فتح", "Road open")}</dt><dd>{a.cleared_count}</dd>
        </dl>
        <p className="xs muted">{tr("لا نعرض سرعات أو مدد رحلات أو طرقًا بديلة محسوبة — فقط ما يبلّغ عنه الناس والجهات.", "We don't show speeds, travel times or computed detours — only what people and agencies report.")}</p>
        {a.is_live && (me ? (
          <div className="row">
            <button className="btn" disabled={busy} onClick={() => vote("still_there")}>{tr("ما زال موجود", "Still there")}</button>
            <button className="btn ghost" disabled={busy} onClick={() => vote("cleared")}>{tr("الطريق فتح", "Road is open")}</button>
          </div>) : <Link to={`/login?next=/road/${a.id}`}>{tr("سجّل الدخول لتحديث الحالة", "Sign in to update")}</Link>)}
      </div>
      <div className="mini-map" style={{ marginTop: 12 }}><MapView label={tr("موقع التنبيه", "Alert location")} cluster={false} center={[a.lat, a.lng]} zoom={16}
        markers={[{ id: a.id, lat: a.lat, lng: a.lng, color: "#A8261B", label: a.type_label, icon: "square" }]} /></div>
    </div>
  );
}
