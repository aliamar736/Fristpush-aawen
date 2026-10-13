import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { get } from "../../api/client";
import type { Area, Paged } from "../../api/types";
import { Icon } from "../../components/Icon";
import { EmptyState, ErrorState, Loading, StaleNote } from "../../components/ui";
import { formatDate, num, timeAgo } from "../../lib/format";
import { useLoad } from "../../lib/hooks";
import { useI18n } from "../../lib/i18n";

type Summary = {
  area: Area;
  reports: { open: number; resolved: number; by_status: Record<string, number> };
  initiatives: { id: number; title: string; summary: string; status: string }[];
  announcements: { id: number; title: string; body: string; agency__name: string; starts_at: string; ends_at: string | null }[];
  services: { id: number; name: string; service: string; phone: string; address: string; hours: string; verified_at: string }[];
  proposals: { id: number; title: string; status: string; votes_count: number }[];
  recently_resolved: { id: number; tracking_number: string; category: string; resolved_at: string }[];
};

const AREA_KEY = "aawen.area";

export function useFollowedArea(): [number | null, (id: number | null) => void] {
  const [id, setId] = useState<number | null>(() => {
    try {
      const v = localStorage.getItem(AREA_KEY);
      return v ? Number(v) : null;
    } catch {
      return null;
    }
  });
  const set = (v: number | null) => {
    setId(v);
    try {
      if (v) localStorage.setItem(AREA_KEY, String(v));
      else localStorage.removeItem(AREA_KEY);
    } catch {
      /* ignore */
    }
  };
  return [id, set];
}

export default function Home() {
  const { tr, lang } = useI18n();
  const [areaId, setAreaId] = useFollowedArea();
  const areas = useLoad<Paged<Area>>("/areas/?page_size=200");
  const sum = useLoad<Summary>(areaId ? `/areas/${areaId}/summary/` : null, [areaId]);
  const [locating, setLocating] = useState(false);
  const [locErr, setLocErr] = useState("");

  useEffect(() => {
    if (areaId && areas.data && !areas.data.results.some((a) => a.id === areaId)) setAreaId(null);
  }, [areas.data, areaId, setAreaId]);

  const locate = () => {
    setLocErr("");
    if (!navigator.geolocation) return setLocErr(tr("جهازك لا يدعم تحديد الموقع.", "Location not supported."));
    setLocating(true);
    // One-off position only — the app never tracks location continuously.
    navigator.geolocation.getCurrentPosition(
      async (p) => {
        try {
          const a = await get<Area | null>(`/areas/locate/?lat=${p.coords.latitude}&lng=${p.coords.longitude}`);
          if (a) setAreaId(a.id);
          else setLocErr(tr("موقعك خارج المناطق المغطاة حاليًا. اختر منطقة من القائمة.", "You're outside covered areas."));
        } catch (e) {
          setLocErr((e as Error).message);
        } finally {
          setLocating(false);
        }
      },
      () => {
        setLocating(false);
        setLocErr(tr("لم نحصل على إذن الموقع. يمكنك اختيار حومتك من القائمة.", "Location permission denied — pick your area from the list."));
      },
      { timeout: 10000, maximumAge: 300000 },
    );
  };

  const s = sum.data;
  return (
    <div>
      <section className="hero routes-bg" aria-labelledby="home-title">
        <div className="row between" style={{ alignItems: "flex-start" }}>
          <div>
            <p className="small" style={{ margin: 0 }}>{tr("حومتي", "My area")}</p>
            <h1 id="home-title" style={{ fontSize: "var(--fs-2xl)", marginBottom: 4 }}>
              {s?.area.name_ar ?? tr("اختر حومتك", "Choose your area")}
            </h1>
            <p style={{ maxWidth: "52ch" }}>{tr("بلّغ، تابع، وشارك في حل مشاكل الشارع مع الجيران والجهات المختصة.",
              "Report, follow up and help fix street problems with neighbours and the responsible authorities.")}</p>
          </div>
        </div>
        <div className="row" style={{ marginTop: 8 }}>
          <label htmlFor="area" className="sr-only">{tr("المنطقة المتابعة", "Followed area")}</label>
          <select id="area" className="input" style={{ maxWidth: 260, color: "var(--petrol)" }} value={areaId ?? ""}
            onChange={(e) => setAreaId(e.target.value ? Number(e.target.value) : null)}>
            <option value="">{tr("— اختر منطقة —", "— Choose an area —")}</option>
            {areas.data?.results.map((a) => <option key={a.id} value={a.id}>{a.name_ar}{a.is_demo ? " (تجريبي)" : ""}</option>)}
          </select>
          <button className="btn teal" onClick={locate} disabled={locating}>
            <Icon name="locate" size={20} />{locating ? tr("جارٍ التحديد…", "Locating…") : tr("حدد حومتي", "Use my location")}
          </button>
        </div>
        {locErr && <p role="alert" style={{ marginTop: 8, color: "var(--yellow)" }}>{locErr}</p>}
      </section>

      <StaleNote stale={sum.stale} savedAt={sum.savedAt} />
      {!areaId && !areas.loading && (
        <EmptyState icon="pin" title={tr("اختر الحومة اللي تهمك", "Pick the area you care about")}>
          {tr("سنعرض لك بلاغاتها ومبادراتها وتنبيهات الجهات فيها. يمكنك تغييرها في أي وقت.",
            "We'll show its reports, initiatives and agency notices.")}
        </EmptyState>
      )}
      {areas.error ? <ErrorState error={areas.error} onRetry={areas.reload} /> : null}
      {areaId && sum.loading && !s && <Loading lines={6} />}
      {areaId && sum.error && !s ? <ErrorState error={sum.error} onRetry={sum.reload} /> : null}

      {s && (
        <>
          <div className="stats" style={{ marginTop: 16 }}>
            <Link to={`/map?area=${s.area.id}&status=open`} className="panel stat" style={{ textDecoration: "none", color: "inherit" }}>
              <b>{num(s.reports.open, lang)}</b><span className="muted small">{tr("بلاغ مفتوح", "open reports")}</span>
            </Link>
            <div className="panel stat"><b>{num(s.reports.resolved, lang)}</b><span className="muted small">{tr("مشكلة اتحلّت", "resolved")}</span></div>
            <div className="panel stat"><b>{num(s.initiatives.length, lang)}</b><span className="muted small">{tr("مبادرة جارية", "active initiatives")}</span></div>
          </div>
          {s.area.boundary_source.startsWith("approximate") && (
            <p className="xs muted" style={{ marginTop: 6 }}>{tr("حدود هذه المنطقة تقريبية لأغراض العرض.", "Area boundaries are approximate.")}</p>
          )}

          <div className="section"><h2>{tr("تنبيهات الجهات", "Agency notices")}</h2></div>
          {s.announcements.length === 0 ? <p className="muted">{tr("لا توجد تنبيهات حالية من الجهات لهذه الحومة.", "No current notices.")}</p> : (
            <ul className="list panel">
              {s.announcements.map((a) => (
                <li key={a.id} className="list-item">
                  <Icon name="bell" />
                  <div className="grow">
                    <div className="title">{a.title}</div>
                    <div className="small">{a.body}</div>
                    <div className="xs muted">{a.agency__name} — {a.ends_at ? `${tr("حتى", "until")} ${formatDate(a.ends_at, lang, true)}` : timeAgo(a.starts_at, lang)}</div>
                  </div>
                </li>
              ))}
            </ul>
          )}

          <div className="section"><h2>{tr("مبادرات الحومة", "Initiatives")}</h2><Link className="more" to="/aawen">{tr("كل المبادرات", "All")}</Link></div>
          {s.initiatives.length === 0 ? (
            <p className="muted">{tr("ما فيش مبادرة جارية هنا. اقترح وحدة من «عاون».", "No initiatives yet — start one from Help.")}</p>
          ) : (
            <div className="grid two">
              {s.initiatives.map((i) => (
                <Link key={i.id} to={`/initiatives/${i.id}`} className="panel" style={{ textDecoration: "none", color: "inherit" }}>
                  <div className="title" style={{ fontWeight: 700 }}>{i.title}</div>
                  <div className="small muted">{i.summary}</div>
                </Link>
              ))}
            </div>
          )}

          <div className="section"><h2>{tr("اتحلّت مؤخرًا", "Recently fixed")}</h2></div>
          {s.recently_resolved.length === 0 ? <p className="muted">{tr("لا توجد أعمال منجزة مسجلة بعد.", "Nothing yet.")}</p> : (
            <ul className="list panel">
              {s.recently_resolved.map((r) => (
                <li key={r.id}><Link className="list-item" to={`/reports/${r.id}`}>
                  <Icon name="check" /><div className="grow"><div className="title">{r.category}</div>
                    <div className="xs muted"><bdi>{r.tracking_number}</bdi> — {timeAgo(r.resolved_at, lang)}</div></div>
                </Link></li>
              ))}
            </ul>
          )}

          <div className="section"><h2>{tr("اقتراحات السكان", "Residents' proposals")}</h2><Link className="more" to="/proposals">{tr("اقترح أو صوّت", "Propose or vote")}</Link></div>
          {s.proposals.length === 0 ? <p className="muted">{tr("لا توجد اقتراحات بعد.", "No proposals yet.")}</p> : (
            <ul className="list panel">
              {s.proposals.map((p) => (
                <li key={p.id} className="list-item"><Icon name="vote" /><div className="grow"><div className="title">{p.title}</div>
                  <div className="xs muted">{num(p.votes_count, lang)} {tr("صوت", "votes")}</div></div></li>
              ))}
            </ul>
          )}

          <div className="section"><h2>{tr("دليل الخدمات الموثّق", "Verified service directory")}</h2></div>
          {s.services.length === 0 ? <p className="muted">{tr("لم يُوثّق أي رقم خدمة لهذه المنطقة بعد.", "No verified entries yet.")}</p> : (
            <ul className="list panel">
              {s.services.map((d) => (
                <li key={d.id} className="list-item"><Icon name="phone" /><div className="grow">
                  <div className="title">{d.name} <span className="muted small">— {d.service}</span></div>
                  {d.phone && <a href={`tel:${d.phone}`} dir="ltr">{d.phone}</a>}
                  <div className="xs muted">{d.hours} — {tr("آخر تحقق", "verified")} {timeAgo(d.verified_at, lang)}</div>
                </div></li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
