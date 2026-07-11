import { useState } from "react";
import { X, BookOpen, Search, ChevronRight } from "lucide-react";
import type { Chapter } from "../api/client";

interface TableOfContentsDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  chapters: Chapter[];
  currentChapterId: number;
  onSelectChapter: (chapterId: number) => void;
  novelName?: string;
}

export function TableOfContentsDrawer({
  isOpen,
  onClose,
  chapters,
  currentChapterId,
  onSelectChapter,
  novelName,
}: TableOfContentsDrawerProps) {
  const [search, setSearch] = useState("");
  const [sortAsc, setSortAsc] = useState(true);

  if (!isOpen) return null;

  // Group chapters by number and pick the best available version (MTL refined vs original)
  const grouped = chapters.reduce<Record<number, Chapter[]>>((acc, ch) => {
    if (!acc[ch.chapter_number]) acc[ch.chapter_number] = [];
    acc[ch.chapter_number].push(ch);
    return acc;
  }, {});

  const sortedNums = Object.keys(grouped)
    .map(Number)
    .sort((a, b) => (sortAsc ? a - b : b - a));

  const filteredNums = sortedNums.filter((n) => {
    if (!search.trim()) return true;
    return String(n).includes(search.trim());
  });

  return (
    <div
      className="fixed inset-0 z-50 flex justify-start animate-fade-in bg-black/60 backdrop-blur-xs"
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm h-full border-r flex flex-col justify-between p-5 shadow-2xl glass-surface animate-slide-right"
        style={{
          backgroundColor: "var(--color-surface)",
          borderColor: "var(--color-border)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div>
          {/* Header */}
          <div
            className="flex items-center justify-between mb-4 border-b pb-3.5"
            style={{ borderColor: "var(--color-border)" }}
          >
            <div className="flex items-center gap-2 min-w-0">
              <BookOpen className="w-5 h-5 shrink-0 text-[var(--color-accent)]" />
              <div className="min-w-0">
                <h3
                  className="text-sm font-bold font-outfit line-clamp-1"
                  style={{ color: "var(--color-text)" }}
                >
                  {novelName || "Catalog / Table of Contents"}
                </h3>
                <p
                  className="text-[11px] opacity-70"
                  style={{ color: "var(--color-text-muted)" }}
                >
                  {Object.keys(grouped).length} Total Entries
                </p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="w-8 h-8 rounded-full flex items-center justify-center hover:bg-white/10 transition-colors shrink-0 cursor-pointer"
              style={{ color: "var(--color-text)" }}
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Search Box and Sort Button */}
          <div className="flex items-center gap-2 mb-4">
            <div className="relative flex-1">
              <Search
                className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 opacity-50"
                style={{ color: "var(--color-text-muted)" }}
              />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Find Ch. #"
                className="w-full pl-8 pr-3 py-1.5 rounded-xl text-xs border focus:outline-none focus:ring-1"
                style={{
                  backgroundColor: "var(--color-bg)",
                  borderColor: "var(--color-border)",
                  color: "var(--color-text)",
                }}
              />
            </div>
            <button
              onClick={() => setSortAsc(!sortAsc)}
              className="px-2.5 py-1.5 rounded-xl border text-xs font-bold transition-colors hover:bg-white/5 cursor-pointer"
              style={{
                borderColor: "var(--color-border)",
                color: "var(--color-text)",
              }}
            >
              {sortAsc ? "1 -> N" : "N -> 1"}
            </button>
          </div>
        </div>

        {/* Chapter List Drawer */}
        <div className="flex-1 overflow-y-auto no-scrollbar space-y-1.5 pr-1">
          {filteredNums.map((chNum) => {
            const entries = grouped[chNum];
            const mtl = entries.find((e) => e.source_type === "mtl");
            const orig = entries.find((e) => e.source_type === "original");
            const targetCh = mtl || orig || entries[0];
            const isCurrent = entries.some((e) => e.id === currentChapterId);

            return (
              <button
                key={chNum}
                onClick={() => {
                  onSelectChapter(targetCh.id);
                  onClose();
                }}
                className={`w-full p-3 rounded-2xl border text-left transition-all flex items-center justify-between gap-3 cursor-pointer ${
                  isCurrent
                    ? "shadow-md glow-accent border-[var(--color-accent)] bg-[var(--color-surface-hover)] scale-[1.01]"
                    : "hover:bg-white/5 border-transparent hover:border-[var(--color-border)]"
                }`}
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div
                    className={`w-8 h-8 rounded-xl flex items-center justify-center text-xs font-bold shrink-0 ${
                      isCurrent
                        ? "bg-[var(--color-accent)] text-white"
                        : "bg-black/20 text-[var(--color-text-muted)]"
                    }`}
                  >
                    {chNum}
                  </div>
                  <div className="min-w-0">
                    <span
                      className="text-xs font-bold block line-clamp-1"
                      style={{
                        color: isCurrent
                          ? "var(--color-accent)"
                          : "var(--color-text)",
                      }}
                    >
                      Chapter {chNum}
                    </span>
                    <span
                      className="text-[10px] opacity-60 flex items-center gap-1 mt-0.5"
                      style={{ color: "var(--color-text-muted)" }}
                    >
                      {mtl?.status === "completed"
                        ? "✨ Refined AI"
                        : orig
                          ? "📄 OG TL (Ref)"
                          : "⏳ Processing"}
                    </span>
                  </div>
                </div>

                <ChevronRight
                  className={`w-4 h-4 shrink-0 ${isCurrent ? "text-[var(--color-accent)]" : "opacity-30"}`}
                />
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
