import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { get, post, put } from "../../api/client";
import type { Area, Initiative, Paged, Resource, Task } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Icon } from "../../components/Icon";
import { DemoBadge, Dialog, EmptyState, ErrorState, Field, Loading, StaleNote, StatusBadge, useAction } from "../../components/ui";
import { formatDate, num, timeAgo } from "../../lib/format";
import { useLoad } from "../../lib/hooks";
import { useI18n } from "../../lib/i18n";

const TABS: [string, string, string][] = [
  ["initiatives", "المبادرات", "Initiatives"], ["tasks", "خُذ مهمة", "Take a task"], ["skills", "مهاراتي", "My skills"],
  ["store", "مخزن الخير", "Goodwill store"], ["care", "نقاط العناية", "Care points"], ["surplus", "فائض ينفع", "Useful surplus"],
];

export default function Aawen() {
  const { tr } = useI18n();
  const [sp, setSp] = useSearchParams();
  const tab = sp.get("tab") ?? "initiatives";
  return (
    <div>
      <h1>{tr("عاون", "Help out")}</h1>
      <p className="muted" style={{ maxWidth: "60ch" }}>{tr("خذ مهمة بوقتك، أعر أداة، أو انضم لمبادرة في حومتك.", "Take a task, lend a tool, or join an initiative.")}</p>
      <div className="tabs" role="tablist" aria-label={tr("أقسام عاون", "Help sections")}>
        {TABS.map(([k, a, e]) => <button key={k} role="tab" aria-selected={tab === k} onClick={() => setSp({ tab: k })}>{tr(a, e)}</button>)}
      </div>
      <div role="tabpanel">
        {tab === "initiatives" && <Initiatives />}
        {tab === "tasks" && <Tasks />}
        {tab === "skills" && <Skills />}
        {tab === "store" && <Store />}
        {tab === "care" && <CarePoints />}
        {tab === "surplus" && <Surplus />}
      </div>
    </div>
  );
}

function Initiatives() {
  const { tr } = useI18n();
  const { me } = useAuth();
  const { data, error, loading, reload, stale, savedAt } = useLoad<Paged<Initiative>>("/initiatives/?page_size=50");
  const blocking = useLoad<{ id: number; initiative: number; initiative_title: string; title: string; kind_label: string }[]>("/needs/blocking/");
  const [creating, setCreating] = useState(false);
  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorState error={error} onRetry={reload} />;
  return (
    <div className="stack">
      <StaleNote stale={stale} savedAt={savedAt} />
      {(blocking.data?.length ?? 0) > 0 && (
        <section className="panel" aria-labelledby="blk">
          <h2 id="blk">{tr("شن ناقص؟", "What's missing?")}</h2>
          <p className="small muted">{tr("هذه الأشياء توقف مبادرات معتمدة. إذا عندك واحدة منها، اعرض مساعدتك.", "These items are blocking approved initiatives.")}</p>
          <ul className="list">
            {blocking.data!.map((n) => (
              <li key={n.id}><Link className="list-item" to={`/initiatives/${n.initiative}#need-${n.id}`}>
                <Icon name="alert" /><div className="grow"><div className="title">{n.title}</div><div className="xs muted">{n.kind_label} — {n.initiative_title}</div></div>
                <Icon name="fwd" className="flip" />
              </Link></li>
            ))}
          </ul>
        </section>
      )}
      <div className="row between">
        <h2 style={{ margin: 0 }}>{tr("المبادرات", "Initiatives")}</h2>
        {me && <button className="btn small ghost" onClick={() => setCreating(true)}><Icon name="plus" size={18} />{tr("اقترح مبادرة", "Start an initiative")}</button>}
      </div>
      {data!.results.length === 0 ? <EmptyState icon="people" title={tr("لا توجد مبادرات بعد", "No initiatives yet")} /> : (
        <div className="grid two">
          {data!.results.map((i) => (
            <Link key={i.id} to={`/initiatives/${i.id}`} className="panel" style={{ textDecoration: "none", color: "inherit" }}>
              <div className="row"><b>{i.title}</b><StatusBadge status={i.status} label={i.status_label} /><DemoBadge show={i.is_demo} /></div>
              <p className="small muted" style={{ margin: "4px 0" }}>{i.summary}</p>
              <div className="xs muted">{i.area_name} — {i.needs.filter((n) => n.status !== "met").length} {tr("احتياج مفتوح", "open needs")}</div>
            </Link>
          ))}
        </div>
      )}
      {creating && <NewInitiative onClose={() => { setCreating(false); reload(); }} />}
    </div>
  );
}

function NewInitiative({ onClose }: { onClose: () => void }) {
  const { tr } = useI18n();
  const areas = useLoad<Paged<Area>>("/areas/?page_size=200");
  const { busy, run } = useAction();
  const [f, setF] = useState({ title: "", summary: "", description: "", area: "" });
  const save = async () => {
    const r = await run(async () => {
      const ini = await post<Initiative>("/initiatives/", { ...f, area: f.area ? Number(f.area) : null });
      await post(`/initiatives/${ini.id}/submit/`);
      return ini;
    }, tr("أُرسلت المبادرة للاعتماد.", "Submitted for approval."));
    if (r) onClose();
  };
  return (
    <Dialog title={tr("اقتراح مبادرة", "New initiative")} onClose={onClose}>
      <p className="small muted">{tr("تُراجع المبادرة من منسق قبل نشرها واستقبال أي مساهمات.", "A coordinator reviews it before it can receive contributions.")}</p>
      <Field id="t" label={tr("العنوان", "Title")}><input id="t" className="input" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
      <Field id="s" label={tr("ملخص بسطر واحد", "One-line summary")}><input id="s" className="input" value={f.summary} onChange={(e) => setF({ ...f, summary: e.target.value })} /></Field>
      <Field id="d" label={tr("التفاصيل", "Details")}><textarea id="d" className="input" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
      <Field id="a" label={tr("الحومة", "Area")}>
        <select id="a" className="input" value={f.area} onChange={(e) => setF({ ...f, area: e.target.value })}>
          <option value="">—</option>{areas.data?.results.map((a) => <option key={a.id} value={a.id}>{a.name_ar}</option>)}
        </select></Field>
      <button className="btn block" disabled={busy || !f.title || !f.summary} onClick={save}>{tr("أرسل للاعتماد", "Submit for approval")}</button>
    </Dialog>
  );
}

export function TaskCard({ t, onChange }: { t: Task; onChange: () => void }) {
  const { tr, lang } = useI18n();
  const { me } = useAuth();
  const { busy, run } = useAction();
  const full = t.booked >= t.capacity;
  return (
    <div className="panel">
      <div className="row"><b>{t.title}</b><DemoBadge show={t.is_demo} />{t.skill_name && <span className="badge plain">{t.skill_name}</span>}</div>
      <div className="small muted">
        <Icon name="clock" size={16} /> {formatDate(t.starts_at, lang, true)} — {Math.round(t.duration_minutes / 60 * 10) / 10} {tr("ساعة", "h")}
        {t.location_text && <> — <Icon name="pin" size={16} /> {t.location_text}</>}
      </div>
      {t.description && <p className="small">{t.description}</p>}
      {t.match_reasons && t.match_reasons.length > 0 && <p className="xs" style={{ color: "var(--teal-ink)" }}>{t.match_reasons.join(" — ")}</p>}
      <div className="row between">
        <span className="xs muted num">{num(t.booked, lang)}/{num(t.capacity, lang)} {tr("مشارك", "joined")} — {tr("المسؤول", "lead")}: {t.owner_name}</span>
        {!me ? <Link className="btn small" to="/login?next=/aawen?tab=tasks">{tr("سجّل للحجز", "Sign in to book")}</Link>
          : t.my_booking && t.my_booking.status !== "cancelled" ? (
            <div className="row"><StatusBadge status={t.my_booking.status} />
              {t.my_booking.status === "booked" && <button className="btn small ghost" disabled={busy}
                onClick={() => run(() => post(`/bookings/${t.my_booking!.id}/cancel/`), tr("أُلغي الحجز", "Cancelled")).then(onChange)}>{tr("إلغاء", "Cancel")}</button>}
            </div>
          ) : (
            <button className="btn small teal" disabled={busy || full}
              onClick={() => run(() => post(`/tasks/${t.id}/book/`), tr("حُجزت المهمة. سيؤكد المسؤول حضورك يوم التنفيذ.", "Booked.")).then(onChange)}>
              {full ? tr("اكتمل العدد", "Full") : tr("خُذ المهمة", "Take this task")}</button>
          )}
      </div>
    </div>
  );
}

function Tasks() {
  const { tr } = useI18n();
  const { me } = useAuth();
  const all = useLoad<Paged<Task>>("/tasks/?page_size=50");
  const rec = useLoad<Task[]>(me ? "/tasks/recommended/" : null, [me?.id]);
  if (all.loading && !all.data) return <Loading />;
  if (all.error && !all.data) return <ErrorState error={all.error} onRetry={all.reload} />;
  const reload = () => { all.reload(); rec.reload(); };
  return (
    <div className="stack">
      <StaleNote stale={all.stale} savedAt={all.savedAt} />
      {me && (rec.data?.length ?? 0) > 0 && (
        <>
          <h2>{tr("مناسبة لك", "Suggested for you")}</h2>
          <p className="small muted">{tr("حسب مهاراتك وأوقاتك في «مهاراتي».", "Based on your skills and availability.")}</p>
          <div className="grid two">{rec.data!.slice(0, 4).map((t) => <TaskCard key={t.id} t={t} onChange={reload} />)}</div>
        </>
      )}
      <h2>{tr("كل المهام القادمة", "All upcoming tasks")}</h2>
      {all.data!.results.length === 0 ? <EmptyState icon="hands" title={tr("لا توجد مهام قادمة", "No upcoming tasks")} /> :
        <div className="grid two">{all.data!.results.map((t) => <TaskCard key={t.id} t={t} onChange={reload} />)}</div>}
    </div>
  );
}

const DAYS: [string, string][] = [["السبت", "Sat"], ["الأحد", "Sun"], ["الاثنين", "Mon"], ["الثلاثاء", "Tue"], ["الأربعاء", "Wed"], ["الخميس", "Thu"], ["الجمعة", "Fri"]];
const SLOTS: [string, string, string][] = [["morning", "صباحًا", "Morning"], ["afternoon", "بعد الظهر", "Afternoon"], ["evening", "مساءً", "Evening"]];

function Skills() {
  const { tr } = useI18n();
  const { me } = useAuth();
  const skills = useLoad<{ id: number; name_ar: string; name_en: string }[]>("/skills/");
  const areas = useLoad<Paged<Area>>("/areas/?page_size=200");
  const [p, setP] = useState<{ skills: number[]; availability: { days: number[]; slots: string[] }; preferred_areas: number[]; bio: string } | null>(null);
  const { busy, run } = useAction();
  useEffect(() => {
    if (me) get<typeof p>("/me/volunteer-profile").then((r) => setP({ ...r!, availability: { ...{ days: [] as number[], slots: [] as string[] }, ...(r!.availability ?? {}) } })).catch(() => {});
  }, [me]);
  if (!me) return <EmptyState icon="star" title={tr("سجّل لحفظ مهاراتك", "Sign in to save your skills")} action={<Link className="btn" to="/login?next=/aawen?tab=skills">{tr("تسجيل الدخول", "Sign in")}</Link>}>{tr("نقترح عليك مهام تناسب مهاراتك وأوقاتك.", "We'll suggest matching tasks.")}</EmptyState>;
  if (!p || !skills.data) return <Loading />;
  const tog = <T,>(arr: T[], v: T) => (arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);
  return (
    <div className="panel stack" style={{ maxWidth: 720 }}>
      <fieldset style={{ border: 0, padding: 0 }}><legend><h2>{tr("مهاراتي", "My skills")}</h2></legend>
        <div className="chips">{skills.data.map((s) => <button key={s.id} className="chip" aria-pressed={p.skills.includes(s.id)} onClick={() => setP({ ...p, skills: tog(p.skills, s.id) })}>{tr(s.name_ar, s.name_en)}</button>)}</div>
      </fieldset>
      <fieldset style={{ border: 0, padding: 0 }}><legend className="label"><b>{tr("أيام التوفر", "Available days")}</b></legend>
        <div className="chips">{DAYS.map(([a, e], i) => <button key={i} className="chip" aria-pressed={p.availability.days.includes(i)} onClick={() => setP({ ...p, availability: { ...p.availability, days: tog(p.availability.days, i) } })}>{tr(a, e)}</button>)}</div>
      </fieldset>
      <fieldset style={{ border: 0, padding: 0 }}><legend className="label"><b>{tr("الأوقات", "Times")}</b></legend>
        <div className="chips">{SLOTS.map(([k, a, e]) => <button key={k} className="chip" aria-pressed={p.availability.slots.includes(k)} onClick={() => setP({ ...p, availability: { ...p.availability, slots: tog(p.availability.slots, k) } })}>{tr(a, e)}</button>)}</div>
      </fieldset>
      <fieldset style={{ border: 0, padding: 0 }}><legend className="label"><b>{tr("مناطق أفضّل العمل فيها", "Preferred areas")}</b></legend>
        <div className="chips">{areas.data?.results.map((a) => <button key={a.id} className="chip" aria-pressed={p.preferred_areas.includes(a.id)} onClick={() => setP({ ...p, preferred_areas: tog(p.preferred_areas, a.id) })}>{a.name_ar}</button>)}</div>
      </fieldset>
      <button className="btn" disabled={busy} onClick={() => run(() => put("/me/volunteer-profile", p), tr("حُفظت مهاراتك. شوف المهام المناسبة لك في «خُذ مهمة».", "Saved."))}>{tr("احفظ", "Save")}</button>
    </div>
  );
}

function Store() {
  const { tr, lang } = useI18n();
  const { me } = useAuth();
  const { data, error, loading, reload, stale, savedAt } = useLoad<Paged<Resource>>("/resources/?page_size=100");
  const [sel, setSel] = useState<Resource | null>(null);
  const [qty, setQty] = useState(1);
  const [purpose, setPurpose] = useState("");
  const { busy, run } = useAction();
  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorState error={error} onRetry={reload} />;
  return (
    <div className="stack">
      <StaleNote stale={stale} savedAt={savedAt} />
      <p className="small muted">{tr("أدوات ومواد للتبرع أو الإعارة. تحجز أولًا، ثم يسلّمك مسؤول الاستلام ويسجّل الكمية.", "Reserve first; the custodian records the hand-over.")}</p>
      {data!.results.length === 0 ? <EmptyState icon="store" title={tr("المخزن فاضي حاليًا", "The store is empty")} /> : (
        <div className="grid two">
          {data!.results.map((r) => (
            <div key={r.id} className="panel">
              <div className="row"><b>{r.title}</b><span className="badge plain">{r.kind_label}</span><DemoBadge show={r.is_demo} /></div>
              <div className="row small" style={{ margin: "6px 0" }}>
                <span><b className="num">{num(r.available_quantity, lang)}</b> {tr("متاح", "available")}</span>
                <span className="muted">{num(r.reserved_quantity, lang)} {tr("محجوز", "reserved")}</span>
                <span className="muted">{num(r.kind === "loan" ? r.out_quantity : r.consumed_quantity, lang)} {r.kind === "loan" ? tr("مُعار", "on loan") : tr("مُسلّم", "handed out")}</span>
              </div>
              <div className="xs muted">{tr("مسؤول الاستلام", "Custodian")}: {r.custodian_name} — {r.pickup_location}{r.kind === "loan" && ` — ${tr("مدة الإعارة", "loan")} ${r.max_loan_days} ${tr("أيام", "days")}`}</div>
              <button className="btn small teal" style={{ marginTop: 8 }} disabled={r.available_quantity < 1}
                onClick={() => (me ? (setSel(r), setQty(1)) : (window.location.href = "/login?next=/aawen?tab=store"))}>
                {r.available_quantity < 1 ? tr("غير متاح الآن", "Unavailable") : tr("احجز", "Reserve")}</button>
            </div>
          ))}
        </div>
      )}
      {sel && (
        <Dialog title={`${tr("حجز", "Reserve")}: ${sel.title}`} onClose={() => setSel(null)}>
          <Field id="q" label={tr("الكمية", "Quantity")} hint={`${tr("المتاح الآن", "Available")}: ${sel.available_quantity} ${sel.unit}`}>
            <input id="q" type="number" min={1} max={sel.available_quantity} className="input" value={qty} onChange={(e) => setQty(Number(e.target.value))} />
          </Field>
          <Field id="pp" label={tr("لأي غرض؟", "What for?")}><input id="pp" className="input" value={purpose} onChange={(e) => setPurpose(e.target.value)} /></Field>
          <button className="btn block" disabled={busy || qty < 1} onClick={async () => {
            const r = await run(() => post(`/resources/${sel.id}/reserve/`, { quantity: qty, purpose, client_id: crypto.randomUUID?.() }),
              tr("تم الحجز. استلم خلال يومين من مسؤول الاستلام.", "Reserved — pick up within 2 days."));
            if (r) { setSel(null); reload(); } else reload();
          }}>{tr("أكّد الحجز", "Confirm reservation")}</button>
        </Dialog>
      )}
    </div>
  );
}

function CarePoints() {
  const { tr, lang } = useI18n();
  const { data, error, loading, reload, stale, savedAt } = useLoad<Paged<{ id: number; name: string; host_type: string; area_name: string; services: string[]; hours: string; contact: string; verified_at: string; is_demo: boolean }>>("/care-points/?page_size=100");
  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorState error={error} onRetry={reload} />;
  return data!.results.length === 0 ? <EmptyState icon="care" title={tr("لا توجد نقاط عناية موثقة بعد", "No verified care points yet")} /> : (
    <><StaleNote stale={stale} savedAt={savedAt} /><ul className="list panel">
      {data!.results.map((c) => (
        <li key={c.id} className="list-item"><Icon name="care" /><div className="grow">
          <div className="row"><b>{c.name}</b><span className="xs muted">{c.host_type}</span><DemoBadge show={c.is_demo} /></div>
          <div className="small">{c.services.join(" — ")}</div>
          <div className="xs muted">{c.hours} — {c.area_name} — {tr("آخر تحقق", "verified")} {timeAgo(c.verified_at, lang)}</div>
        </div></li>
      ))}
    </ul></>
  );
}

function Surplus() {
  const { tr, lang } = useI18n();
  const { me, config } = useAuth();
  const { data, error, loading, reload } = useLoad<Paged<{ id: number; title: string; kind: string; quantity: string; pickup_location: string; pickup_window: string; available_until: string; status: string; mine: boolean; reserved_by_me: boolean; is_demo: boolean }>>("/surplus/?page_size=100");
  const { busy, run } = useAction();
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ title: "", quantity: "", pickup_location: "", pickup_window: "", kind: "non_food" });
  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorState error={error} onRetry={reload} />;
  return (
    <div className="stack">
      {!config?.features.surplus_food && <div className="banner info">{tr("مشاركة الأغذية غير مفعّلة حتى تجهيز إجراءات السلامة الغذائية مع شريك مختص. يمكن مشاركة الأشياء غير الغذائية.", "Food sharing is off until a food-safety partner is set up.")}</div>}
      {me && <button className="btn small ghost" style={{ alignSelf: "flex-start" }} onClick={() => setOpen(true)}><Icon name="plus" size={18} />{tr("اعرض فائضًا", "Offer surplus")}</button>}
      {data!.results.length === 0 ? <EmptyState icon="box" title={tr("لا يوجد فائض معروض الآن", "Nothing offered right now")} /> : (
        <ul className="list panel">
          {data!.results.map((o) => (
            <li key={o.id} className="list-item"><Icon name="box" /><div className="grow">
              <div className="row"><b>{o.title}</b><StatusBadge status={o.status === "available" ? "open" : o.status} label={{ available: tr("متاح", "Available"), reserved: tr("محجوز", "Reserved"), handed_over: tr("مُسلّم", "Handed over") }[o.status]} /><DemoBadge show={o.is_demo} /></div>
              <div className="small">{o.quantity} — {o.pickup_window} — {o.pickup_location}</div>
              <div className="xs muted">{tr("متاح حتى", "Until")} {formatDate(o.available_until, lang)}</div>
            </div>
              {me && !o.mine && o.status === "available" && <button className="btn small teal" disabled={busy} onClick={() => run(() => post(`/surplus/${o.id}/reserve/`), tr("حُجز لك. يظهر مكان الاستلام الآن.", "Reserved.")).then(reload)}>{tr("احجز", "Reserve")}</button>}
              {o.mine && o.status === "reserved" && <button className="btn small" disabled={busy} onClick={() => run(() => post(`/surplus/${o.id}/handover/`), tr("سُجّل التسليم.", "Handed over.")).then(reload)}>{tr("تم التسليم", "Mark handed over")}</button>}
            </li>
          ))}
        </ul>
      )}
      {open && (
        <Dialog title={tr("عرض فائض", "Offer surplus")} onClose={() => setOpen(false)}>
          <Field id="st" label={tr("ماذا تعرض؟", "What?")}><input id="st" className="input" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
          <Field id="sq" label={tr("الكمية", "Quantity")}><input id="sq" className="input" value={f.quantity} onChange={(e) => setF({ ...f, quantity: e.target.value })} /></Field>
          <Field id="sl" label={tr("مكان الاستلام (يظهر لمن يحجز فقط)", "Pickup place (shown only after reservation)")}><input id="sl" className="input" value={f.pickup_location} onChange={(e) => setF({ ...f, pickup_location: e.target.value })} /></Field>
          <Field id="sw" label={tr("وقت الاستلام", "Pickup time")}><input id="sw" className="input" value={f.pickup_window} onChange={(e) => setF({ ...f, pickup_window: e.target.value })} /></Field>
          <button className="btn block" disabled={busy || !f.title} onClick={async () => {
            const r = await run(() => post("/surplus/", { ...f, available_until: new Date(Date.now() + 5 * 86400e3).toISOString() }), tr("نُشر العرض.", "Published."));
            if (r) { setOpen(false); reload(); }
          }}>{tr("انشر", "Publish")}</button>
        </Dialog>
      )}
    </div>
  );
}
