import { useEffect, useState, type ImgHTMLAttributes } from "react";

import { tokens } from "../api/client";

/** Private media (not yet approved) is served only with the staff member's token, which <img> cannot send.
 *  These helpers fetch with the Authorization header and display a local object URL. */
async function fetchBlobUrl(src: string): Promise<string | null> {
  const t = tokens.get();
  const r = await fetch(src, { headers: t ? { Authorization: `Bearer ${t.access}` } : {} });
  if (!r.ok) return null;
  return URL.createObjectURL(await r.blob());
}

export function AuthImg({ src, alt, ...rest }: { src: string; alt: string } & ImgHTMLAttributes<HTMLImageElement>) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    let made: string | null = null;
    fetchBlobUrl(src).then((u) => {
      made = u;
      if (!alive) return;
      if (u) setUrl(u);
      else setFailed(true);
    }).catch(() => alive && setFailed(true));
    return () => {
      alive = false;
      if (made) URL.revokeObjectURL(made);
    };
  }, [src]);
  if (failed) return <span className="xs muted">تعذر تحميل الملف</span>;
  if (!url) return <span className="skeleton" style={{ display: "block", width: "100%", aspectRatio: "4/3" }} aria-label="جارٍ التحميل" />;
  return <img src={url} alt={alt} {...rest} />;
}

export function AuthAudio({ src }: { src: string }) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => { fetchBlobUrl(src).then(setUrl).catch(() => {}); }, [src]);
  return url ? <audio controls src={url} style={{ width: "100%" }} /> : null;
}

export async function openAuthFile(src: string) {
  const u = await fetchBlobUrl(src);
  if (u) window.open(u, "_blank", "noopener");
}
