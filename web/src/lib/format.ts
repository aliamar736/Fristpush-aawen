const rtf = (lang: string) => new Intl.RelativeTimeFormat(lang === "en" ? "en" : "ar-LY", { numeric: "auto" });

export function timeAgo(iso?: string | null, lang = "ar"): string {
  if (!iso) return "";
  const diff = (new Date(iso).getTime() - Date.now()) / 1000;
  const abs = Math.abs(diff);
  const f = rtf(lang);
  if (abs < 60) return f.format(Math.round(diff), "second");
  if (abs < 3600) return f.format(Math.round(diff / 60), "minute");
  if (abs < 86400) return f.format(Math.round(diff / 3600), "hour");
  if (abs < 86400 * 30) return f.format(Math.round(diff / 86400), "day");
  return formatDate(iso, lang);
}

export function formatDate(iso?: string | null, lang = "ar", withTime = false): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat(lang === "en" ? "en-GB" : "ar-LY", {
    day: "numeric", month: "long", year: "numeric", ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  }).format(new Date(iso));
}

export function money(v: string | number | null | undefined, lang = "ar"): string {
  const n = Number(v ?? 0);
  return new Intl.NumberFormat(lang === "en" ? "en" : "ar-LY", { minimumFractionDigits: 0, maximumFractionDigits: 2 })
    .format(n) + (lang === "en" ? " LYD" : " د.ل");
}

export function num(v: number, lang = "ar") {
  return new Intl.NumberFormat(lang === "en" ? "en" : "ar-LY").format(v);
}

export function toLocalInput(d: Date) {
  const p = (x: number) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

export function uuid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}
