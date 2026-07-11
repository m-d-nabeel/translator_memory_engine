import { Search, Plus, Moon, Sun, Laptop, Sparkles } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import { useReaderSettings, type ReaderTheme } from "../hooks/useReaderSettings";

interface HeaderProps {
  onOpenCreateNovel: () => void;
  onSearchToggle?: () => void;
  searchQuery?: string;
  onSearchChange?: (q: string) => void;
}

export function Header({ onOpenCreateNovel, searchQuery = "", onSearchChange }: HeaderProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const settings = useReaderSettings();

  // If inside reader mode (/read/:id), Header is hidden (Reader manages its own immersive top bar)
  if (location.pathname.startsWith("/read/")) return null;

  const cycleTheme = () => {
    const order: ReaderTheme[] = ["dark", "oled", "light", "sepia", "cyber"];
    const nextIdx = (order.indexOf(settings.theme) + 1) % order.length;
    settings.setTheme(order[nextIdx]);
  };

  const themeLabel = {
    dark: "Dark Night",
    oled: "OLED Black",
    light: "Paper Light",
    sepia: "Sepia Eye-Care",
    cyber: "Cyberpunk",
  }[settings.theme] || "Dark";

  return (
    <header className="sticky top-0 z-30 glass-surface border-b px-4 py-3 md:py-3.5 transition-all duration-200" style={{ borderColor: "var(--color-border)" }}>
      <div className="max-w-6xl mx-auto flex items-center justify-between gap-3">
        
        {/* Mobile Brand Title (only visible on mobile where sidebar is hidden) */}
        <div className="flex items-center gap-2.5 md:hidden cursor-pointer" onClick={() => navigate("/")}>
          <div className="w-8 h-8 rounded-lg flex items-center justify-center font-bold text-white text-sm shadow-md" style={{ background: "linear-gradient(135deg, var(--color-accent) 0%, #ea580c 100%)" }}>
            TN
          </div>
          <div>
            <span className="font-bold text-sm tracking-tight leading-none" style={{ color: "var(--color-text)" }}>
              Webnovel <span style={{ color: "var(--color-accent)" }}>AI</span>
            </span>
          </div>
        </div>

        {/* Desktop Title / Breadcrumb context */}
        <div className="hidden md:flex items-center gap-3">
          <span className="text-xs font-semibold px-2.5 py-1 rounded-full border flex items-center gap-1.5" style={{ backgroundColor: "var(--color-surface)", borderColor: "var(--color-border)", color: "var(--color-text-muted)" }}>
            <Sparkles className="w-3.5 h-3.5 text-[var(--color-accent)] animate-pulse" />
            Translator Memory Engine Activated
          </span>
        </div>

        {/* Search Bar Input (Compact inline on desktop, expandable on mobile) */}
        {onSearchChange !== undefined && (
          <div className="flex-1 max-w-md mx-2">
            <div className="relative flex items-center">
              <Search className="absolute left-3 w-4 h-4 opacity-50" style={{ color: "var(--color-text-muted)" }} />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => onSearchChange(e.target.value)}
                placeholder="Search novels, policies, or translations..."
                className="w-full pl-9 pr-4 py-1.5 rounded-full text-xs md:text-sm border transition-all duration-150 focus:outline-none focus:ring-2"
                style={{
                  backgroundColor: "var(--color-bg)",
                  borderColor: "var(--color-border)",
                  color: "var(--color-text)",
                }}
              />
              {searchQuery && (
                <button
                  onClick={() => onSearchChange("")}
                  className="absolute right-3 text-xs opacity-60 hover:opacity-100 cursor-pointer"
                  style={{ color: "var(--color-text-muted)" }}
                >
                  ✕
                </button>
              )}
            </div>
          </div>
        )}

        {/* Action Controls */}
        <div className="flex items-center gap-2">
          {/* Quick Theme Cycle Button */}
          <button
            onClick={cycleTheme}
            title={`Current Theme: ${themeLabel}. Click to switch.`}
            className="px-2.5 py-1.5 rounded-xl border text-xs font-medium flex items-center gap-1.5 transition-all hover:scale-105 cursor-pointer"
            style={{
              backgroundColor: "var(--color-surface)",
              borderColor: "var(--color-border)",
              color: "var(--color-text-muted)",
            }}
          >
            {settings.theme === "light" ? (
              <Sun className="w-3.5 h-3.5 text-amber-500" />
            ) : settings.theme === "sepia" ? (
              <Laptop className="w-3.5 h-3.5 text-amber-700" />
            ) : (
              <Moon className="w-3.5 h-3.5 text-[var(--color-accent)]" />
            )}
            <span className="hidden sm:inline font-mono">{themeLabel}</span>
          </button>

          {/* New Novel Action Trigger */}
          {location.pathname === "/" && (
            <button
              onClick={onOpenCreateNovel}
              className="px-3.5 py-1.5 rounded-xl text-xs md:text-sm font-semibold text-white flex items-center gap-1.5 shadow-md transition-all duration-150 hover:scale-105 active:scale-95 cursor-pointer glow-accent"
              style={{ background: "linear-gradient(135deg, var(--color-accent) 0%, #ea580c 100%)" }}
            >
              <Plus className="w-4 h-4" strokeWidth={2.5} />
              <span>New Novel</span>
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
