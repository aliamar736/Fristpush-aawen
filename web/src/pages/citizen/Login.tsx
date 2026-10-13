import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { fieldErrors, post } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { PageHeader } from "../../components/Shell";
import { Field } from "../../components/ui";
import { useI18n } from "../../lib/i18n";

type Tok = { access: string; refresh: string };

export default function Login() {
  const { tr } = useI18n();
  const { loginWithTokens } = useAuth();
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const next = sp.get("next") || "/";
  const [mode, setMode] = useState<"otp" | "password">("otp");
  const [step, setStep] = useState<"phone" | "code">("phone");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [devCode, setDevCode] = useState<string | null>(null);
  const [err, setErr] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const requestCode = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setErr({}); setMsg("");
    try {
      const r = await post<{ phone: string; dev_code?: string }>("/auth/otp/request", { phone });
      setPhone(r.phone);
      setDevCode(r.dev_code ?? null);
      setStep("code");
    } catch (ex) {
      setErr(fieldErrors(ex));
      setMsg((ex as Error).message);
    } finally { setBusy(false); }
  };
  const verify = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setErr({}); setMsg("");
    try {
      const r = await post<Tok>("/auth/otp/verify", { phone, code, display_name: name });
      await loginWithTokens(r);
      nav(next, { replace: true });
    } catch (ex) {
      setMsg((ex as Error).message);
    } finally { setBusy(false); }
  };
  const pwLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setMsg("");
    try {
      const r = await post<Tok>("/auth/login", { username: phone, password });
      await loginWithTokens(r);
      nav(next, { replace: true });
    } catch (ex) {
      setMsg((ex as Error).message);
    } finally { setBusy(false); }
  };

  return (
    <div style={{ maxWidth: 440, margin: "0 auto" }}>
      <PageHeader title={tr("الدخول إلى عاون", "Sign in to Aawen")} back="" />
      <p className="muted">{tr("التصفح متاح دون حساب. نحتاج رقم هاتفك فقط عند إرسال بلاغ أو حجز أو مساهمة، ولا يظهر رقمك لأحد.",
        "Browsing needs no account. We only ask for your phone when you report, book or contribute — it is never shown publicly.")}</p>
      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={mode === "otp"} onClick={() => setMode("otp")}>{tr("رمز عبر الهاتف", "Phone code")}</button>
        <button role="tab" aria-selected={mode === "password"} onClick={() => setMode("password")}>{tr("كلمة مرور (للفرق)", "Password (staff)")}</button>
      </div>
      {msg && <div className="banner error" role="alert" style={{ marginBottom: 12 }}>{msg}</div>}
      {mode === "otp" && step === "phone" && (
        <form onSubmit={requestCode} className="panel" noValidate>
          <Field id="phone" label={tr("رقم الهاتف", "Phone number")} hint={tr("مثال: 0912345678", "e.g. 0912345678")} error={err.phone}>
            <input id="phone" className="input" inputMode="tel" autoComplete="tel" dir="ltr" required value={phone}
              onChange={(e) => setPhone(e.target.value)} aria-invalid={!!err.phone} aria-describedby="phone-hint" />
          </Field>
          <button className="btn block" disabled={busy || !phone}>{busy ? tr("جارٍ الإرسال…", "Sending…") : tr("أرسل رمز الدخول", "Send code")}</button>
        </form>
      )}
      {mode === "otp" && step === "code" && (
        <form onSubmit={verify} className="panel" noValidate>
          <p>{tr("أرسلنا رمزًا من 6 أرقام إلى", "We sent a 6-digit code to")} <bdi dir="ltr">{phone}</bdi></p>
          {devCode && (
            <div className="banner warn" role="note" style={{ marginBottom: 12 }}>
              {tr("بيئة تطوير: الرسائل النصية تعمل بمحاكي، والرمز هو", "Development: SMS is simulated, the code is")} <b dir="ltr">{devCode}</b>
            </div>
          )}
          <Field id="code" label={tr("رمز الدخول", "Code")}>
            <input id="code" className="input" inputMode="numeric" autoComplete="one-time-code" dir="ltr" maxLength={6}
              value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} required />
          </Field>
          <Field id="name" label={tr("اسمك كما يظهر للفرق (اختياري)", "Your name (optional)")}
            hint={tr("لا يظهر اسمك على البلاغات العامة.", "Your name is never shown on public reports.")}>
            <input id="name" className="input" value={name} onChange={(e) => setName(e.target.value)} autoComplete="nickname" />
          </Field>
          <button className="btn block" disabled={busy || code.length !== 6}>{tr("دخول", "Sign in")}</button>
          <button type="button" className="btn ghost block" style={{ marginTop: 8 }} onClick={() => setStep("phone")}>{tr("تغيير الرقم", "Change number")}</button>
        </form>
      )}
      {mode === "password" && (
        <form onSubmit={pwLogin} className="panel">
          <Field id="u" label={tr("رقم الهاتف أو اسم المستخدم", "Phone or username")}>
            <input id="u" className="input" dir="ltr" value={phone} onChange={(e) => setPhone(e.target.value)} autoComplete="username" required />
          </Field>
          <Field id="p" label={tr("كلمة المرور", "Password")}>
            <input id="p" type="password" className="input" dir="ltr" value={password} onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password" required />
          </Field>
          <button className="btn block" disabled={busy}>{tr("دخول", "Sign in")}</button>
        </form>
      )}
    </div>
  );
}
