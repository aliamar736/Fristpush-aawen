import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { get } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { flushOutbox, listDrafts } from "../lib/drafts";
import { useOnline } from "../lib/hooks";
import { useI18n } from "../lib/i18n";
import { Icon } from "./Icon";
import { useToast } from "./ui";

export function Logo({ dark = false, compact = false }: { dark?: boolean; compact?: boolean }) {
  const src = compact ? (dark ? "/brand/aawen-mark-on-dark.svg" : "/brand/aawen-mark.svg")
    : dark ? "/brand/aawen-lockup-on-dark.svg" : "/brand/aawen-lockup.svg";
  return <img src={src} alt="عاون — مع بعض نعاونوا" />;
}

export function OfflineBanner() {
  const online = useOnline();
  const { tr } = useI18n();
  const [queued, setQueued] = useState(0);
  const toast = useToast();
  useEffect(() => {
    const check = () => listDrafts().then((d) => setQueued(d.filter((x) => x.status === "queued" || x.status === "sending").length)).catch(() => {});
    check();
    const id = window.setInterval(check, 5000);
    return () => window.clearInterval(id);
  }, []);
  useEffect(() => {
    if (online) {
      flushOutbox().then((n) => {
        if (n > 0) toast(tr(`أُرسل ${n} بلاغ كان بانتظار الاتصال`, `${n} queued report(s) sent`));
      }).catch(() => {});
    }
  }, [online, toast, tr]);
  if (online && queued === 0) return null;
  return (
    <div className={`banner ${online ? "info" : "offline"}`} role="status" aria-live="polite">
      <Icon name={online ? "refresh" : "wifioff"} size={20} />
      <span>
        {!online && tr("أنت غير متصل. يمكنك كتابة بلاغ وسيُرسل تلقائيًا عند عودة الاتصال.", "You're offline. Reports you write will be sent when you reconnect.")}
        {online && queued > 0 && tr(`جارٍ إرسال ${queued} بلاغ محفوظ…`, `Sending ${queued} saved report(s)…`)}
      </span>
    </div>
  );
}

function useUnread() {
  const { me } = useAuth();
  const loc = useLocation();
  const [n, setN] = useState(0);
  useEffect(() => {
    if (!me) return setN(0);
    get<{ count: number }>("/notifications/unread/").then((r) => setN(r.count)).catch(() => {});
  }, [me, loc.pathname]);
  return n;
}

export function CitizenShell() {
  const { tr, lang, setLang } = useI18n();
  const { me, isStaff, hasRole } = useAuth();
  const unread = useUnread();
  const loc = useLocation();
  const fullBleed = loc.pathname.startsWith("/map");
  const tabs: [string, string, string, string][] = [
    ["/", "home", "حومتي", "My area"],
    ["/map", "map", "الخريطة", "Map"],
    ["/aawen", "hands", "عاون", "Help"],
    ["/contribute", "give", "ساهم", "Contribute"],
    ["/me", "me", "أثري", "My impact"],
  ];
  return (
    <div className="app citizen">
      <a className="skip-link" href="#main">{tr("انتقل إلى المحتوى", "Skip to content")}</a>
      <header className="topbar">
        <Link to="/" className="brand" aria-label={tr("عاون — الصفحة الرئيسية", "Aawen home")}><Logo /></Link>
        {(isStaff || hasRole("agency_staff")) && (
          <Link className="btn ghost small" to={hasRole("agency_staff") && !isStaff ? "/agency" : "/staff"}>
            {tr("لوحة العمل", "Workspace")}
          </Link>
        )}
        <button className="icon-btn" onClick={() => setLang(lang === "ar" ? "en" : "ar")} aria-label={tr("English", "العربية")}
          title={tr("English", "العربية")}><Icon name="globe" /></button>
        <Link className="icon-btn" to={me ? "/notifications" : "/login"} aria-label={tr(`الإشعارات${unread ? `: ${unread} جديدة` : ""}`, `Notifications${unread ? `: ${unread} new` : ""}`)}>
          <Icon name="bell" />{unread > 0 && <span className="dot">{unread > 9 ? "9+" : unread}</span>}
        </Link>
      </header>
      <nav className="tabbar" aria-label={tr("التبويبات الرئيسية", "Main tabs")}>
        {tabs.slice(0, 2).map(([to, icon, ar, en]) => (
          <NavLink key={to} to={to} end={to === "/"}><Icon name={icon} /><span>{tr(ar, en)}</span></NavLink>
        ))}
        <NavLink to="/report/new" className="report-fab" aria-label={tr("بلّغ عن مشكلة", "Report a problem")}>
          <Icon name="plus" /><span>{tr("بلّغ", "Report")}</span>
        </NavLink>
        {tabs.slice(2).map(([to, icon, ar, en]) => (
          <NavLink key={to} to={to}><Icon name={icon} /><span>{tr(ar, en)}</span></NavLink>
        ))}
      </nav>
      <div style={{ minWidth: 0 }}>
        <OfflineBanner />
        <main id="main" className={`content ${fullBleed ? "full" : ""}`} tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}

type NavItem = { to: string; ar: string; en: string; roles: string[] };
type NavGroup = { ar: string; en: string; items: NavItem[] };
const STAFF_NAV: NavGroup[] = [
  { ar: "البلاغات", en: "Reports", items: [
    { to: "/staff", ar: "نظرة عامة", en: "Overview", roles: ["reviewer", "coordinator", "sysadmin"] },
    { to: "/staff/queue", ar: "قوائم العمل", en: "Work queues", roles: ["reviewer", "coordinator"] },
    { to: "/staff/moderation", ar: "مراجعة الوسائط", en: "Media review", roles: ["reviewer", "coordinator"] },
    { to: "/staff/followups", ar: "المراجعات اللاحقة", en: "Follow-ups", roles: ["reviewer", "coordinator", "ambassador"] },
    { to: "/staff/bundles", ar: "حزم الحل", en: "Bundles", roles: ["coordinator"] },
  ] },
  { ar: "المشاركة", en: "Participation", items: [
    { to: "/staff/initiatives", ar: "المبادرات", en: "Initiatives", roles: ["coordinator"] },
    { to: "/staff/proposals", ar: "اقتراحات الحومة", en: "Proposals", roles: ["reviewer", "coordinator"] },
    { to: "/staff/coverage", ar: "تغطية المناطق", en: "Coverage", roles: ["coordinator", "sysadmin", "reviewer"] },
    { to: "/staff/directory", ar: "الدليل ونقاط العناية", en: "Directory & care points", roles: ["coordinator"] },
  ] },
  { ar: "المالية", en: "Finance", items: [
    { to: "/staff/finance", ar: "المساهمات والصرف", en: "Contributions & spending", roles: ["accountant", "financial_auditor"] },
  ] },
  { ar: "الإدارة", en: "Administration", items: [
    { to: "/staff/categories", ar: "الفئات", en: "Categories", roles: ["sysadmin", "coordinator"] },
    { to: "/staff/geo", ar: "المناطق والجهات والتوجيه", en: "Areas, agencies & routing", roles: ["sysadmin", "coordinator"] },
    { to: "/staff/users", ar: "المستخدمون والأدوار", en: "Users & roles", roles: ["sysadmin"] },
    { to: "/staff/settings", ar: "الإعدادات", en: "Settings", roles: ["sysadmin", "coordinator"] },
    { to: "/staff/audit", ar: "سجل التغييرات", en: "Audit log", roles: ["sysadmin", "financial_auditor"] },
  ] },
];

export function StaffShell({ kind = "staff" }: { kind?: "staff" | "agency" | "field" }) {
  const { tr } = useI18n();
  const { hasRole, logout, me } = useAuth();
  const nav = useNavigate();
  let groups: NavGroup[] = STAFF_NAV.map((g) => ({ ...g, items: g.items.filter((i) => hasRole(...i.roles)) }))
    .filter((g) => g.items.length);
  if (kind === "agency") groups = [{ ar: "بوابة الجهة", en: "Agency portal", items: [
    { to: "/agency", ar: "البلاغات المحالة", en: "Referred reports", roles: [] },
    { to: "/agency/announcements", ar: "تنبيهات الجهة", en: "Announcements", roles: [] },
    { to: "/field", ar: "المهام الميدانية", en: "Field tasks", roles: [] },
  ] }];
  if (kind === "field") groups = [{ ar: "الميدان", en: "Field", items: [
    { to: "/field", ar: "مهامي الميدانية", en: "My field tasks", roles: [] },
  ] }];
  return (
    <div className="app staff">
      <a className="skip-link" href="#main">{tr("انتقل إلى المحتوى", "Skip to content")}</a>
      <nav className="staff-nav" aria-label={tr("قائمة لوحة العمل", "Workspace navigation")}>
        <Link to="/" className="brand" aria-label={tr("الرجوع لواجهة المواطن", "Back to citizen app")} style={{ padding: "4px 8px 12px" }}>
          <Logo dark />
        </Link>
        {groups.map((g) => (
          <div key={g.ar} style={{ display: "contents" }}>
            <div className="group">{tr(g.ar, g.en)}</div>
            {g.items.map((i) => <NavLink key={i.to} to={i.to} end>{tr(i.ar, i.en)}</NavLink>)}
          </div>
        ))}
        <div style={{ marginTop: "auto" }} />
        <span className="group" style={{ display: "block" }}>{me?.display_name}</span>
        <a href="/" onClick={(e) => { e.preventDefault(); logout().then(() => nav("/")); }}>{tr("تسجيل الخروج", "Sign out")}</a>
      </nav>
      <div style={{ minWidth: 0 }}>
        <OfflineBanner />
        <main id="main" className="staff-main" tabIndex={-1}><Outlet /></main>
      </div>
    </div>
  );
}

export function PageHeader({ title, back, children }: { title: string; back?: string; children?: ReactNode }) {
  const nav = useNavigate();
  const { tr } = useI18n();
  return (
    <div className="row" style={{ marginBottom: 12, alignItems: "center" }}>
      {back !== undefined && (
        <button className="icon-btn" onClick={() => (back ? nav(back) : nav(-1))} aria-label={tr("رجوع", "Back")}>
          <Icon name="back" className="flip" />
        </button>
      )}
      <h1 style={{ margin: 0, flex: 1 }}>{title}</h1>
      {children}
    </div>
  );
}
