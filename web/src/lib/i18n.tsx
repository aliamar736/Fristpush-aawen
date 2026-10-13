import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

export type Lang = "ar" | "en";
type Ctx = { lang: Lang; setLang: (l: Lang) => void; tr: (ar: string, en?: string) => string };
const I18n = createContext<Ctx>({ lang: "ar", setLang: () => {}, tr: (a) => a });

function readLang(): Lang {
  try {
    return (localStorage.getItem("aawen.lang") as Lang) || "ar";
  } catch {
    return "ar";
  }
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(readLang);
  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  }, [lang]);
  const setLang = (l: Lang) => {
    setLangState(l);
    try {
      localStorage.setItem("aawen.lang", l);
    } catch {
      /* storage unavailable */
    }
  };
  // Arabic is the source language; English is shown when provided, otherwise Arabic falls through.
  const tr = (ar: string, en?: string) => (lang === "en" && en ? en : ar);
  return <I18n.Provider value={{ lang, setLang, tr }}>{children}</I18n.Provider>;
}

export const useI18n = () => useContext(I18n);
