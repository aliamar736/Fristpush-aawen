import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { get, post } from "../../api/client";
import type { Area, Category, Paged, Report } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { CATEGORY_ICON, Icon } from "../../components/Icon";
import { MapView, TRIPOLI } from "../../components/MapView";
import { PageHeader } from "../../components/Shell";
import { DemoBadge, Field, Loading, StatusBadge, useToast } from "../../components/ui";
import { deleteDraft, loadDraft, newDraft, saveDraft, sendDraft, type Draft } from "../../lib/drafts";
import { toLocalInput } from "../../lib/format";
import { useLoad, useOnline } from "../../lib/hooks";
import { compressImage } from "../../lib/image";
import { useI18n } from "../../lib/i18n";

type Landmark = { id: number; name: string; kind: string; distance_m: number };
const SENSITIVE_LABELS: Record<string, [string, string]> = {
  phone_number: ["رقم هاتف", "a phone number"], national_id: ["رقم وطني", "a national ID"], email: ["بريد إلكتروني", "an email"],
  vehicle_plate: ["رقم لوحة سيارة", "a licence plate"], possible_injury: ["إشارة لمصابين", "a mention of injured people"],
  personal_name: ["اسم شخص", "a person's name"],
};

export default function ReportWizard() {
  const { tr, lang } = useI18n();
  const { me, config } = useAuth();
  const online = useOnline();
  const nav = useNavigate();
  const toast = useToast();
  const [sp] = useSearchParams();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [step, setStep] = useState(1);
  const [landmarks, setLandmarks] = useState<Landmark[]>([]);
  const [similar, setSimilar] = useState<Report[] | null>(null);
  const [aiHint, setAiHint] = useState<{ suggestion: { slug: string; category_id: number } | null; sensitive_flags: string[] } | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [sending, setSending] = useState(false);
  const [recording, setRecording] = useState(false);
  const recRef = useRef<MediaRecorder | null>(null);
  const [locMsg, setLocMsg] = useState("");
  const cats = useLoad<Paged<Category>>("/categories/?page_size=100");
  const areas = useLoad<Paged<Area>>("/areas/?geometry=1&page_size=200");
  const stepTitle = useRef<HTMLHeadingElement>(null);

  // Load or create the local draft (survives reloads, logins and lost connectivity)
  useEffect(() => {
    const id = sp.get("draft");
    (async () => {
      const d = (id && (await loadDraft(id))) || newDraft();
      setDraft(d);
      if (!id) nav(`/report/new?draft=${d.client_id}`, { replace: true });
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (draft && draft.status !== "sent") saveDraft(draft).catch(() => {});
  }, [draft]);
  useEffect(() => stepTitle.current?.focus(), [step]);

  const upd = (patch: Partial<Draft>) => setDraft((d) => (d ? { ...d, ...patch } : d));

  // Nearby landmarks for the chosen point
  useEffect(() => {
    if (draft?.lat == null || draft.lng == null || !online) return;
    const t = window.setTimeout(() => {
      get<Landmark[]>(`/landmarks/near/?lat=${draft.lat}&lng=${draft.lng}`).then(setLandmarks).catch(() => setLandmarks([]));
    }, 400);
    return () => window.clearTimeout(t);
  }, [draft?.lat, draft?.lng, online]);

  // AI assist (advisory): category hint + sensitive data warning; manual choice always works without it
  useEffect(() => {
    const text = draft?.description ?? "";
    if (text.trim().length < 6 || !online) return setAiHint(null);
    const t = window.setTimeout(() => {
      post<typeof aiHint>("/reports/suggest-category/", { text }).then(setAiHint).catch(() => setAiHint(null));
    }, 700);
    return () => window.clearTimeout(t);
  }, [draft?.description, online]);

  const locate = () => {
    setLocMsg("");
    if (!navigator.geolocation) return setLocMsg(tr("حدد الموقع على الخريطة.", "Pick the spot on the map."));
    navigator.geolocation.getCurrentPosition(
      (p) => upd({ lat: p.coords.latitude, lng: p.coords.longitude, location_edited: false }),
      () => setLocMsg(tr("لم نحصل على إذن الموقع. اضغط على الخريطة لتحديد مكان المشكلة.", "Location permission denied — tap the map instead.")),
      { enableHighAccuracy: true, timeout: 12000 },
    );
  };

  const addPhoto = async (files: FileList | null) => {
    if (!files || !draft) return;
    const imgs: Blob[] = [];
    for (const f of Array.from(files).slice(0, 4 - draft.photos.length)) imgs.push(await compressImage(f));
    upd({ photos: [...draft.photos, ...imgs], uploaded: [] });
  };

  const toggleRecord = async () => {
    if (recording) {
      recRef.current?.stop();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      const chunks: BlobPart[] = [];
      rec.ondataavailable = (e) => chunks.push(e.data);
      rec.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        upd({ audio: new Blob(chunks, { type: rec.mimeType || "audio/webm" }), uploaded: [] });
        setRecording(false);
      };
      rec.start();
      recRef.current = rec;
      setRecording(true);
      window.setTimeout(() => rec.state === "recording" && rec.stop(), 60000);
    } catch {
      toast(tr("لم نحصل على إذن الميكروفون. اكتب الوصف بدلًا من التسجيل.", "Microphone permission denied — type instead."));
    }
  };

  const validate = (s: number) => {
    const e: Record<string, string> = {};
    if (s === 1 && (draft?.lat == null || draft?.lng == null)) e.location = tr("حدد مكان المشكلة على الخريطة أو استخدم موقعك.", "Choose the location.");
    if (s === 2 && !draft?.category) e.category = tr("اختر نوع المشكلة.", "Choose a category.");
    if (s === 2 && !draft?.description.trim() && !draft?.photos.length && !draft?.audio) e.description = tr("اكتب وصفًا قصيرًا أو أرفق صورة أو تسجيلًا.", "Add a description, photo or voice note.");
    if (s === 3 && new Date(draft!.observed_at).getTime() > Date.now() + 5 * 60000) e.observed_at = tr("وقت الرصد لا يكون في المستقبل.", "Can't be in the future.");
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const next = async () => {
    if (!validate(step)) return;
    if (step === 3 && online && draft) {
      setSimilar(null);
      try {
        const r = await get<{ results: Report[] }>(`/reports/similar/?lat=${draft.lat}&lng=${draft.lng}&category=${draft.category}`);
        setSimilar(r.results);
      } catch {
        setSimilar([]);
      }
    }
    setStep((s) => s + 1);
  };

  const confirmExisting = async (id: number) => {
    if (!me) return nav(`/login?next=${encodeURIComponent(`/reports/${id}`)}`);
    try {
      await post(`/reports/${id}/confirm/`, {});
      if (draft) await deleteDraft(draft.client_id);
      toast(tr("شكرًا، أكدنا وجود المشكلة على البلاغ القائم.", "Thanks — you confirmed the existing report."));
      nav(`/reports/${id}`);
    } catch (e) {
      toast((e as Error).message);
    }
  };

  const submit = async () => {
    if (!draft) return;
    if (!me) {
      await saveDraft(draft);
      return nav(`/login?next=${encodeURIComponent(`/report/new?draft=${draft.client_id}&step=5`)}`);
    }
    setSending(true);
    const out = await sendDraft({ ...draft, status: "queued" });
    setDraft(out);
    setSending(false);
    if (out.status === "sent") {
      toast(tr(`وصل بلاغك. رقم المتابعة ${out.tracking_number}`, `Report received: ${out.tracking_number}`));
      await deleteDraft(out.client_id);
      nav(`/reports/${out.report_id}`, { replace: true });
    }
  };

  useEffect(() => {
    if (sp.get("step") === "5" && draft) setStep(5);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft?.client_id]);

  const photoUrls = useMemo(() => (draft?.photos ?? []).map((p) => URL.createObjectURL(p)), [draft?.photos]);
  useEffect(() => () => photoUrls.forEach(URL.revokeObjectURL), [photoUrls]);
  if (!draft) return <Loading />;
  const catList = cats.data?.results ?? [];
  const chosen = catList.find((c) => c.id === draft.category);
  const steps = [tr("المكان", "Where"), tr("المشكلة", "What"), tr("الوقت", "When"), tr("بلاغات قريبة", "Nearby"), tr("إرسال", "Send")];

  return (
    <div style={{ maxWidth: 720, margin: "0 auto" }}>
      <PageHeader title={tr("بلّغ عن مشكلة", "Report a problem")} back="/" />
      <div className="banner warn" role="note" style={{ marginBottom: 12 }}>
        <Icon name="alert" size={20} />
        <span>{lang === "en" ? config?.emergency_notice.en : config?.emergency_notice.ar ?? "بلاغ الخريطة لا يرسل إسعافًا."}
          {config?.emergency_notice.contacts.map((c) => <span key={c.phone}> {c.name}: <a href={`tel:${c.phone}`} dir="ltr">{c.phone}</a></span>)}</span>
      </div>
      <div className="steps" aria-label={tr("مراحل البلاغ", "Steps")}>
        <ol>{steps.map((st, i) => <li key={st} className={i + 1 < step ? "done" : i + 1 === step ? "now" : ""} aria-current={step === i + 1 ? "step" : undefined}><span className="sr-only">{st}</span></li>)}</ol>
        <span className="small muted">{tr(`الخطوة ${step} من ${steps.length}`, `Step ${step} of ${steps.length}`)}</span>
      </div>
      {!online && <div className="banner offline" style={{ borderRadius: 12, marginBottom: 12 }}>{tr("أنت غير متصل — المسودة محفوظة على جهازك وستُرسل عند عودة الاتصال.", "Offline — your draft is saved on this device.")}</div>}

      <section className="panel" aria-labelledby="step-title">
        <h2 id="step-title" tabIndex={-1} ref={stepTitle}>{steps[step - 1]}</h2>

        {step === 1 && (
          <>
            <p className="muted small">{tr("اضغط على الخريطة أو اسحب الدبوس الأصفر لمكان المشكلة بالضبط.", "Tap the map or drag the yellow pin to the exact spot.")}</p>
            <div className="mini-map" style={{ height: 320 }}>
              <MapView label={tr("اختيار موقع المشكلة", "Choose the problem location")} cluster={false}
                areas={(areas.data?.results ?? []).map((a) => ({ id: a.id, name: a.name_ar, geometry: a.geometry }))}
                center={draft.lat != null ? [draft.lat, draft.lng!] : TRIPOLI} zoom={draft.lat != null ? 16 : 13}
                picker={{ lat: draft.lat, lng: draft.lng, onChange: (lat, lng) => upd({ lat, lng, location_edited: true }) }} />
            </div>
            <div className="row" style={{ margin: "10px 0" }}>
              <button className="btn ghost small" onClick={locate}><Icon name="locate" size={18} />{tr("استخدم موقعي الحالي", "Use my location")}</button>
              {draft.lat != null && <span className="xs muted" dir="ltr">{draft.lat.toFixed(5)}, {draft.lng!.toFixed(5)}</span>}
            </div>
            {locMsg && <p className="err" role="alert">{locMsg}</p>}
            {errors.location && <p className="err" role="alert" style={{ color: "var(--danger)" }}>{errors.location}</p>}
            <Field id="lm" label={tr("معلم قريب", "Nearby landmark")} hint={tr("مثال: قدام مخبز النور، جنب الجامع", "e.g. in front of the bakery")}>
              <input id="lm" className="input" value={draft.landmark_text} onChange={(e) => upd({ landmark_text: e.target.value, landmark: null })} list="lm-list" />
            </Field>
            {landmarks.length > 0 && (
              <div className="chips" aria-label={tr("معالم مقترحة", "Suggested landmarks")}>
                {landmarks.map((l) => (
                  <button key={l.id} className="chip" aria-pressed={draft.landmark === l.id}
                    onClick={() => upd({ landmark: l.id, landmark_text: l.name })}>{l.name} <span className="xs muted">{l.distance_m}م</span></button>
                ))}
              </div>
            )}
          </>
        )}

        {step === 2 && (
          <>
            <div role="radiogroup" aria-label={tr("نوع المشكلة", "Problem type")} className="choice-grid">
              {catList.map((c) => (
                <button key={c.id} role="radio" aria-checked={draft.category === c.id} className="choice" onClick={() => upd({ category: c.id })}>
                  <Icon name={CATEGORY_ICON[c.slug] ?? c.icon} className="ico" />
                  <span style={{ fontWeight: 600 }}>{lang === "en" && c.name_en ? c.name_en : c.name_ar}</span>
                </button>
              ))}
            </div>
            {errors.category && <p className="err" role="alert" style={{ color: "var(--danger)" }}>{errors.category}</p>}
            <div style={{ height: 12 }} />
            <Field id="desc" label={tr("وصف المشكلة", "Description")} error={errors.description}
              hint={tr("اكتب ما تراه فقط. لا تكتب أسماء أو أرقام هواتف أو لوحات سيارات.", "Describe what you see. No names, phone numbers or plates.")}>
              <textarea id="desc" className="input" value={draft.description} maxLength={2000} onChange={(e) => upd({ description: e.target.value })} aria-describedby="desc-hint" />
            </Field>
            {aiHint?.suggestion && aiHint.suggestion.category_id !== draft.category && (
              <div className="banner info" role="status">
                <Icon name="star" size={20} />
                <span>{tr("يبدو أنها:", "Looks like:")} <b>{catList.find((c) => c.id === aiHint.suggestion!.category_id)?.name_ar}</b></span>
                <button className="btn small ghost" onClick={() => upd({ category: aiHint.suggestion!.category_id })}>{tr("اختر هذه الفئة", "Use this category")}</button>
              </div>
            )}
            {aiHint && aiHint.sensitive_flags.length > 0 && (
              <div className="banner warn" role="alert" style={{ marginTop: 8 }}>
                <Icon name="shield" size={20} />
                <span>{tr("يبدو أن الوصف يحتوي على", "Your text seems to contain")} {aiHint.sensitive_flags.map((f) => tr(...(SENSITIVE_LABELS[f] ?? [f, f]))).join("، ")}.
                  {" "}{tr("احذفها لحماية الخصوصية. سيحجبها فريق المراجعة على أي حال قبل النشر.", "Please remove it; reviewers will mask it before publishing anyway.")}</span>
              </div>
            )}
            <div className="field" style={{ marginTop: 12 }}>
              <span className="label">{tr("صورة (اختياري)", "Photo (optional)")}</span>
              <span className="hint">{tr("لا تصوّر وجوه الناس أو المصابين أو لوحات السيارات. الصور تُراجع قبل نشرها.", "Avoid faces, injured people and plates — photos are reviewed before publishing.")}</span>
              {photoUrls.length > 0 && (
                <div className="photo-grid">
                  {photoUrls.map((u, i) => (
                    <div key={u} style={{ position: "relative" }}>
                      <img src={u} alt={tr(`صورة ${i + 1}`, `Photo ${i + 1}`)} />
                      <button className="icon-btn" style={{ position: "absolute", top: 2, insetInlineEnd: 2, background: "var(--paper)" }}
                        aria-label={tr("حذف الصورة", "Remove photo")} onClick={() => upd({ photos: draft.photos.filter((_, j) => j !== i), uploaded: [] })}><Icon name="x" size={18} /></button>
                    </div>
                  ))}
                </div>
              )}
              {draft.photos.length < 4 && (
                <label className="btn ghost" style={{ alignSelf: "flex-start" }}>
                  <Icon name="camera" size={20} />{tr("التقط أو اختر صورة", "Take or choose a photo")}
                  <input type="file" accept="image/*" capture="environment" className="sr-only" onChange={(e) => addPhoto(e.target.files)} />
                </label>
              )}
            </div>
            <div className="field">
              <span className="label">{tr("تسجيل صوتي (اختياري)", "Voice note (optional)")}</span>
              <div className="row">
                <button className={`btn ${recording ? "danger" : "ghost"}`} onClick={toggleRecord} aria-pressed={recording}>
                  <Icon name="mic" size={20} />{recording ? tr("إيقاف التسجيل", "Stop recording") : tr("سجّل وصفًا بصوتك", "Record a voice note")}
                </button>
                {draft.audio && !recording && (
                  <>
                    <audio controls src={URL.createObjectURL(draft.audio)} aria-label={tr("التسجيل الصوتي", "Voice note")} />
                    <button className="btn small ghost" onClick={() => upd({ audio: null, uploaded: [] })}>{tr("حذف", "Delete")}</button>
                  </>
                )}
              </div>
            </div>
            <fieldset className="field" style={{ border: 0, padding: 0 }}>
              <legend className="label">{tr("هل تشكل خطرًا؟", "Is it dangerous?")}</legend>
              <div className="chips" role="radiogroup">
                {[[0, "لا خطر", "No danger"], [1, "إزعاج", "Nuisance"], [2, "خطر محتمل", "Possible danger"], [3, "خطر مباشر", "Immediate danger"]].map(([v, a, e]) => (
                  <button key={v} role="radio" className="chip" aria-checked={draft.danger_level === v} onClick={() => upd({ danger_level: v as number })}>{tr(a as string, e as string)}</button>
                ))}
              </div>
            </fieldset>
          </>
        )}

        {step === 3 && (
          <>
            <p className="muted small">{tr("متى شفت المشكلة؟ نسجل وقت الرصد منفصلًا عن وقت الإرسال.", "When did you see it? We record this separately from the sending time.")}</p>
            <div className="chips" style={{ marginBottom: 12 }}>
              <button className="chip" onClick={() => upd({ observed_at: new Date().toISOString() })}>{tr("الآن", "Now")}</button>
              <button className="chip" onClick={() => upd({ observed_at: new Date(Date.now() - 3600e3).toISOString() })}>{tr("قبل ساعة", "An hour ago")}</button>
              <button className="chip" onClick={() => { const d = new Date(); d.setHours(8, 0, 0, 0); upd({ observed_at: d.toISOString() }); }}>{tr("اليوم الصبح", "This morning")}</button>
              <button className="chip" onClick={() => upd({ observed_at: new Date(Date.now() - 86400e3).toISOString() })}>{tr("أمس", "Yesterday")}</button>
            </div>
            <Field id="obs" label={tr("وقت الرصد", "Observed at")} error={errors.observed_at}>
              <input id="obs" type="datetime-local" className="input" value={toLocalInput(new Date(draft.observed_at))}
                max={toLocalInput(new Date())} onChange={(e) => e.target.value && upd({ observed_at: new Date(e.target.value).toISOString() })} />
            </Field>
          </>
        )}

        {step === 4 && (
          <>
            {!online ? (
              <p className="muted">{tr("لا يمكن فحص البلاغات القريبة دون اتصال. سنرسل بلاغك وسيدمجه فريق المراجعة إن كان مكررًا.", "Can't check nearby reports offline; reviewers will merge duplicates.")}</p>
            ) : similar === null ? <Loading /> : similar.length === 0 ? (
              <div className="banner ok"><Icon name="check" size={20} />{tr("لا توجد بلاغات مشابهة قريبة. بلاغك جديد.", "No similar reports nearby.")}</div>
            ) : (
              <>
                <p>{tr("هذه بلاغات مشابهة قريبة من المكان. إن كانت نفس المشكلة، أكدها بدل إرسال بلاغ جديد — هذا يرفع أولويتها.",
                  "Similar nearby reports. If it's the same problem, confirm it instead of filing a duplicate.")}</p>
                <ul className="list">
                  {similar.map((r) => (
                    <li key={r.id} className="list-item">
                      <Icon name={CATEGORY_ICON[r.category.slug] ?? "pin"} />
                      <div className="grow">
                        <div className="row"><b>{r.category.name}</b><StatusBadge status={r.status} /><DemoBadge show={r.is_demo} /></div>
                        <div className="xs muted">{tr("على بعد", "")} {Math.round(r.distance_m ?? 0)} {tr("متر", "m away")} — {r.confirmations_count} {tr("تأكيد", "confirmations")}</div>
                        {r.description && <div className="small">{r.description}</div>}
                      </div>
                      <button className="btn small teal" onClick={() => confirmExisting(r.id)}>{tr("نفس المشكلة، أؤكدها", "Same problem — confirm")}</button>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </>
        )}

        {step === 5 && (
          <>
            <dl className="kv">
              <dt>{tr("الفئة", "Category")}</dt><dd>{chosen?.name_ar ?? "—"}</dd>
              <dt>{tr("المكان", "Location")}</dt><dd>{draft.landmark_text || (draft.lat != null ? `${draft.lat.toFixed(4)}, ${draft.lng!.toFixed(4)}` : "—")}</dd>
              <dt>{tr("وقت الرصد", "Observed")}</dt><dd>{new Date(draft.observed_at).toLocaleString(lang === "en" ? "en-GB" : "ar-LY")}</dd>
              <dt>{tr("المرفقات", "Attachments")}</dt><dd>{draft.photos.length} {tr("صورة", "photo(s)")}{draft.audio ? tr(" + تسجيل صوتي", " + voice") : ""}</dd>
            </dl>
            <p className="small muted" style={{ marginTop: 12 }}>{tr("هويتك لا تظهر للعامة. الوصف يُنشر بعد مراجعته وحجب أي بيانات شخصية.", "Your identity is never public. The description is published after review.")}</p>
            {draft.status === "queued" && <div className="banner warn" role="status">{tr("محفوظ وبانتظار الاتصال. سنرسله تلقائيًا — لن يتكرر حتى لو ضغطت مرة أخرى.", "Saved and waiting for connection — it won't be duplicated.")}</div>}
            {draft.status === "failed" && <div className="banner error" role="alert">{draft.error}</div>}
            {!me && <div className="banner info">{tr("ستحتاج لتأكيد رقم هاتفك مرة واحدة. مسودتك محفوظة.", "You'll verify your phone once. Your draft is kept.")}</div>}
          </>
        )}
      </section>

      <div className="row between" style={{ marginTop: 12 }}>
        {step > 1 ? <button className="btn ghost" onClick={() => setStep((s) => s - 1)}>{tr("السابق", "Back")}</button> : <Link className="btn ghost" to="/me?tab=drafts">{tr("مسوداتي", "My drafts")}</Link>}
        {step < 5 ? (
          <button className="btn" onClick={next}>{step === 4 && similar?.length ? tr("بلاغي مختلف، تابع", "Mine is different — continue") : tr("التالي", "Next")}</button>
        ) : (
          <button className="btn teal" onClick={submit} disabled={sending}>
            {sending ? tr("جارٍ الإرسال…", "Sending…") : !me ? tr("تأكيد الرقم والإرسال", "Verify & send") : online ? tr("أرسل البلاغ", "Send report") : tr("احفظ للإرسال لاحقًا", "Save to send later")}
          </button>
        )}
      </div>
    </div>
  );
}
