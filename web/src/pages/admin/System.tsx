import { useEffect, useState } from "react";

import { del, get, patch, post } from "../../api/client";
import type { Area, Category, Paged } from "../../api/types";
import { PageHeader } from "../../components/Shell";
import { Dialog, ErrorState, Field, Loading, useAction } from "../../components/ui";
import { formatDate } from "../../lib/format";
import { useLoad } from "../../lib/hooks";
import { useI18n } from "../../lib/i18n";

export function Categories() {
  const { tr } = useI18n();
  const { data, error, loading, reload } = useLoad<Paged<Category>>("/categories/?page_size=200");
  const [edit, setEdit] = useState<Partial<Category> | null>(null);
  const { busy, run } = useAction();
  const save = async () => {
    const body = { ...edit, keywords: typeof edit!.keywords === "string" ? (edit!.keywords as unknown as string).split(/[,،]\s*/).filter(Boolean) : edit!.keywords };
    const r = await run(() => (edit!.id ? patch(`/categories/${edit!.id}/`, body) : post("/categories/", body)), tr("حُفظت الفئة", "Saved"));
    if (r) { setEdit(null); reload(); }
  };
  if (loading && !data) return <Loading />;
  if (error && !data) return <ErrorState error={error} onRetry={reload} />;
  return (
    <div>
      <PageHeader title={tr("فئات البلاغات", "Report categories")}><button className="btn small" onClick={() => setEdit({ layer: "services", hazard_weight: 2, active: true, keywords: [] })}>{tr("فئة جديدة", "New category")}</button></PageHeader>
      <div className="table-wrap"><table className="data"><thead><tr><th>{tr("الاسم", "Name")}</th><th>{tr("الطبقة", "Layer")}</th><th>{tr("الخطورة", "Hazard")}</th><th>{tr("المراجعة اللاحقة (يوم)", "Follow-up (days)")}</th><th>{tr("فعالة", "Active")}</th><th /></tr></thead>
        <tbody>{data!.results.map((c) => <tr key={c.id}><td>{c.name_ar} <span className="xs muted">{c.name_en}</span></td><td>{c.layer}</td><td>{c.hazard_weight}</td><td>{c.followup_days ?? "—"}</td><td>{c.active ? "✓" : "—"}</td>
          <td><button className="btn small ghost" onClick={() => setEdit({ ...c })}>{tr("تعديل", "Edit")}</button></td></tr>)}</tbody></table></div>
      {edit && (
        <Dialog title={edit.id ? tr("تعديل فئة", "Edit category") : tr("فئة جديدة", "New category")} onClose={() => setEdit(null)}>
          {!edit.id && <Field id="cs" label={tr("المعرف (لاتيني)", "Slug")}><input id="cs" className="input" dir="ltr" value={edit.slug ?? ""} onChange={(e) => setEdit({ ...edit, slug: e.target.value })} /></Field>}
          <Field id="ca" label={tr("الاسم بالعربية", "Arabic name")}><input id="ca" className="input" value={edit.name_ar ?? ""} onChange={(e) => setEdit({ ...edit, name_ar: e.target.value })} /></Field>
          <Field id="ce" label={tr("الاسم بالإنجليزية", "English name")}><input id="ce" className="input" dir="ltr" value={edit.name_en ?? ""} onChange={(e) => setEdit({ ...edit, name_en: e.target.value })} /></Field>
          <Field id="cl" label={tr("الطبقة", "Layer")}><select id="cl" className="input" value={edit.layer} onChange={(e) => setEdit({ ...edit, layer: e.target.value })}>
            <option value="services">{tr("مشاكل الخدمات", "Services")}</option><option value="pedestrian">{tr("سهولة حركة المشاة", "Pedestrian")}</option><option value="road">{tr("الطريق", "Road")}</option></select></Field>
          <Field id="ch" label={tr("درجة الخطورة 0–5", "Hazard 0–5")}><input id="ch" type="number" min={0} max={5} className="input" value={edit.hazard_weight ?? 2} onChange={(e) => setEdit({ ...edit, hazard_weight: Number(e.target.value) })} /></Field>
          <Field id="cf" label={tr("مراجعة لاحقة بعد (يوم)", "Follow-up after (days)")}><input id="cf" type="number" className="input" value={edit.followup_days ?? ""} onChange={(e) => setEdit({ ...edit, followup_days: e.target.value ? Number(e.target.value) : null })} /></Field>
          <Field id="ck" label={tr("كلمات مفتاحية للاقتراح الآلي (مفصولة بفواصل)", "Keywords (comma separated)")}><input id="ck" className="input" value={Array.isArray(edit.keywords) ? edit.keywords.join("، ") : (edit.keywords ?? "")} onChange={(e) => setEdit({ ...edit, keywords: e.target.value as unknown as string[] })} /></Field>
          <label className="row"><input type="checkbox" checked={!!edit.active} onChange={(e) => setEdit({ ...edit, active: e.target.checked })} />{tr("فعالة", "Active")}</label>
          <button className="btn block" style={{ marginTop: 12 }} disabled={busy} onClick={save}>{tr("احفظ", "Save")}</button>
        </Dialog>
      )}
    </div>
  );
}

type Agency = { id: number; name: string; kind: string; contact_phone: string; is_linked: boolean; active: boolean };
type Rule = { id: number; category: number; category_name: string; area: number | null; area_name: string | null; city: number | null; agency: number; agency_name: string; priority: number; active: boolean };

export function Geo() {
  const { tr } = useI18n();
  const areas = useLoad<Paged<Area>>("/areas/?page_size=300");
  const agencies = useLoad<Paged<Agency>>("/agencies/?page_size=300");
  const rules = useLoad<Paged<Rule>>("/jurisdiction-rules/?page_size=500");
  const cats = useLoad<Paged<Category>>("/categories/?page_size=200");
  const cities = useLoad<Paged<{ id: number; name_ar: string }>>("/cities/");
  const { busy, run } = useAction();
  const [ag, setAg] = useState<Partial<Agency> | null>(null);
  const [rule, setRule] = useState<{ category: string; area: string; agency: string; priority: number } | null>(null);
  const [area, setArea] = useState<{ name_ar: string; slug: string; geojson: string; boundary_source: string } | null>(null);
  return (
    <div>
      <PageHeader title={tr("المناطق والجهات والتوجيه", "Areas, agencies & routing")} />
      <div className="section"><h2>{tr("قواعد الاختصاص", "Jurisdiction rules")}</h2><button className="btn small more" onClick={() => setRule({ category: "", area: "", agency: "", priority: 100 })}>{tr("قاعدة جديدة", "New rule")}</button></div>
      <p className="small muted">{tr("المنطقة × الفئة ← الجهة. القاعدة الخاصة بمنطقة تتقدم على قاعدة المدينة. الحالات الحدودية تُرسل للمراجعة.", "Area × category → agency; area rules override city rules.")}</p>
      <div className="table-wrap"><table className="data"><thead><tr><th>{tr("الفئة", "Category")}</th><th>{tr("النطاق", "Scope")}</th><th>{tr("الجهة", "Agency")}</th><th>{tr("الأولوية", "Priority")}</th><th /></tr></thead>
        <tbody>{rules.data?.results.map((r) => <tr key={r.id}><td>{r.category_name}</td><td>{r.area_name ?? tr("كامل المدينة", "Whole city")}</td><td>{r.agency_name}</td><td>{r.priority}</td>
          <td><button className="btn small ghost" disabled={busy} onClick={() => run(() => del(`/jurisdiction-rules/${r.id}/`), tr("حُذفت القاعدة", "Deleted")).then(rules.reload)}>{tr("حذف", "Delete")}</button></td></tr>)}</tbody></table></div>

      <div className="section"><h2>{tr("الجهات", "Agencies")}</h2><button className="btn small more" onClick={() => setAg({ kind: "municipality", active: true, is_linked: false })}>{tr("جهة جديدة", "New agency")}</button></div>
      <div className="table-wrap"><table className="data"><tbody>{agencies.data?.results.map((a) => <tr key={a.id}><td>{a.name}</td><td>{a.kind}</td><td>{a.is_linked ? tr("مرتبطة بالبوابة", "On portal") : tr("غير مرتبطة", "Not on portal")}</td>
        <td><button className="btn small ghost" onClick={() => setAg(a)}>{tr("تعديل", "Edit")}</button></td></tr>)}</tbody></table></div>

      <div className="section"><h2>{tr("المناطق", "Areas")}</h2><button className="btn small more" onClick={() => setArea({ name_ar: "", slug: "", geojson: "", boundary_source: "" })}>{tr("استيراد منطقة", "Import area")}</button></div>
      <div className="table-wrap"><table className="data"><tbody>{areas.data?.results.map((a) => <tr key={a.id}><td>{a.name_ar}</td><td>{a.population ?? "—"}</td><td>{a.boundary_source}{a.boundary_source.startsWith("approximate") && <span className="badge s-wait" style={{ marginInlineStart: 6 }}>{tr("حدود تقريبية", "Approximate")}</span>}</td></tr>)}</tbody></table></div>

      {ag && (
        <Dialog title={ag.id ? tr("تعديل جهة", "Edit agency") : tr("جهة جديدة", "New agency")} onClose={() => setAg(null)}>
          <Field id="an" label={tr("الاسم", "Name")}><input id="an" className="input" value={ag.name ?? ""} onChange={(e) => setAg({ ...ag, name: e.target.value })} /></Field>
          <Field id="ak" label={tr("النوع", "Kind")}><select id="ak" className="input" value={ag.kind} onChange={(e) => setAg({ ...ag, kind: e.target.value })}>
            {[["municipality", "بلدية"], ["utility", "شركة خدمية"], ["ministry", "وزارة/إدارة"], ["partner", "شريك"], ["ngo", "منظمة"]].map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></Field>
          <Field id="ap" label={tr("هاتف التواصل", "Phone")}><input id="ap" className="input" dir="ltr" value={ag.contact_phone ?? ""} onChange={(e) => setAg({ ...ag, contact_phone: e.target.value })} /></Field>
          <label className="row"><input type="checkbox" checked={!!ag.is_linked} onChange={(e) => setAg({ ...ag, is_linked: e.target.checked })} />{tr("تستخدم البوابة وتؤكد الاستلام بنفسها", "Uses the portal")}</label>
          <button className="btn block" style={{ marginTop: 12 }} disabled={busy || !ag.name} onClick={() => run(() => (ag.id ? patch(`/agencies/${ag.id}/`, ag) : post("/agencies/", { ...ag, city: cities.data?.results[0]?.id })), tr("حُفظت", "Saved")).then((r) => { if (r) { setAg(null); agencies.reload(); } })}>{tr("احفظ", "Save")}</button>
        </Dialog>
      )}
      {rule && (
        <Dialog title={tr("قاعدة اختصاص", "Jurisdiction rule")} onClose={() => setRule(null)}>
          <Field id="rc" label={tr("الفئة", "Category")}><select id="rc" className="input" value={rule.category} onChange={(e) => setRule({ ...rule, category: e.target.value })}><option value="">—</option>{cats.data?.results.map((c) => <option key={c.id} value={c.id}>{c.name_ar}</option>)}</select></Field>
          <Field id="ra" label={tr("المنطقة (فارغ = كامل المدينة)", "Area (empty = whole city)")}><select id="ra" className="input" value={rule.area} onChange={(e) => setRule({ ...rule, area: e.target.value })}><option value="">{tr("كامل المدينة", "Whole city")}</option>{areas.data?.results.map((a) => <option key={a.id} value={a.id}>{a.name_ar}</option>)}</select></Field>
          <Field id="rg" label={tr("الجهة", "Agency")}><select id="rg" className="input" value={rule.agency} onChange={(e) => setRule({ ...rule, agency: e.target.value })}><option value="">—</option>{agencies.data?.results.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></Field>
          <button className="btn block" disabled={busy || !rule.category || !rule.agency} onClick={() => run(() => post("/jurisdiction-rules/", { category: Number(rule.category), agency: Number(rule.agency), area: rule.area ? Number(rule.area) : null, city: rule.area ? null : cities.data?.results[0]?.id, priority: rule.area ? 10 : 100 }), tr("أُضيفت القاعدة", "Added")).then((r) => { if (r) { setRule(null); rules.reload(); } })}>{tr("أضف", "Add")}</button>
        </Dialog>
      )}
      {area && (
        <Dialog title={tr("استيراد حدود منطقة", "Import area boundary")} onClose={() => setArea(null)}>
          <p className="small muted">{tr("الصق مضلع GeoJSON من مصدر رسمي (بلدية / مصلحة التخطيط). للاستيراد الجماعي استخدم أمر import_areas.", "Paste official GeoJSON. Use import_areas for bulk imports.")}</p>
          <Field id="aa" label={tr("الاسم", "Name")}><input id="aa" className="input" value={area.name_ar} onChange={(e) => setArea({ ...area, name_ar: e.target.value })} /></Field>
          <Field id="as" label={tr("المعرف", "Slug")}><input id="as" className="input" dir="ltr" value={area.slug} onChange={(e) => setArea({ ...area, slug: e.target.value })} /></Field>
          <Field id="asrc" label={tr("مصدر الحدود", "Boundary source")}><input id="asrc" className="input" value={area.boundary_source} onChange={(e) => setArea({ ...area, boundary_source: e.target.value })} /></Field>
          <Field id="ag" label="GeoJSON"><textarea id="ag" className="input" dir="ltr" value={area.geojson} onChange={(e) => setArea({ ...area, geojson: e.target.value })} /></Field>
          <button className="btn block" disabled={busy} onClick={() => run(async () => post("/areas/", { ...area, city: cities.data?.results[0]?.id, geojson: JSON.parse(area.geojson) }), tr("أُضيفت المنطقة", "Added")).then((r) => { if (r) { setArea(null); areas.reload(); } })}>{tr("استيراد", "Import")}</button>
        </Dialog>
      )}
    </div>
  );
}

type U = { id: number; phone: string; display_name: string; is_active: boolean; roles: { id: number; role: string; role_label: string; area_name: string | null; agency_name: string | null; active: boolean }[]; is_demo: boolean };
const ROLES: [string, string][] = [["ambassador", "سفير"], ["volunteer", "متطوع"], ["reviewer", "مراجع"], ["coordinator", "منسق"], ["agency_staff", "موظف جهة"],
  ["initiative_manager", "مسؤول مبادرة"], ["accountant", "محاسب"], ["financial_auditor", "مراجع مالي"], ["sysadmin", "مدير النظام"]];

export function Users() {
  const { tr } = useI18n();
  const [q, setQ] = useState("");
  const { data, error, loading, reload } = useLoad<Paged<U>>(`/admin/users/?q=${encodeURIComponent(q)}&page_size=100`, [q]);
  const areas = useLoad<Paged<Area>>("/areas/?page_size=300");
  const agencies = useLoad<Paged<{ id: number; name: string }>>("/agencies/?page_size=300");
  const { busy, run } = useAction();
  const [grant, setGrant] = useState<{ user: number; role: string; area: string; agency: string } | null>(null);
  const [nu, setNu] = useState<{ phone: string; display_name: string } | null>(null);
  return (
    <div>
      <PageHeader title={tr("المستخدمون والأدوار", "Users & roles")}><button className="btn small" onClick={() => setNu({ phone: "", display_name: "" })}>{tr("حساب فريق جديد", "New staff account")}</button></PageHeader>
      <p className="small muted">{tr("لا كلمات مرور افتراضية: يدخل الموظف برمز يصل لهاتفه. كل منح أو سحب دور يُسجّل في سجل التغييرات.", "No default passwords; staff sign in with a code sent to their phone. Every role change is audited.")}</p>
      <Field id="uq" label={tr("بحث", "Search")}><input id="uq" className="input" value={q} onChange={(e) => setQ(e.target.value)} /></Field>
      {loading && !data ? <Loading /> : error && !data ? <ErrorState error={error} onRetry={reload} /> : (
        <div className="table-wrap"><table className="data"><thead><tr><th>{tr("الاسم", "Name")}</th><th>{tr("الهاتف", "Phone")}</th><th>{tr("الأدوار", "Roles")}</th><th /></tr></thead>
          <tbody>{data!.results.map((u) => <tr key={u.id}><td>{u.display_name || "—"}{!u.is_active && <span className="badge s-bad"> {tr("معطل", "Disabled")}</span>}</td><td dir="ltr">{u.phone}</td>
            <td>{u.roles.filter((r) => r.active).map((r) => <span key={r.id} className="badge plain" style={{ margin: 2 }}>{r.role_label}{r.area_name ? ` · ${r.area_name}` : ""}{r.agency_name ? ` · ${r.agency_name}` : ""}
              <button className="icon-btn" style={{ width: 22, height: 22 }} aria-label={tr("سحب الدور", "Revoke")} onClick={() => run(() => del(`/admin/roles/${r.id}/`), tr("سُحب الدور", "Revoked")).then(reload)}>×</button></span>)}</td>
            <td><button className="btn small ghost" onClick={() => setGrant({ user: u.id, role: "reviewer", area: "", agency: "" })}>{tr("امنح دورًا", "Grant role")}</button></td></tr>)}</tbody></table></div>
      )}
      {grant && (
        <Dialog title={tr("منح دور", "Grant role")} onClose={() => setGrant(null)}>
          <Field id="gr" label={tr("الدور", "Role")}><select id="gr" className="input" value={grant.role} onChange={(e) => setGrant({ ...grant, role: e.target.value })}>{ROLES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></Field>
          <Field id="ga" label={tr("نطاق المنطقة (فارغ = الكل)", "Area scope (empty = all)")}><select id="ga" className="input" value={grant.area} onChange={(e) => setGrant({ ...grant, area: e.target.value })}><option value="">{tr("كل المناطق", "All areas")}</option>{areas.data?.results.map((a) => <option key={a.id} value={a.id}>{a.name_ar}</option>)}</select></Field>
          {grant.role === "agency_staff" && <Field id="gg" label={tr("الجهة (مطلوبة)", "Agency (required)")}><select id="gg" className="input" value={grant.agency} onChange={(e) => setGrant({ ...grant, agency: e.target.value })}><option value="">—</option>{agencies.data?.results.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></Field>}
          <button className="btn block" disabled={busy} onClick={() => run(() => post("/admin/roles/", { user: grant.user, role: grant.role, area: grant.area ? Number(grant.area) : null, agency: grant.agency ? Number(grant.agency) : null }), tr("مُنح الدور", "Granted")).then((r) => { if (r) { setGrant(null); reload(); } })}>{tr("امنح", "Grant")}</button>
        </Dialog>
      )}
      {nu && (
        <Dialog title={tr("حساب فريق جديد", "New staff account")} onClose={() => setNu(null)}>
          <Field id="np" label={tr("الهاتف", "Phone")}><input id="np" className="input" dir="ltr" value={nu.phone} onChange={(e) => setNu({ ...nu, phone: e.target.value })} /></Field>
          <Field id="nn" label={tr("الاسم", "Name")}><input id="nn" className="input" value={nu.display_name} onChange={(e) => setNu({ ...nu, display_name: e.target.value })} /></Field>
          <button className="btn block" disabled={busy} onClick={() => run(() => post("/admin/users/", nu), tr("أُنشئ الحساب. امنحه دورًا الآن.", "Created — now grant a role.")).then((r) => { if (r) { setNu(null); reload(); } })}>{tr("أنشئ", "Create")}</button>
        </Dialog>
      )}
    </div>
  );
}

type RoadRule = { ttl: number; extend: number; max_lifetime: number; stale_after: number; clear_votes: number };
type SettingsT = { road_rules: Record<string, RoadRule>; routing_boundary_tolerance_m: number; similar_radius_m: number; similar_window_days: number;
  followup_days_default: number; referral_escalation_days: number; features: Record<string, boolean>;
  emergency_notice: { ar: string; en: string; contacts: { name: string; phone: string }[] } };

export function Settings() {
  const { tr } = useI18n();
  const [s, setS] = useState<SettingsT | null>(null);
  const [err, setErr] = useState<unknown>(null);
  const { busy, run } = useAction();
  useEffect(() => { get<SettingsT>("/admin/settings").then(setS).catch(setErr); }, []);
  if (err) return <ErrorState error={err} />;
  if (!s) return <Loading />;
  const save = (keys: (keyof SettingsT)[]) => run(() => patch<SettingsT>("/admin/settings", Object.fromEntries(keys.map((k) => [k, s[k]]))), tr("حُفظت الإعدادات", "Settings saved")).then((r) => r && setS(r));
  const typeLabel: Record<string, string> = { accident: tr("حادث", "Accident"), congestion: tr("ازدحام", "Congestion"), closure: tr("إغلاق", "Closure"), obstacle: tr("عائق", "Obstacle") };
  return (
    <div className="stack">
      <PageHeader title={tr("الإعدادات", "Settings")} />
      <section className="panel">
        <h2>{tr("قواعد صلاحية تنبيهات الطريق (بالدقائق)", "Road alert validity rules (minutes)")}</h2>
        <div className="table-wrap"><table className="data"><thead><tr><th /><th>{tr("المدة الأولى", "Initial")}</th><th>{tr("تمديد لكل «ما زال موجود»", "Extend per confirm")}</th><th>{tr("أقصى عمر", "Max lifetime")}</th><th>{tr("يُعد متأخرًا بعد", "Late after")}</th><th>{tr("أصوات «الطريق فتح»", "Open votes")}</th></tr></thead>
          <tbody>{Object.entries(s.road_rules).map(([t, r]) => <tr key={t}><td>{typeLabel[t] ?? t}</td>
            {(["ttl", "extend", "max_lifetime", "stale_after", "clear_votes"] as (keyof RoadRule)[]).map((k) => <td key={k}><input aria-label={`${typeLabel[t]} ${k}`} className="input" type="number" min={1} style={{ minWidth: 80 }} value={r[k]}
              onChange={(e) => setS({ ...s, road_rules: { ...s.road_rules, [t]: { ...r, [k]: Number(e.target.value) } } })} /></td>)}</tr>)}</tbody></table></div>
        <button className="btn small" style={{ marginTop: 8 }} disabled={busy} onClick={() => save(["road_rules"])}>{tr("احفظ القواعد", "Save rules")}</button>
      </section>
      <section className="panel">
        <h2>{tr("البلاغات والتوجيه", "Reports & routing")}</h2>
        <div className="grid two">
          {([["routing_boundary_tolerance_m", "مسافة الحالة الحدودية (م)", "Boundary tolerance (m)"], ["similar_radius_m", "نصف قطر البلاغات المشابهة (م)", "Similar radius (m)"],
            ["similar_window_days", "نافذة البحث عن المشابه (يوم)", "Similar window (days)"], ["followup_days_default", "المراجعة اللاحقة بعد (يوم)", "Follow-up after (days)"],
            ["referral_escalation_days", "تصعيد الإحالة بلا استلام بعد (يوم)", "Escalate unacknowledged after (days)"]] as [keyof SettingsT, string, string][]).map(([k, a, e]) => (
            <Field key={k} id={k} label={tr(a, e)}><input id={k} type="number" min={1} className="input" value={s[k] as number} onChange={(ev) => setS({ ...s, [k]: Number(ev.target.value) })} /></Field>))}
        </div>
        <p className="xs muted">{tr("التصعيد ينبّه المنسق فقط؛ لا يُغلق أي بلاغ بسبب مرور الوقت.", "Escalation only alerts the coordinator; nothing closes by time.")}</p>
        <button className="btn small" disabled={busy} onClick={() => save(["routing_boundary_tolerance_m", "similar_radius_m", "similar_window_days", "followup_days_default", "referral_escalation_days"])}>{tr("احفظ", "Save")}</button>
      </section>
      <section className="panel">
        <h2>{tr("المزايا", "Features")}</h2>
        {Object.entries(s.features).map(([k, v]) => <label key={k} className="row" style={{ padding: 4 }}><input type="checkbox" checked={v} onChange={(e) => setS({ ...s, features: { ...s.features, [k]: e.target.checked } })} />
          {{ surplus_food: tr("مشاركة الأغذية (فعّلها فقط بعد تجهيز إجراءات السلامة وشريك مختص)", "Food surplus (only with a food-safety partner)"), public_registration: tr("التسجيل العام", "Public registration"),
             english_ui: tr("الواجهة الإنجليزية", "English UI"), ai_assist: tr("المساعدة الذكية (اقتراح الفئة والتنبيه للبيانات الحساسة)", "AI assist") }[k] ?? k}</label>)}
        <button className="btn small" disabled={busy} onClick={() => save(["features"])}>{tr("احفظ", "Save")}</button>
      </section>
      <section className="panel">
        <h2>{tr("تنبيه الطوارئ وأرقامه الرسمية", "Emergency notice & official numbers")}</h2>
        <p className="xs muted">{tr("أدخل أرقامًا رسمية متحققًا منها فقط.", "Only enter verified official numbers.")}</p>
        <Field id="ea" label={tr("النص العربي", "Arabic text")}><textarea id="ea" className="input" value={s.emergency_notice.ar} onChange={(e) => setS({ ...s, emergency_notice: { ...s.emergency_notice, ar: e.target.value } })} /></Field>
        {s.emergency_notice.contacts.map((c, i) => <div key={i} className="row"><input aria-label={tr("الجهة", "Name")} className="input" style={{ maxWidth: 220 }} value={c.name} onChange={(e) => { const cs = [...s.emergency_notice.contacts]; cs[i] = { ...c, name: e.target.value }; setS({ ...s, emergency_notice: { ...s.emergency_notice, contacts: cs } }); }} />
          <input aria-label={tr("الرقم", "Number")} className="input" dir="ltr" style={{ maxWidth: 160 }} value={c.phone} onChange={(e) => { const cs = [...s.emergency_notice.contacts]; cs[i] = { ...c, phone: e.target.value }; setS({ ...s, emergency_notice: { ...s.emergency_notice, contacts: cs } }); }} />
          <button className="btn small ghost" onClick={() => setS({ ...s, emergency_notice: { ...s.emergency_notice, contacts: s.emergency_notice.contacts.filter((_, j) => j !== i) } })}>{tr("حذف", "Remove")}</button></div>)}
        <div className="row" style={{ marginTop: 8 }}><button className="btn small ghost" onClick={() => setS({ ...s, emergency_notice: { ...s.emergency_notice, contacts: [...s.emergency_notice.contacts, { name: "", phone: "" }] } })}>{tr("أضف رقمًا", "Add number")}</button>
          <button className="btn small" disabled={busy} onClick={() => save(["emergency_notice"])}>{tr("احفظ", "Save")}</button></div>
      </section>
    </div>
  );
}

export function Audit() {
  const { tr, lang } = useI18n();
  const [prefix, setPrefix] = useState("");
  const { data, error, loading, reload } = useLoad<Paged<{ id: number; at: string; actor_name: string | null; action: string; target_type: string; target_id: string; data: Record<string, unknown>; ip: string | null }>>(`/admin/audit/?page_size=200&prefix=${prefix}`, [prefix]);
  return (
    <div>
      <PageHeader title={tr("سجل التغييرات الحساسة", "Audit log")} />
      <div className="chips" style={{ marginBottom: 12 }}>{[["", "الكل", "All"], ["report.", "البلاغات", "Reports"], ["role.", "الأدوار", "Roles"], ["finance.", "المالية", "Finance"], ["media.", "الوسائط", "Media"], ["settings.", "الإعدادات", "Settings"]].map(([k, a, e]) =>
        <button key={k} className="chip" aria-pressed={prefix === k} onClick={() => setPrefix(k)}>{tr(a, e)}</button>)}</div>
      {loading && !data ? <Loading /> : error && !data ? <ErrorState error={error} onRetry={reload} /> : (
        <div className="table-wrap"><table className="data"><thead><tr><th>{tr("الوقت", "Time")}</th><th>{tr("المنفّذ", "Actor")}</th><th>{tr("الإجراء", "Action")}</th><th>{tr("الهدف", "Target")}</th><th>{tr("التفاصيل", "Details")}</th></tr></thead>
          <tbody>{data!.results.map((a) => <tr key={a.id}><td>{formatDate(a.at, lang, true)}</td><td>{a.actor_name ?? tr("النظام", "System")}</td><td dir="ltr">{a.action}</td><td dir="ltr">{a.target_type}#{a.target_id}</td>
            <td className="xs" dir="ltr" style={{ maxWidth: 360, wordBreak: "break-word" }}>{JSON.stringify(a.data)}</td></tr>)}</tbody></table></div>
      )}
    </div>
  );
}
