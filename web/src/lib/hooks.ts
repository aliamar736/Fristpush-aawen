import { useCallback, useEffect, useRef, useState } from "react";

import { getCached } from "../api/client";

export function useOnline() {
  const [online, setOnline] = useState(typeof navigator === "undefined" ? true : navigator.onLine);
  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, []);
  return online;
}

export type Load<T> = { data: T | null; error: unknown; loading: boolean; stale: boolean; savedAt: number | null;
  reload: () => void };

/** Data loader with offline cache fallback (shows how old cached data is). */
export function useLoad<T>(path: string | null, deps: unknown[] = []): Load<T> {
  const [state, setState] = useState<Omit<Load<T>, "reload">>({ data: null, error: null, loading: !!path, stale: false,
                                                                  savedAt: null });
  const seq = useRef(0);
  const run = useCallback(() => {
    if (!path) return;
    const n = ++seq.current;
    setState((s) => ({ ...s, loading: true, error: null }));
    getCached<T>(path)
      .then((r) => n === seq.current && setState({ data: r.data, error: null, loading: false, stale: r.stale, savedAt: r.savedAt }))
      .catch((e) => n === seq.current && setState((s) => ({ ...s, error: e, loading: false })));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, ...deps]);
  useEffect(run, [run]);
  return { ...state, reload: run };
}
