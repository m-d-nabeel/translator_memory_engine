import { useState, useEffect, useCallback } from "react";

export type ReaderTheme = "dark" | "oled" | "light" | "sepia" | "cyber";
export type ReaderFont = "sans" | "serif" | "outfit" | "mono";
export type ReaderLineHeight = 1.5 | 1.8 | 2.2;
export type ReaderParaMode = "indent" | "block";
export type ReaderWidth = "compact" | "normal" | "full";

export interface ReaderSettings {
  theme: ReaderTheme;
  font: ReaderFont;
  fontSize: number;
  lineHeight: ReaderLineHeight;
  paraMode: ReaderParaMode;
  maxWidth: ReaderWidth;
}

const STORAGE_KEY = "tme-reader-settings-v2";

const defaults: ReaderSettings = {
  theme: "dark",
  font: "sans",
  fontSize: 18,
  lineHeight: 1.8,
  paraMode: "indent",
  maxWidth: "normal",
};

function load(): ReaderSettings {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) return { ...defaults, ...JSON.parse(stored) };
  } catch {
    /* ignore */
  }
  return defaults;
}

export function useReaderSettings() {
  const [settings, setSettings] = useState<ReaderSettings>(load);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", settings.theme);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  }, [settings]);

  const setTheme = useCallback((theme: ReaderTheme) => {
    setSettings((s) => ({ ...s, theme }));
  }, []);

  const setFont = useCallback((font: ReaderFont) => {
    setSettings((s) => ({ ...s, font }));
  }, []);

  const setFontSize = useCallback((fontSize: number) => {
    setSettings((s) => ({
      ...s,
      fontSize: Math.max(14, Math.min(30, fontSize)),
    }));
  }, []);

  const setLineHeight = useCallback((lineHeight: ReaderLineHeight) => {
    setSettings((s) => ({ ...s, lineHeight }));
  }, []);

  const setParaMode = useCallback((paraMode: ReaderParaMode) => {
    setSettings((s) => ({ ...s, paraMode }));
  }, []);

  const setMaxWidth = useCallback((maxWidth: ReaderWidth) => {
    setSettings((s) => ({ ...s, maxWidth }));
  }, []);

  const increaseFontSize = useCallback(() => {
    setSettings((s) => ({ ...s, fontSize: Math.min(s.fontSize + 2, 30) }));
  }, []);

  const decreaseFontSize = useCallback(() => {
    setSettings((s) => ({ ...s, fontSize: Math.max(s.fontSize - 2, 14) }));
  }, []);

  return {
    ...settings,
    setTheme,
    setFont,
    setFontSize,
    setLineHeight,
    setParaMode,
    setMaxWidth,
    increaseFontSize,
    decreaseFontSize,
  };
}
