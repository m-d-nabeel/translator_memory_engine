import React, { useState } from "react";
import { X, BookOpen, Sparkles, Languages } from "lucide-react";

interface CreateNovelModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: { name: string; title?: string; source_language?: string }) => Promise<void>;
  isPending: boolean;
}

export function CreateNovelModal({ isOpen, onClose, onSubmit, isPending }: CreateNovelModalProps) {
  const [name, setName] = useState("");
  const [title, setTitle] = useState("");
  const [sourceLang, setSourceLang] = useState("korean");

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || isPending) return;
    await onSubmit({
      name: name.trim(),
      title: title.trim() || undefined,
      source_language: sourceLang,
    });
    setName("");
    setTitle("");
    onClose();
  };

  const languages = [
    { id: "korean", label: "Korean (KR)", flag: "🇰🇷" },
    { id: "chinese", label: "Chinese (CN)", flag: "🇨🇳" },
    { id: "japanese", label: "Japanese (JP)", flag: "🇯🇵" },
    { id: "english", label: "English / Other", flag: "🌐" },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-end md:items-center justify-center p-0 md:p-4 animate-fade-in bg-black/75 backdrop-blur-sm">
      <div
        className="w-full max-w-lg rounded-t-3xl md:rounded-3xl border border-[var(--color-border)] p-6 shadow-2xl glass-surface animate-slide-up"
        style={{ backgroundColor: "var(--color-surface)" }}
      >
        <div className="flex items-center justify-between mb-6 border-b pb-4" style={{ borderColor: "var(--color-border)" }}>
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl flex items-center justify-center text-white" style={{ background: "linear-gradient(135deg, var(--color-accent) 0%, #ea580c 100%)" }}>
              <BookOpen className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold" style={{ color: "var(--color-text)" }}>
                Add New Webnovel
              </h2>
              <p className="text-xs opacity-70" style={{ color: "var(--color-text-muted)" }}>
                Import into Translator Memory Engine
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-full flex items-center justify-center opacity-60 hover:opacity-100 hover:bg-white/10 transition-colors cursor-pointer"
            style={{ color: "var(--color-text)" }}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: "var(--color-text-muted)" }}>
              Internal Novel Identifier (<span className="text-red-400">*</span>)
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-4 py-3 rounded-xl border text-sm font-medium focus:outline-none focus:ring-2 transition-all"
              style={{
                backgroundColor: "var(--color-bg)",
                borderColor: "var(--color-border)",
                color: "var(--color-text)",
              }}
              placeholder="e.g. shadow_monarch_01 or sss_class_hunter"
              autoFocus
              required
            />
            <p className="text-[11px] mt-1 opacity-60" style={{ color: "var(--color-text-muted)" }}>
              Unique key or slug for this translation memory database.
            </p>
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: "var(--color-text-muted)" }}>
              Display Title (Optional)
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full px-4 py-3 rounded-xl border text-sm font-medium focus:outline-none focus:ring-2 transition-all"
              style={{
                backgroundColor: "var(--color-bg)",
                borderColor: "var(--color-border)",
                color: "var(--color-text)",
              }}
              placeholder="e.g. Solo Leveling / Omniscient Reader's Viewpoint"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider mb-2 flex items-center gap-1.5" style={{ color: "var(--color-text-muted)" }}>
              <Languages className="w-3.5 h-3.5 text-[var(--color-accent)]" />
              Source Language
            </label>
            <div className="grid grid-cols-2 gap-2">
              {languages.map((lang) => {
                const isSelected = sourceLang === lang.id;
                return (
                  <button
                    key={lang.id}
                    type="button"
                    onClick={() => setSourceLang(lang.id)}
                    className={`flex items-center gap-2 px-3.5 py-2.5 rounded-xl border text-xs font-medium transition-all cursor-pointer ${
                      isSelected ? "shadow-md glow-accent" : "opacity-60 hover:opacity-100"
                    }`}
                    style={{
                      backgroundColor: isSelected ? "var(--color-surface-hover)" : "var(--color-bg)",
                      borderColor: isSelected ? "var(--color-accent)" : "var(--color-border)",
                      color: isSelected ? "var(--color-text)" : "var(--color-text-muted)",
                    }}
                  >
                    <span className="text-base">{lang.flag}</span>
                    <span>{lang.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="pt-3 flex items-center gap-3">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-3 rounded-xl text-xs font-semibold border transition-colors hover:bg-white/5 cursor-pointer"
              style={{ borderColor: "var(--color-border)", color: "var(--color-text-muted)" }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!name.trim() || isPending}
              className="flex-1 py-3 rounded-xl text-xs font-semibold text-white transition-all duration-150 flex items-center justify-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer glow-accent"
              style={{ background: "linear-gradient(135deg, var(--color-accent) 0%, #ea580c 100%)" }}
            >
              {isPending ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  <span>Creating Memory...</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  <span>Create Novel Studio</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
