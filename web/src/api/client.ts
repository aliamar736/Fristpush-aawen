/** API client: JWT with silent refresh, Arabic error mapping, offline detection and an
 *  offline read cache (IndexedDB) that remembers when data was saved. */
import { get as idbGet, set as idbSet } from "idb-keyval";

export const API_BASE = "/api/v1";

export class ApiError extends Error {
  status: number;
  code: string;
  fields?: Record<string, unknown>;
  constructor(status: number, code: string, message: string, fields?: Record<string, unknown>) {
    super(message);
    this.status = status;
    this.code = code;
    this.fields = fields;
  }
}

export class OfflineError extends Error {
  constructor() {
    super("لا يوجد اتصال بالإنترنت.");
  }
}

type Tokens = { access: string; refresh: string };
const TOKEN_KEY = "aawen.tokens";
let listeners: Array<() => void> = [];

export const tokens = {
  get(): Tokens | null {
    try {
      const raw = localStorage.getItem(TOKEN_KEY);
      return raw ? (JSON.parse(raw) as Tokens) : null;
    } catch {
      return null;
    }
  },
  set(t: Tokens | null) {
    try {
      if (t) localStorage.setItem(TOKEN_KEY, JSON.stringify(t));
      else localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* ignore */
    }
    listeners.forEach((l) => l());
  },
  subscribe(fn: () => void) {
    listeners.push(fn);
    return () => {
      listeners = listeners.filter((l) => l !== fn);
    };
  },
};

let refreshing: Promise<boolean> | null = null;
async function refreshAccess(): Promise<boolean> {
  const t = tokens.get();
  if (!t?.refresh) return false;
  refreshing ??= (async () => {
    try {
      const r = await fetch(`${API_BASE}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh: t.refresh }),
      });
      if (!r.ok) {
        tokens.set(null);
        return false;
      }
      const data = await r.json();
      tokens.set({ access: data.access, refresh: data.refresh ?? t.refresh });
      return true;
    } catch {
      return false;
    } finally {
      setTimeout(() => (refreshing = null), 0);
    }
  })();
  return refreshing;
}

export type RequestOpts = { idempotencyKey?: string; signal?: AbortSignal; raw?: boolean };

export async function api<T = unknown>(method: string, path: string, body?: unknown, opts: RequestOpts = {}): Promise<T> {
  const doFetch = async () => {
    const headers: Record<string, string> = { Accept: "application/json",
      "Accept-Language": document.documentElement.lang || "ar" };
    const t = tokens.get();
    if (t?.access) headers.Authorization = `Bearer ${t.access}`;
    if (opts.idempotencyKey) headers["Idempotency-Key"] = opts.idempotencyKey;
    let payload: BodyInit | undefined;
    if (body instanceof FormData) payload = body;
    else if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(body);
    }
    return fetch(API_BASE + path, { method, headers, body: payload, signal: opts.signal });
  };
  let res: Response;
  try {
    res = await doFetch();
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new OfflineError();
  }
  if (res.status === 401 && tokens.get()?.refresh) {
    if (await refreshAccess()) res = await doFetch();
  }
  if (opts.raw) return res as unknown as T;
  if (res.status === 204) return undefined as T;
  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const err = (data as { error?: { code: string; message: string; fields?: Record<string, unknown> } })?.error;
    const msg = err?.message ?? (res.status >= 500 ? "حدث خطأ في الخادم. حاول بعد قليل." : "تعذر تنفيذ الطلب.");
    throw new ApiError(res.status, err?.code ?? String(res.status), msg, err?.fields);
  }
  return data as T;
}

export const get = <T,>(p: string, o?: RequestOpts) => api<T>("GET", p, undefined, o);
export const post = <T,>(p: string, b?: unknown, o?: RequestOpts) => api<T>("POST", p, b ?? {}, o);
export const patch = <T,>(p: string, b?: unknown) => api<T>("PATCH", p, b);
export const put = <T,>(p: string, b?: unknown) => api<T>("PUT", p, b);
export const del = <T,>(p: string, b?: unknown) => api<T>("DELETE", p, b);

/** GET with an offline fallback: returns cached data with its age when the network is unavailable. */
export async function getCached<T>(path: string): Promise<{ data: T; savedAt: number; stale: boolean }> {
  const key = `cache:${path}`;
  try {
    const data = await get<T>(path);
    idbSet(key, { data, savedAt: Date.now() }).catch(() => {});
    return { data, savedAt: Date.now(), stale: false };
  } catch (e) {
    if (e instanceof OfflineError) {
      const hit = (await idbGet(key).catch(() => undefined)) as { data: T; savedAt: number } | undefined;
      if (hit) return { ...hit, stale: true };
    }
    throw e;
  }
}

export function fieldErrors(e: unknown): Record<string, string> {
  if (!(e instanceof ApiError) || !e.fields) return {};
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(e.fields)) out[k] = Array.isArray(v) ? String(v[0]) : String(v);
  return out;
}

export async function uploadMedia(file: Blob, kind: "image" | "audio" | "document", context = ""): Promise<string> {
  const fd = new FormData();
  const ext = kind === "audio" ? (file.type.includes("ogg") ? "ogg" : file.type.includes("mp4") ? "m4a" : "webm") : "jpg";
  fd.append("file", file, `upload.${ext}`);
  fd.append("kind", kind);
  if (context) fd.append("context", context);
  const r = await api<{ uid: string }>("POST", "/media/", fd);
  return r.uid;
}
