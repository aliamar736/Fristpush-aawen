import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";

import { ApiError, OfflineError } from "../api/client";
import { timeAgo } from "../lib/format";
import { useI18n } from "../lib/i18n";
import { Icon } from "./Icon";

/* ---------- status ---------- */
const STATUS_TONE: Record<string, string> = {
  draft: "s-new", submitted: "s-new", under_review: "s-new", needs_info: "s-wait", verified: "s-work", referred: "s-work",
  acknowledged: "s-work", in_progress: "s-work", waiting_resource: "s-wait", done_pending_verification: "s-wait",
  resolved: "s-done", disputed: "s-bad", reopened: "s-bad", unresolvable: "s-bad",
  active: "s-work", expired: "s-new", cleared: "s-done", historical: "s-new",
  pledged: "s-new", awaiting_payment: "s-wait", paid: "s-done", cancelled: "s-new", refunded: "s-new", failed: "s-bad",
  succeeded: "s-done", initiated: "s-wait", needs_review: "s-bad",
  reserved: "s-wait", picked_up: "s-work", returned: "s-done", overdue: "s-bad", booked: "s-work", attended: "s-work",
  completed: "s-done", no_show: "s-bad", approved: "s-done", pending_approval: "s-wait", requested: "s-wait",
  rejected: "s-bad", pending_review: "s-wait", eligible: "s-done", open: "s-work", met: "s-done", partial: "s-wait",
};
export const STATUS_LABEL: Record<string, [string, string]> = {
  draft: ["مسودة", "Draft"], submitted: ["مقدّم", "Submitted"], under_review: ["تحت المراجعة", "Under review"],
  needs_info: ["يحتاج معلومات", "Needs info"], verified: ["موثّق", "Verified"], referred: ["محال للجهة", "Referred"],
  acknowledged: ["استلام مؤكد", "Acknowledged"], in_progress: ["قيد التنفيذ", "In progress"],
  waiting_resource: ["بانتظار مورد أو تصريح", "Waiting for resource/permit"],
  done_pending_verification: ["إنجاز بانتظار التحقق", "Done, awaiting verification"], resolved: ["محلول", "Resolved"],
  disputed: ["معترض عليه", "Disputed"], reopened: ["معاد فتحه", "Reopened"], unresolvable: ["تعذّر الحل", "Could not be resolved"],
};

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const { tr } = useI18n();
  const l = STATUS_LABEL[status];
  return <span className={`badge ${STATUS_TONE[status] ?? ""}`}>{label ?? (l ? tr(l[0], l[1]) : status)}</span>;
}

export function DemoBadge({ show }: { show?: boolean }) {
  const { tr } = useI18n();
  return show ? <span className="badge demo" title={tr("بيانات عرض وتدريب، ليست بلاغًا حقيقيًا", "Demo data")}>{tr("تجريبي", "Demo")}</span> : null;
}

/* ---------- loading / empty / error ---------- */
export function Loading({ lines = 3, label }: { lines?: number; label?: string }) {
  const { tr } = useI18n();
  return (
    <div role="status" aria-live="polite" className="stack" style={{ padding: "8px 0" }}>
      <span className="sr-only">{label ?? tr("جارٍ التحميل…", "Loading…")}</span>
      {Array.from({ length: lines }).map((_, i) => <div key={i} className="skeleton" style={{ height: 18, width: `${90 - i * 12}%` }} />)}
    </div>
  );
}

export function EmptyState({ icon = "box", title, children, action }: { icon?: string; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="state">
      <Icon name={icon} />
      <h2>{title}</h2>
      {children && <p className="muted">{children}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { tr } = useI18n();
  const loc = useLocation();
  if (error instanceof OfflineError) {
    return (
      <div className="state error" role="alert">
        <Icon name="wifioff" />
        <h2>{tr("لا يوجد اتصال", "You are offline")}</h2>
        <p className="muted">{tr("لم نتمكن من تحميل هذه الصفحة ولا توجد نسخة محفوظة منها على جهازك.", "This page isn't saved on your device yet.")}</p>
        {onRetry && <button className="btn ghost" onClick={onRetry}>{tr("حاول مرة أخرى", "Try again")}</button>}
      </div>
    );
  }
  if (error instanceof ApiError && error.status === 401) {
    return (
      <div className="state error" role="alert">
        <Icon name="lock" />
        <h2>{tr("سجّل الدخول للمتابعة", "Sign in to continue")}</h2>
        <Link className="btn" to={`/login?next=${encodeURIComponent(loc.pathname)}`}>{tr("تسجيل الدخول", "Sign in")}</Link>
      </div>
    );
  }
  if (error instanceof ApiError && error.status === 403) {
    return (
      <div className="state error" role="alert">
        <Icon name="shield" />
        <h2>{tr("ليس لديك صلاحية لهذه الصفحة", "You don't have access to this page")}</h2>
        <p className="muted">{tr("إذا كنت تعمل مع جهة أو فريق عاون، اطلب من مدير النظام منحك الدور المناسب.", "Ask a system administrator for the right role.")}</p>
      </div>
    );
  }
  if (error instanceof ApiError && error.status === 404) {
    return <EmptyState icon="search" title={tr("غير موجود", "Not found")}>{tr("ربما حُذف أو أن الرابط غير صحيح.", "It may have been removed.")}</EmptyState>;
  }
  return (
    <div className="state error" role="alert">
      <Icon name="alert" />
      <h2>{tr("تعذر التحميل", "Couldn't load")}</h2>
      <p className="muted">{(error as Error)?.message}</p>
      {onRetry && <button className="btn ghost" onClick={onRetry}>{tr("حاول مرة أخرى", "Try again")}</button>}
    </div>
  );
}

export function StaleNote({ stale, savedAt }: { stale: boolean; savedAt: number | null }) {
  const { tr, lang } = useI18n();
  if (!stale || !savedAt) return null;
  return (
    <div className="banner warn" role="status">
      <Icon name="clock" size={20} />
      <span>{tr("أنت تشاهد نسخة محفوظة على جهازك من", "Showing data saved")} {timeAgo(new Date(savedAt).toISOString(), lang)}.
        {" "}{tr("قد لا تكون محدّثة.", "It may be out of date.")}</span>
    </div>
  );
}

export function Field({ label, hint, error, children, id }: { label: string; hint?: string; error?: string; children: ReactNode; id: string }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children}
      {hint && <span className="hint" id={`${id}-hint`}>{hint}</span>}
      {error && <span className="err" id={`${id}-err`} role="alert">{error}</span>}
    </div>
  );
}

export function Dialog({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    ref.current?.querySelector<HTMLElement>("input,textarea,select,button")?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      prev?.focus();
    };
  }, [onClose]);
  return (
    <div className="dialog-backdrop" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="dlg-title" ref={ref}>
        <div className="row between" style={{ marginBottom: 8 }}>
          <h2 id="dlg-title" style={{ margin: 0 }}>{title}</h2>
          <button className="icon-btn" onClick={onClose} aria-label="إغلاق"><Icon name="x" /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

/* ---------- toast ---------- */
const ToastCtx = createContext<(msg: string) => void>(() => {});
export function ToastProvider({ children }: { children: ReactNode }) {
  const [msg, setMsg] = useState<string | null>(null);
  const show = useCallback((m: string) => {
    setMsg(m);
    window.setTimeout(() => setMsg(null), 4000);
  }, []);
  return (
    <ToastCtx.Provider value={show}>
      {children}
      <div aria-live="polite" role="status">{msg && <div className="toast">{msg}</div>}</div>
    </ToastCtx.Provider>
  );
}
export const useToast = () => useContext(ToastCtx);

/** Runs an async action, surfaces API errors as a toast, returns the result or undefined. */
export function useAction() {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const run = async <T,>(fn: () => Promise<T>, okMsg?: string): Promise<T | undefined> => {
    setBusy(true);
    try {
      const r = await fn();
      if (okMsg) toast(okMsg);
      return r;
    } catch (e) {
      toast(e instanceof Error ? e.message : "تعذر التنفيذ");
      return undefined;
    } finally {
      setBusy(false);
    }
  };
  return { busy, run };
}
