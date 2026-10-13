/** Local drafts & outbox for reports (IndexedDB).
 *  - drafts survive reloads and lost connectivity;
 *  - photos are compressed before storage; uploaded media ids are remembered so retries never re-upload;
 *  - the report POST carries a stable client_id, so the server returns the same report on every retry. */
import { createStore, del, entries, get, set, type UseStore } from "idb-keyval";

import { ApiError, OfflineError, post, uploadMedia } from "../api/client";
import type { Report } from "../api/types";
import { uuid } from "./format";

export type DraftStatus = "draft" | "queued" | "sending" | "failed" | "sent";
export type Draft = {
  client_id: string;
  status: DraftStatus;
  category?: number;
  description: string;
  lat?: number;
  lng?: number;
  location_edited: boolean;
  landmark?: number | null;
  landmark_text: string;
  observed_at: string; // ISO
  danger_level: number;
  photos: Blob[];
  audio?: Blob | null;
  uploaded: string[]; // media uids already uploaded (photos then audio)
  updated_at: number;
  error?: string;
  report_id?: number;
  tracking_number?: string;
};

let store: UseStore | null = null;
const db = () => (store ??= createStore("aawen-drafts", "drafts"));

export function newDraft(): Draft {
  return { client_id: uuid(), status: "draft", description: "", location_edited: false, landmark_text: "",
           observed_at: new Date().toISOString(), danger_level: 1, photos: [], audio: null, uploaded: [],
           updated_at: Date.now() };
}

/* Blobs are stored as {type, buf} because some browsers (older iOS Safari) cannot persist Blobs in IndexedDB. */
type StoredBlob = { type: string; buf: ArrayBuffer };
type StoredDraft = Omit<Draft, "photos" | "audio"> & { photos: StoredBlob[]; audio: StoredBlob | null };
async function toStored(b: Blob): Promise<StoredBlob> {
  const buf = typeof b.arrayBuffer === "function" ? await b.arrayBuffer()
    : await new Response(b).arrayBuffer();
  return { type: b.type, buf };
}
const fromStored = (s: StoredBlob) => new Blob([s.buf], { type: s.type });
function revive(s: StoredDraft | undefined): Draft | undefined {
  if (!s) return undefined;
  return { ...s, photos: (s.photos ?? []).map(fromStored), audio: s.audio ? fromStored(s.audio) : null };
}

export async function saveDraft(d: Draft) {
  const stored: StoredDraft = { ...d, updated_at: Date.now(), photos: await Promise.all(d.photos.map(toStored)),
                                audio: d.audio ? await toStored(d.audio) : null };
  await set(d.client_id, stored, db());
}
export const loadDraft = async (id: string) => revive(await get<StoredDraft>(id, db()));
export const deleteDraft = (id: string) => del(id, db());
export async function listDrafts(): Promise<Draft[]> {
  const all = (await entries<string, StoredDraft>(db())).map(([, v]) => revive(v)!);
  return all.sort((a, b) => b.updated_at - a.updated_at);
}

/** Try to send one draft. Network failures keep it queued; validation errors mark it failed. */
export async function sendDraft(d: Draft): Promise<Draft> {
  d = { ...d, status: "sending", error: undefined };
  await saveDraft(d);
  try {
    const blobs: [Blob, "image" | "audio"][] = [...d.photos.map((p) => [p, "image"] as [Blob, "image"]),
      ...(d.audio ? [[d.audio, "audio"] as [Blob, "audio"]] : [])];
    for (let i = d.uploaded.length; i < blobs.length; i++) {
      const [blob, kind] = blobs[i];
      const uid = await uploadMedia(blob, kind);
      d = { ...d, uploaded: [...d.uploaded, uid] };
      await saveDraft(d); // remember progress: never re-upload after reconnecting
    }
    const r = await post<Report>("/reports/", {
      client_id: d.client_id, category: d.category, description: d.description, lat: d.lat, lng: d.lng,
      location_edited: d.location_edited, landmark: d.landmark ?? null, landmark_text: d.landmark_text,
      observed_at: d.observed_at, danger_level: d.danger_level, media: d.uploaded,
    }, { idempotencyKey: d.client_id });
    d = { ...d, status: "sent", report_id: r.id, tracking_number: r.tracking_number ?? undefined, photos: [], audio: null };
    await saveDraft(d);
    return d;
  } catch (e) {
    if (e instanceof OfflineError || (e instanceof ApiError && (e.status >= 500 || e.status === 429))) {
      d = { ...d, status: "queued", error: e instanceof OfflineError ? "بانتظار الاتصال" : e.message };
    } else {
      d = { ...d, status: "failed", error: (e as Error).message };
    }
    await saveDraft(d);
    return d;
  }
}

let flushing = false;
export async function flushOutbox(): Promise<number> {
  if (flushing || !navigator.onLine) return 0;
  flushing = true;
  let sent = 0;
  try {
    for (const d of await listDrafts()) {
      if (d.status === "queued" || d.status === "sending") {
        const out = await sendDraft(d);
        if (out.status === "sent") sent++;
        else if (out.status === "queued") break; // still offline
      }
    }
  } finally {
    flushing = false;
  }
  return sent;
}
