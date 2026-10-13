import { beforeEach, describe, expect, it, vi } from "vitest";

import { flushOutbox, listDrafts, newDraft, saveDraft, sendDraft } from "./drafts";

type Call = { url: string; body: unknown; headers: Record<string, string> };

function mockServer(opts: { offlineUntil?: number } = {}) {
  const calls: Call[] = [];
  const reports = new Map<string, number>();
  let n = 0;
  const fetchMock = vi.fn(async (url: string, init: RequestInit) => {
    n++;
    if (opts.offlineUntil && n <= opts.offlineUntil) throw new TypeError("Failed to fetch");
    const headers = (init.headers ?? {}) as Record<string, string>;
    const body = init.body instanceof FormData ? "form" : init.body ? JSON.parse(String(init.body)) : null;
    calls.push({ url, body, headers });
    if (url.endsWith("/media/")) return new Response(JSON.stringify({ uid: `m${calls.length}` }), { status: 201 });
    if (url.endsWith("/reports/")) {
      const cid = (body as { client_id: string }).client_id;
      if (!reports.has(cid)) reports.set(cid, reports.size + 1); // server-side idempotency by client_id
      return new Response(JSON.stringify({ id: reports.get(cid), tracking_number: `AW-2026-00000${reports.get(cid)}` }), { status: 201 });
    }
    return new Response("{}", { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, reports };
}

describe("offline drafts & outbox", () => {
  beforeEach(async () => {
    vi.unstubAllGlobals();
    for (const d of await listDrafts()) {
      const { deleteDraft } = await import("./drafts");
      await deleteDraft(d.client_id);
    }
  });

  it("keeps the draft queued while offline and sends it exactly once when back online", async () => {
    const d = { ...newDraft(), category: 1, lat: 32.88, lng: 13.19, description: "حفرة", photos: [new Blob(["x"], { type: "image/jpeg" })] };
    await saveDraft(d);
    mockServer({ offlineUntil: 1 });
    const first = await sendDraft({ ...d, status: "queued" });
    expect(first.status).toBe("queued");
    expect(first.error).toContain("الاتصال");

    const srv = mockServer();
    Object.defineProperty(navigator, "onLine", { value: true, configurable: true });
    expect(await flushOutbox()).toBe(1);
    expect(await flushOutbox()).toBe(0); // nothing left to send
    const reportPosts = srv.calls.filter((c) => c.url.endsWith("/reports/"));
    expect(reportPosts).toHaveLength(1);
    expect(reportPosts[0].headers["Idempotency-Key"]).toBe(d.client_id);
    expect((reportPosts[0].body as { client_id: string }).client_id).toBe(d.client_id);
    const [saved] = await listDrafts();
    expect(saved.status).toBe("sent");
    expect(saved.tracking_number).toBe("AW-2026-000001");
  });

  it("does not re-upload photos that were uploaded before the connection dropped", async () => {
    const d = { ...newDraft(), category: 1, lat: 1, lng: 1, photos: [new Blob(["a"]), new Blob(["b"])] };
    // first photo uploads, then the connection drops on the second
    let n = 0;
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      n++;
      if (n === 1 && url.endsWith("/media/")) return new Response(JSON.stringify({ uid: "u1" }), { status: 201 });
      throw new TypeError("network");
    }));
    const out = await sendDraft(d);
    expect(out.status).toBe("queued");
    expect(out.uploaded).toEqual(["u1"]);
    const srv = mockServer();
    const done = await sendDraft(out);
    expect(done.status).toBe("sent");
    expect(srv.calls.filter((c) => c.url.endsWith("/media/"))).toHaveLength(1); // only the missing photo
    const post = srv.calls.find((c) => c.url.endsWith("/reports/"))!;
    expect((post.body as { media: string[] }).media).toEqual(["u1", "m1"]);
  });

  it("retrying the same draft twice never creates two reports", async () => {
    const d = { ...newDraft(), category: 1, lat: 1, lng: 1 };
    const srv = mockServer();
    await sendDraft(d);
    await sendDraft(d); // e.g. the user tapped send again after a timeout
    expect(srv.reports.size).toBe(1);
  });

  it("marks validation errors as failed (not retried forever)", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ error: { code: "validation_error", message: "بعض البيانات غير صحيحة." } }), { status: 400 })));
    const out = await sendDraft({ ...newDraft(), category: 1, lat: 1, lng: 1 });
    expect(out.status).toBe("failed");
    expect(out.error).toBe("بعض البيانات غير صحيحة.");
  });
});
