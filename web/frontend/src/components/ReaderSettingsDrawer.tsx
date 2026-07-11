import { X, Sliders, Check } from "lucide-react";
import {
  type ReaderSettings,
  type ReaderTheme,
  type ReaderFont,
  type ReaderLineHeight,
  type ReaderParaMode,
  type ReaderWidth,
} from "../hooks/useReaderSettings";

interface ReaderSettingsDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  settings: ReaderSettings & {
    setTheme: (theme: ReaderTheme) => void;
    setFont: (font: ReaderFont) => void;
    setFontSize: (fontSize: number) => void;
    setLineHeight: (lineHeight: ReaderLineHeight) => void;
    setParaMode: (paraMode: ReaderParaMode) => void;
    setMaxWidth: (maxWidth: ReaderWidth) => void;
    increaseFontSize: () => void;
    decreaseFontSize: () => void;
  };
}

export function ReaderSettingsDrawer({
  isOpen,
  onClose,
  settings,
}: ReaderSettingsDrawerProps) {
  if (!isOpen) return null;

  const themes: {
    id: ReaderTheme;
    label: string;
    bg: string;
    text: string;
    border: string;
  }[] = [
    {
      id: "dark",
      label: "Dark Night",
      bg: "#0d1117",
      text: "#f8fafc",
      border: "#f97316",
    },
    {
      id: "oled",
      label: "OLED Black",
      bg: "#000000",
      text: "#ffffff",
      border: "#fbbf24",
    },
    {
      id: "light",
      label: "Paper Light",
      bg: "#f8fafc",
      text: "#0f172a",
      border: "#ea580c",
    },
    {
      id: "sepia",
      label: "Sepia Eye",
      bg: "#f4ecd8",
      text: "#433422",
      border: "#b45309",
    },
    {
      id: "cyber",
      label: "Cyberpunk",
      bg: "#090812",
      text: "#f3e8ff",
      border: "#a855f7",
    },
  ];

  const fonts: { id: ReaderFont; label: string; style: string }[] = [
    { id: "sans", label: "Sans", style: "var(--font-sans)" },
    { id: "serif", label: "Serif", style: "var(--font-serif)" },
    { id: "outfit", label: "Novel", style: "var(--font-outfit)" },
    { id: "mono", label: "Mono", style: "var(--font-mono)" },
  ];

  return (
    <div
      className="fixed inset-0 z-50 flex items-end md:items-center justify-center p-0 md:p-4 animate-fade-in bg-black/60 backdrop-blur-xs"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-t-3xl md:rounded-3xl border border-[var(--color-border)] p-5 md:p-6 shadow-2xl glass-surface animate-slide-up"
        style={{ backgroundColor: "var(--color-surface)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          className="flex items-center justify-between mb-5 border-b pb-3.5"
          style={{ borderColor: "var(--color-border)" }}
        >
          <div className="flex items-center gap-2">
            <Sliders className="w-5 h-5 text-[var(--color-accent)]" />
            <h3
              className="text-base font-bold font-outfit"
              style={{ color: "var(--color-text)" }}
            >
              Display Preferences
            </h3>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-full flex items-center justify-center hover:bg-white/10 transition-colors cursor-pointer"
            style={{ color: "var(--color-text)" }}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="space-y-5 max-h-[75vh] overflow-y-auto no-scrollbar pr-1">
          {/* Theme Selector */}
          <div>
            <span
              className="block text-xs font-semibold uppercase tracking-wider mb-2.5 opacity-70"
              style={{ color: "var(--color-text-muted)" }}
            >
              Reading Theme
            </span>
            <div className="grid grid-cols-5 gap-2">
              {themes.map((t) => {
                const isSel = settings.theme === t.id;
                return (
                  <button
                    key={t.id}
                    onClick={() => settings.setTheme(t.id)}
                    className={`flex flex-col items-center justify-center py-2.5 px-1 rounded-2xl border text-[10px] font-bold transition-all cursor-pointer ${
                      isSel
                        ? "shadow-md scale-105"
                        : "opacity-60 hover:opacity-100"
                    }`}
                    style={{
                      backgroundColor: t.bg,
                      color: t.text,
                      borderColor: isSel ? t.border : "var(--color-border)",
                      borderWidth: isSel ? "2px" : "1px",
                    }}
                  >
                    <div
                      className="w-4 h-4 rounded-full border mb-1 flex items-center justify-center"
                      style={{ borderColor: t.border }}
                    >
                      {isSel && (
                        <Check className="w-2.5 h-2.5" strokeWidth={3} />
                      )}
                    </div>
                    <span className="line-clamp-1 text-center">{t.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Typography / Font Family */}
          <div>
            <span
              className="block text-xs font-semibold uppercase tracking-wider mb-2.5 opacity-70"
              style={{ color: "var(--color-text-muted)" }}
            >
              Font Family
            </span>
            <div className="grid grid-cols-4 gap-2">
              {fonts.map((f) => {
                const isSel = settings.font === f.id;
                return (
                  <button
                    key={f.id}
                    onClick={() => settings.setFont(f.id)}
                    className={`py-2 px-2 rounded-xl text-xs font-bold border transition-all cursor-pointer ${
                      isSel
                        ? "shadow-sm glow-accent"
                        : "opacity-60 hover:opacity-100"
                    }`}
                    style={{
                      backgroundColor: isSel
                        ? "var(--color-surface-hover)"
                        : "var(--color-bg)",
                      borderColor: isSel
                        ? "var(--color-accent)"
                        : "var(--color-border)",
                      color: isSel
                        ? "var(--color-text)"
                        : "var(--color-text-muted)",
                      fontFamily: f.style,
                    }}
                  >
                    {f.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Font Size */}
          <div>
            <div className="flex justify-between items-center mb-2">
              <span
                className="text-xs font-semibold uppercase tracking-wider opacity-70"
                style={{ color: "var(--color-text-muted)" }}
              >
                Font Size
              </span>
              <span className="text-xs font-bold font-mono text-[var(--color-accent)]">
                {settings.fontSize}px
              </span>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={settings.decreaseFontSize}
                className="w-10 h-10 rounded-xl border flex items-center justify-center font-bold text-sm cursor-pointer hover:bg-white/5"
                style={{
                  borderColor: "var(--color-border)",
                  color: "var(--color-text)",
                }}
              >
                A-
              </button>
              <input
                type="range"
                min="14"
                max="30"
                step="1"
                value={settings.fontSize}
                onChange={(e) => settings.setFontSize(Number(e.target.value))}
                className="flex-1 accent-[var(--color-accent)] cursor-pointer"
              />
              <button
                onClick={settings.increaseFontSize}
                className="w-10 h-10 rounded-xl border flex items-center justify-center font-bold text-sm cursor-pointer hover:bg-white/5"
                style={{
                  borderColor: "var(--color-border)",
                  color: "var(--color-text)",
                }}
              >
                A+
              </button>
            </div>
          </div>

          {/* Line Spacing */}
          <div>
            <span
              className="block text-xs font-semibold uppercase tracking-wider mb-2 opacity-70"
              style={{ color: "var(--color-text-muted)" }}
            >
              Line Spacing
            </span>
            <div className="grid grid-cols-3 gap-2">
              {([1.5, 1.8, 2.2] as ReaderLineHeight[]).map((lh) => (
                <button
                  key={lh}
                  onClick={() => settings.setLineHeight(lh)}
                  className={`py-2 rounded-xl text-xs font-bold border transition-all cursor-pointer ${
                    settings.lineHeight === lh
                      ? "shadow-sm"
                      : "opacity-60 hover:opacity-100"
                  }`}
                  style={{
                    backgroundColor:
                      settings.lineHeight === lh
                        ? "var(--color-surface-hover)"
                        : "var(--color-bg)",
                    borderColor:
                      settings.lineHeight === lh
                        ? "var(--color-accent)"
                        : "var(--color-border)",
                    color:
                      settings.lineHeight === lh
                        ? "var(--color-accent)"
                        : "var(--color-text)",
                  }}
                >
                  {lh === 1.5 ? "Tight" : lh === 1.8 ? "Normal" : "Relaxed"}
                </button>
              ))}
            </div>
          </div>

          {/* Paragraph Margin Mode */}
          <div>
            <span
              className="block text-xs font-semibold uppercase tracking-wider mb-2 opacity-70"
              style={{ color: "var(--color-text-muted)" }}
            >
              Indentation & Spacing
            </span>
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => settings.setParaMode("indent")}
                className={`py-2 px-3 rounded-xl text-xs font-bold border transition-all cursor-pointer ${
                  settings.paraMode === "indent"
                    ? "shadow-sm"
                    : "opacity-60 hover:opacity-100"
                }`}
                style={{
                  backgroundColor:
                    settings.paraMode === "indent"
                      ? "var(--color-surface-hover)"
                      : "var(--color-bg)",
                  borderColor:
                    settings.paraMode === "indent"
                      ? "var(--color-accent)"
                      : "var(--color-border)",
                  color:
                    settings.paraMode === "indent"
                      ? "var(--color-text)"
                      : "var(--color-text-muted)",
                }}
              >
                Book Indent (2em)
              </button>
              <button
                onClick={() => settings.setParaMode("block")}
                className={`py-2 px-3 rounded-xl text-xs font-bold border transition-all cursor-pointer ${
                  settings.paraMode === "block"
                    ? "shadow-sm"
                    : "opacity-60 hover:opacity-100"
                }`}
                style={{
                  backgroundColor:
                    settings.paraMode === "block"
                      ? "var(--color-surface-hover)"
                      : "var(--color-bg)",
                  borderColor:
                    settings.paraMode === "block"
                      ? "var(--color-accent)"
                      : "var(--color-border)",
                  color:
                    settings.paraMode === "block"
                      ? "var(--color-text)"
                      : "var(--color-text-muted)",
                }}
              >
                Block Margin (Modern)
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
