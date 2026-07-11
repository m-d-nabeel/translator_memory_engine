import React from "react";
import { BookOpen, Sparkles, Layers, ChevronRight, Play } from "lucide-react";
import type { Novel } from "../api/client";

interface NovelCardProps {
  novel: Novel;
  onClick: () => void;
  onQuickRead?: (e: React.MouseEvent) => void;
}

// Generate deterministic rich gradient cover and theme colors from novel name/id
function getBookCoverStyle(id: number, name: string) {
  const gradients = [
    { from: "#3b82f6", to: "#1d4ed8", accent: "#60a5fa", tag: "Blue Cyber" },
    { from: "#f97316", to: "#c2410c", accent: "#fb923c", tag: "Webnovel Gold" },
    { from: "#8b5cf6", to: "#5b21b6", accent: "#a78bfa", tag: "Mystic Violet" },
    { from: "#10b981", to: "#047857", accent: "#34d399", tag: "Emerald Jade" },
    { from: "#ec4899", to: "#be185d", accent: "#f472b6", tag: "Rose Crimson" },
    { from: "#6366f1", to: "#312e81", accent: "#818cf8", tag: "Indigo Night" },
  ];
  const idx = (id + name.length) % gradients.length;
  return gradients[idx];
}

export function NovelCard({ novel, onClick, onQuickRead }: NovelCardProps) {
  const cover = getBookCoverStyle(novel.id, novel.name);

  const flagMap: Record<string, string> = {
    korean: "🇰🇷 KR",
    chinese: "🇨🇳 CN",
    japanese: "🇯🇵 JP",
  };
  const langBadge = flagMap[novel.source_language.toLowerCase()] || `🌐 ${novel.source_language.toUpperCase()}`;

  return (
    <div
      onClick={onClick}
      className="group relative rounded-2xl border transition-all duration-300 hover:-translate-y-1 hover:shadow-xl cursor-pointer overflow-hidden flex flex-col justify-between"
      style={{
        backgroundColor: "var(--color-surface)",
        borderColor: "var(--color-border)",
      }}
    >
      {/* Top Banner / Cover Header */}
      <div className="p-4 relative flex items-start gap-4">
        {/* Book Cover Graphic Badge */}
        <div
          className="w-20 h-28 shrink-0 rounded-xl shadow-lg flex flex-col justify-between p-2.5 relative overflow-hidden transition-transform duration-300 group-hover:scale-105"
          style={{
            background: `linear-gradient(135deg, ${cover.from} 0%, ${cover.to} 100%)`,
          }}
        >
          {/* Decorative book spine line */}
          <div className="absolute top-0 bottom-0 left-2.5 w-0.5 bg-white/20" />
          
          <div className="flex justify-between items-center z-10">
            <span className="text-[10px] font-black tracking-tighter uppercase px-1 py-0.5 rounded bg-black/40 text-white backdrop-blur-sm">
              AI
            </span>
            <Sparkles className="w-3.5 h-3.5 text-white/80" />
          </div>

          <div className="z-10 mt-auto">
            <p className="text-[11px] font-extrabold text-white leading-tight line-clamp-2 drop-shadow-md font-outfit">
              {novel.title || novel.name}
            </p>
          </div>
        </div>

        {/* Book Metadata details */}
        <div className="flex-1 min-w-0 py-1 flex flex-col justify-between h-28">
          <div>
            <div className="flex items-center gap-2 mb-1.5 flex-wrap">
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-md border" style={{ backgroundColor: "var(--color-bg)", borderColor: "var(--color-border)", color: "var(--color-text-muted)" }}>
                {langBadge}
              </span>
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-md flex items-center gap-1" style={{ backgroundColor: "var(--color-ai-glow)", color: "var(--color-ai)" }}>
                <Layers className="w-3 h-3" />
                Memory Active
              </span>
            </div>

            <h3 className="text-base font-bold leading-snug line-clamp-1 transition-colors group-hover:text-[var(--color-accent)] font-outfit" style={{ color: "var(--color-text)" }}>
              {novel.name}
            </h3>

            {novel.title && novel.title !== novel.name && (
              <p className="text-xs line-clamp-1 opacity-70 mt-0.5" style={{ color: "var(--color-text-muted)" }}>
                {novel.title}
              </p>
            )}
          </div>

          {/* Chapters and status bar */}
          <div className="flex items-center justify-between text-xs pt-2 border-t" style={{ borderColor: "var(--color-border)" }}>
            <span className="flex items-center gap-1.5 font-medium" style={{ color: "var(--color-text-muted)" }}>
              <BookOpen className="w-3.5 h-3.5 text-[var(--color-accent)]" />
              <strong style={{ color: "var(--color-text)" }}>{novel.chapter_count}</strong> chapters
            </span>

            <span className="text-[10px] uppercase tracking-wider font-semibold opacity-60" style={{ color: "var(--color-text-muted)" }}>
              Engine Ready
            </span>
          </div>
        </div>
      </div>

      {/* Action Footer Button Bar */}
      <div className="px-4 py-2.5 bg-black/20 border-t flex items-center justify-between transition-colors group-hover:bg-black/40" style={{ borderColor: "var(--color-border)" }}>
        <span className="text-xs font-semibold flex items-center gap-1 transition-colors group-hover:text-[var(--color-accent)]" style={{ color: "var(--color-text)" }}>
          <span>Open Webnovel Studio</span>
          <ChevronRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
        </span>

        {novel.chapter_count > 0 && onQuickRead && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onQuickRead(e);
            }}
            className="px-3 py-1 rounded-lg text-xs font-bold text-white flex items-center gap-1.5 shadow-sm transition-transform hover:scale-105 active:scale-95 cursor-pointer"
            style={{ background: "linear-gradient(135deg, var(--color-accent) 0%, #ea580c 100%)" }}
          >
            <Play className="w-3 h-3 fill-white" />
            <span>Read</span>
          </button>
        )}
      </div>
    </div>
  );
}
