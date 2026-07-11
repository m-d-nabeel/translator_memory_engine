import { Settings, Sun, Type } from "lucide-react";
import { useReaderSettings, type ReaderTheme, type ReaderFont, type ReaderLineHeight, type ReaderWidth } from "../hooks/useReaderSettings";

export function SettingsTab() {
  const settings = useReaderSettings();

  const themes: { id: ReaderTheme; label: string; desc: string; previewBg: string; previewText: string; accent: string }[] = [
    { id: "dark", label: "Dark Night", desc: "Default immersive blue-slate dark mode", previewBg: "#0d1117", previewText: "#f8fafc", accent: "#f97316" },
    { id: "oled", label: "OLED Black", desc: "Pure pitch black (#000000) battery saver", previewBg: "#000000", previewText: "#ffffff", accent: "#fbbf24" },
    { id: "light", label: "Paper Light", desc: "Crisp daytime reading sheet", previewBg: "#f8fafc", previewText: "#0f172a", accent: "#ea580c" },
    { id: "sepia", label: "Sepia Eye-Care", desc: "Warm vintage book tone for long reading", previewBg: "#f4ecd8", previewText: "#433422", accent: "#b45309" },
    { id: "cyber", label: "Cyberpunk", desc: "Sleek dark violet cyberpunk aesthetics", previewBg: "#090812", previewText: "#f3e8ff", accent: "#a855f7" },
  ];

  const fonts: { id: ReaderFont; label: string; desc: string; sample: string }[] = [
    { id: "sans", label: "Modern Sans (Inter)", desc: "Clean geometric sans-serif for high speed reading", sample: "Inter, sans-serif" },
    { id: "serif", label: "Book Serif (Merriweather)", desc: "Classic book serif typography with organic curves", sample: "Merriweather, serif" },
    { id: "outfit", label: "Studio Display (Outfit)", desc: "Bold modern display font with distinct personality", sample: "Outfit, sans-serif" },
    { id: "mono", label: "Terminal (Fira Code)", desc: "Monospace coding aesthetic for raw comparison", sample: "Fira Code, monospace" },
  ];

  return (
    <div className="space-y-8 animate-fade-in pb-12 max-w-4xl mx-auto">
      {/* Header */}
      <div className="p-6 rounded-3xl border glass-surface" style={{ borderColor: "var(--color-border)" }}>
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl flex items-center justify-center text-white shadow-lg glow-accent" style={{ background: "linear-gradient(135deg, var(--color-accent) 0%, #ea580c 100%)" }}>
            <Settings className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-xl md:text-2xl font-black font-outfit" style={{ color: "var(--color-text)" }}>
              Global Reader & UI Preferences
            </h1>
            <p className="text-xs md:text-sm mt-0.5 opacity-70" style={{ color: "var(--color-text-muted)" }}>
              Customize how novels, themes, and AI translations look across desktop and mobile devices.
            </p>
          </div>
        </div>
      </div>

      {/* Theme Selection */}
      <section className="space-y-4">
        <div className="flex items-center gap-2 border-b pb-2" style={{ borderColor: "var(--color-border)" }}>
          <Sun className="w-4 h-4 text-[var(--color-accent)]" />
          <h2 className="text-base font-bold font-outfit" style={{ color: "var(--color-text)" }}>
            Visual Theme & Color Palette
          </h2>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3">
          {themes.map((t) => {
            const isSelected = settings.theme === t.id;
            return (
              <button
                key={t.id}
                onClick={() => settings.setTheme(t.id)}
                className={`p-4 rounded-2xl border text-left transition-all flex flex-col justify-between cursor-pointer ${
                  isSelected ? "shadow-lg scale-[1.02]" : "opacity-75 hover:opacity-100"
                }`}
                style={{
                  backgroundColor: "var(--color-surface)",
                  borderColor: isSelected ? "var(--color-accent)" : "var(--color-border)",
                  boxShadow: isSelected ? "0 0 20px var(--color-accent-glow)" : "none",
                }}
              >
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-sm font-bold font-outfit" style={{ color: "var(--color-text)" }}>
                      {t.label}
                    </span>
                    <div
                      className="w-5 h-5 rounded-full border flex items-center justify-center text-[10px] font-bold"
                      style={{ backgroundColor: t.previewBg, color: t.previewText, borderColor: t.accent }}
                    >
                      A
                    </div>
                  </div>
                  <p className="text-xs leading-relaxed opacity-80" style={{ color: "var(--color-text-muted)" }}>
                    {t.desc}
                  </p>
                </div>

                {/* Mini Preview Box */}
                <div
                  className="mt-3 p-2.5 rounded-xl border text-[11px] font-medium transition-colors"
                  style={{ backgroundColor: t.previewBg, color: t.previewText, borderColor: isSelected ? t.accent : "transparent" }}
                >
                  "Shadow Monarch initiated memory sync..."
                </div>
              </button>
            );
          })}
        </div>
      </section>

      {/* Typography Selection */}
      <section className="space-y-4">
        <div className="flex items-center gap-2 border-b pb-2" style={{ borderColor: "var(--color-border)" }}>
          <Type className="w-4 h-4 text-[var(--color-accent)]" />
          <h2 className="text-base font-bold font-outfit" style={{ color: "var(--color-text)" }}>
            Reader Typography & Layout
          </h2>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          {fonts.map((f) => {
            const isSelected = settings.font === f.id;
            return (
              <button
                key={f.id}
                onClick={() => settings.setFont(f.id)}
                className={`p-4 rounded-2xl border text-left transition-all cursor-pointer ${
                  isSelected ? "shadow-md glow-accent" : "opacity-75 hover:opacity-100"
                }`}
                style={{
                  backgroundColor: "var(--color-surface)",
                  borderColor: isSelected ? "var(--color-accent)" : "var(--color-border)",
                  fontFamily: f.sample,
                }}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-base font-bold" style={{ color: "var(--color-text)" }}>
                    {f.label}
                  </span>
                  {isSelected && (
                    <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded bg-[var(--color-accent)] text-white font-sans">
                      Active
                    </span>
                  )}
                </div>
                <p className="text-xs opacity-80 font-sans" style={{ color: "var(--color-text-muted)" }}>
                  {f.desc}
                </p>
              </button>
            );
          })}
        </div>

        {/* Sliders and Scanners */}
        <div className="p-5 rounded-3xl border space-y-6 glass-surface" style={{ borderColor: "var(--color-border)" }}>
          <div className="grid sm:grid-cols-2 gap-6">
            {/* Font Size Scrubber */}
            <div>
              <div className="flex justify-between items-center mb-2">
                <span className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--color-text-muted)" }}>
                  Default Reader Font Size
                </span>
                <span className="text-sm font-bold font-mono" style={{ color: "var(--color-accent)" }}>
                  {settings.fontSize}px
                </span>
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={settings.decreaseFontSize}
                  className="w-9 h-9 rounded-xl border flex items-center justify-center font-bold text-sm cursor-pointer hover:bg-white/5"
                  style={{ borderColor: "var(--color-border)", color: "var(--color-text)" }}
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
                  className="w-9 h-9 rounded-xl border flex items-center justify-center font-bold text-sm cursor-pointer hover:bg-white/5"
                  style={{ borderColor: "var(--color-border)", color: "var(--color-text)" }}
                >
                  A+
                </button>
              </div>
            </div>

            {/* Line Spacing Scrubber */}
            <div>
              <span className="block text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: "var(--color-text-muted)" }}>
                Line Spacing (Height)
              </span>
              <div className="grid grid-cols-3 gap-2">
                {([1.5, 1.8, 2.2] as ReaderLineHeight[]).map((lh) => (
                  <button
                    key={lh}
                    onClick={() => settings.setLineHeight(lh)}
                    className={`py-2 rounded-xl text-xs font-bold border transition-all cursor-pointer ${
                      settings.lineHeight === lh ? "shadow-sm glow-accent" : "opacity-65 hover:opacity-100"
                    }`}
                    style={{
                      backgroundColor: settings.lineHeight === lh ? "var(--color-surface-hover)" : "var(--color-bg)",
                      borderColor: settings.lineHeight === lh ? "var(--color-accent)" : "var(--color-border)",
                      color: settings.lineHeight === lh ? "var(--color-accent)" : "var(--color-text)",
                    }}
                  >
                    {lh === 1.5 ? "Tight (1.5x)" : lh === 1.8 ? "Normal (1.8x)" : "Relaxed (2.2x)"}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="grid sm:grid-cols-2 gap-6 pt-4 border-t" style={{ borderColor: "var(--color-border)" }}>
            {/* Paragraph Mode */}
            <div>
              <span className="block text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: "var(--color-text-muted)" }}>
                Paragraph Indentation & Margins
              </span>
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => settings.setParaMode("indent")}
                  className={`py-2 px-3 rounded-xl text-xs font-bold border transition-all cursor-pointer ${
                    settings.paraMode === "indent" ? "shadow-sm" : "opacity-65 hover:opacity-100"
                  }`}
                  style={{
                    backgroundColor: settings.paraMode === "indent" ? "var(--color-surface-hover)" : "var(--color-bg)",
                    borderColor: settings.paraMode === "indent" ? "var(--color-accent)" : "var(--color-border)",
                    color: settings.paraMode === "indent" ? "var(--color-text)" : "var(--color-text-muted)",
                  }}
                >
                  Book Indent (2em)
                </button>
                <button
                  onClick={() => settings.setParaMode("block")}
                  className={`py-2 px-3 rounded-xl text-xs font-bold border transition-all cursor-pointer ${
                    settings.paraMode === "block" ? "shadow-sm" : "opacity-65 hover:opacity-100"
                  }`}
                  style={{
                    backgroundColor: settings.paraMode === "block" ? "var(--color-surface-hover)" : "var(--color-bg)",
                    borderColor: settings.paraMode === "block" ? "var(--color-accent)" : "var(--color-border)",
                    color: settings.paraMode === "block" ? "var(--color-text)" : "var(--color-text-muted)",
                  }}
                >
                  Block Space (Modern)
                </button>
              </div>
            </div>

            {/* Container Max Width */}
            <div>
              <span className="block text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: "var(--color-text-muted)" }}>
                Reader Container Width
              </span>
              <div className="grid grid-cols-3 gap-2">
                {([
                  { id: "compact", label: "Compact 600px" },
                  { id: "normal", label: "Normal 720px" },
                  { id: "full", label: "Full 100%" },
                ] as { id: ReaderWidth; label: string }[]).map((w) => (
                  <button
                    key={w.id}
                    onClick={() => settings.setMaxWidth(w.id)}
                    className={`py-2 px-2 rounded-xl text-[11px] font-bold border transition-all cursor-pointer ${
                      settings.maxWidth === w.id ? "shadow-sm" : "opacity-65 hover:opacity-100"
                    }`}
                    style={{
                      backgroundColor: settings.maxWidth === w.id ? "var(--color-surface-hover)" : "var(--color-bg)",
                      borderColor: settings.maxWidth === w.id ? "var(--color-accent)" : "var(--color-border)",
                      color: settings.maxWidth === w.id ? "var(--color-text)" : "var(--color-text-muted)",
                    }}
                  >
                    {w.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
