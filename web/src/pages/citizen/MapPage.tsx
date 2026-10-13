import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import type { Area, Category, MapReport, Paged, RoadAlert } from "../../api/types";
import { Icon } from "../../components/Icon";
import { MapView, type MapMarker } from "../../components/MapView";
import { StaleNote, StatusBadge, DemoBadge } from "../../components/ui";
import { timeAgo } from "../../lib/format";
import { useLoad } from "../../lib/hooks";
import { useI18n } from "../../lib/i18n";

const ALERT_COLORS: Record<string, string> = { accident: "#A8261B", closure: "#0C2E33", obstacle: "#F4B544", congestion: "#D9822B" };

type Sel = { kind: "report"; r: MapReport } | { kind: "alert"; a: RoadAlert } | null;

export default function MapPage() {
  const { tr, lang } = useI18n();
  const [sp] = useSearchParams();
  const [layers, setLayers] = useState({ services: true, road: true, pedestrian: true });
  const [cat, setCat] = useState<string>("");
  const [status, setStatus] = useState<string>(sp.get("status") ?? "open");
  const [since, setSince] = useState<string>("30");
  const [alertTypes, setAlertTypes] = useState<string[]>(["accident", "closure", "obstacle", "congestion"]);
  const [showFilters, setShowFilters] = useState(false);
  const [sel, setSel] = useState<Sel>(null);

  const cats = useLoad<Paged<Category>>("/categories/?page_size=100");
  const areas = useLoad<Paged<Area>>("/areas/?geometry=1&page_size=200");
  const q = new URLSearchParams({ view: "map" });
  if (cat) q.set("category", cat);
  if (status === "open") q.set("status", "open");
  else if (status !== "all") q.set("status", status);
  if (since !== "all") q.set("since", since);
  if (sp.get("area")) q.set("area", sp.get("area")!);
  const reports = useLoad<MapReport[]>(`/reports/?${q}`, [q.toString()]);
  const alerts = useLoad<RoadAlert[]>("/road-alerts/");

  const catById = useMemo(() => Object.fromEntries((cats.data?.results ?? []).map((c) => [c.id, c])), [cats.data]);
  const markers: MapMarker[] = useMemo(() => {
    const out: MapMarker[] = [];
    for (const r of reports.data ?? []) {
      const c = catById[r.category_id];
      const layer = c?.layer ?? "services";
      if (layer === "pedestrian" ? !layers.pedestrian : !layers.services) continue;
      out.push({ id: `r${r.id}`, lat: r.lat, lng: r.lng, label: `${c?.name_ar ?? ""} — ${r.tracking_number}`,
                 color: r.status === "resolved" ? "#123F46" : layer === "pedestrian" ? "#2D5A61" : "#0B6E64",
                 onClick: () => setSel({ kind: "report", r }) });
    }
    if (layers.road) {
      for (const a of alerts.data ?? []) {
        if (!alertTypes.includes(a.type)) continue;
        out.push({ id: `a${a.id}`, lat: a.lat, lng: a.lng, label: a.type_label, color: ALERT_COLORS[a.type] ?? "#123F46",
                   icon: "square", onClick: () => setSel({ kind: "alert", a }) });
      }
    }
    return out;
  }, [reports.data, alerts.data, layers, catById, alertTypes]);

  const toggle = (k: keyof typeof layers) => setLayers((l) => ({ ...l, [k]: !l[k] }));
  const loading = reports.loading || alerts.loading;

  return (
    <div className="map-wrap">
      <h1 className="sr-only">{tr("الخريطة", "Map")}</h1>
      <MapView markers={markers} label={tr("خريطة البلاغات وتنبيهات الطريق", "Map of reports and road alerts")}
        areas={(areas.data?.results ?? []).map((a) => ({ id: a.id, name: a.name_ar, geometry: a.geometry }))} />
      <div className="map-panel">
        <div className="chips" role="group" aria-label={tr("طبقات الخريطة", "Map layers")}>
          <button className="chip" aria-pressed={layers.services} onClick={() => toggle("services")}>
            <Icon name="trash" size={18} />{tr("مشاكل الخدمات", "Service problems")}</button>
          <button className="chip" aria-pressed={layers.road} onClick={() => toggle("road")}>
            <Icon name="car" size={18} />{tr("الطريق توّا", "Road now")}</button>
          <button className="chip" aria-pressed={layers.pedestrian} onClick={() => toggle("pedestrian")}>
            <Icon name="wheelchair" size={18} />{tr("طريق للكل", "Walkability")}</button>
          <button className="chip" aria-expanded={showFilters} onClick={() => setShowFilters((v) => !v)}>
            <Icon name="layers" size={18} />{tr("فلاتر", "Filters")}</button>
          <Link className="chip" to="/road/new" style={{ textDecoration: "none" }}><Icon name="plus" size={18} />{tr("تنبيه طريق", "Road alert")}</Link>
        </div>
      </div>
      {showFilters && (
        <div className="map-sheet panel" role="region" aria-label={tr("فلاتر الخريطة", "Map filters")} style={{ maxWidth: 560, marginInline: "auto" }}>
          <div className="grid two">
            <div className="field"><label htmlFor="f-cat">{tr("الفئة", "Category")}</label>
              <select id="f-cat" className="input" value={cat} onChange={(e) => setCat(e.target.value)}>
                <option value="">{tr("كل الفئات", "All")}</option>
                {cats.data?.results.map((c) => <option key={c.id} value={c.id}>{lang === "en" && c.name_en ? c.name_en : c.name_ar}</option>)}
              </select></div>
            <div className="field"><label htmlFor="f-st">{tr("الحالة", "Status")}</label>
              <select id="f-st" className="input" value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="open">{tr("مفتوحة", "Open")}</option>
                <option value="resolved">{tr("محلولة", "Resolved")}</option>
                <option value="referred,acknowledged,in_progress">{tr("عند الجهة", "With the agency")}</option>
                <option value="all">{tr("الكل", "All")}</option>
              </select></div>
            <div className="field"><label htmlFor="f-t">{tr("الفترة", "Time")}</label>
              <select id="f-t" className="input" value={since} onChange={(e) => setSince(e.target.value)}>
                <option value="1">{tr("آخر 24 ساعة", "Last 24h")}</option><option value="7">{tr("آخر أسبوع", "Last week")}</option>
                <option value="30">{tr("آخر شهر", "Last month")}</option><option value="all">{tr("كل الوقت", "All time")}</option>
              </select></div>
            <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
              <legend className="label">{tr("تنبيهات الطريق (المصدر: مبلّغون وجهات)", "Road alerts")}</legend>
              <div className="chips">
                {Object.keys(ALERT_COLORS).map((t) => (
                  <button key={t} className="chip" aria-pressed={alertTypes.includes(t)}
                    onClick={() => setAlertTypes((x) => x.includes(t) ? x.filter((y) => y !== t) : [...x, t])}>
                    <span aria-hidden style={{ width: 10, height: 10, borderRadius: 3, background: ALERT_COLORS[t] }} />
                    {{ accident: tr("حوادث", "Accidents"), closure: tr("إغلاقات", "Closures"), obstacle: tr("عوائق", "Obstacles"),
                       congestion: tr("ازدحام مبلّغ عنه", "Reported congestion") }[t]}
                  </button>
                ))}
              </div>
            </fieldset>
          </div>
          <div className="row between">
            <span className="xs muted" aria-live="polite">{loading ? tr("جارٍ التحميل…", "Loading…") : `${markers.length} ${tr("علامة على الخريطة", "markers")}`}</span>
            <button className="btn small" onClick={() => setShowFilters(false)}>{tr("تم", "Done")}</button>
          </div>
        </div>
      )}
      {!showFilters && sel && (
        <div className="map-sheet panel" role="dialog" aria-label={tr("تفاصيل", "Details")} style={{ maxWidth: 560, marginInline: "auto" }}>
          <div className="row between">
            {sel.kind === "report" ? (
              <div>
                <div className="row"><b>{catById[sel.r.category_id]?.name_ar}</b><StatusBadge status={sel.r.status} /><DemoBadge show={sel.r.is_demo} /></div>
                <div className="xs muted"><bdi>{sel.r.tracking_number}</bdi> — {timeAgo(sel.r.submitted_at, lang)}</div>
              </div>
            ) : (
              <div>
                <div className="row"><b>{sel.a.type_label}</b><span className="badge s-wait">{sel.a.verification_label}</span><DemoBadge show={sel.a.is_demo} /></div>
                <div className="xs muted">{tr("رُصد", "Seen")} {timeAgo(sel.a.observed_at, lang)} — {tr("آخر تأكيد", "last confirmed")} {timeAgo(sel.a.last_confirmed_at, lang)} — {tr("المصدر", "source")}: {sel.a.source_label}</div>
              </div>
            )}
            <button className="icon-btn" onClick={() => setSel(null)} aria-label={tr("إغلاق", "Close")}><Icon name="x" /></button>
          </div>
          {sel.kind === "report" ? (
            <div className="row" style={{ marginTop: 8 }}>
              <Link className="btn small" to={`/reports/${sel.r.id}`}>{tr("تفاصيل البلاغ", "Report details")}</Link>
              <Link className="btn small ghost" to={`/place?lat=${sel.r.lat}&lng=${sel.r.lng}`}>{tr("ملف المكان", "Place history")}</Link>
            </div>
          ) : (
            <div className="row" style={{ marginTop: 8 }}>
              <Link className="btn small" to={`/road/${sel.a.id}`}>{tr("ما زال موجود؟", "Still there?")}</Link>
            </div>
          )}
        </div>
      )}
      <div style={{ position: "absolute", zIndex: 650, bottom: 12, insetInlineStart: 12, maxWidth: 320 }}>
        <StaleNote stale={reports.stale} savedAt={reports.savedAt} />
        {(reports.error || alerts.error) && !reports.data ? <div className="banner error" role="alert">{tr("تعذر تحميل بيانات الخريطة.", "Couldn't load map data.")}</div> : null}
      </div>
    </div>
  );
}
