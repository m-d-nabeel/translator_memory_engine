import React, { useState, useEffect } from "react";
import { useLocalStorageState } from "../hooks/useLocalStorageState";
import { Sparkles, ArrowRight, Languages, RefreshCw } from "lucide-react";

interface PasteFormProps {
  onSubmit: (data: {
    chapter_number: number;
    source_type: string;
    raw_text: string;
  }) => Promise<void>;
  isProcessing: boolean;
  nextSuggestedNumber?: number;
  onCancel?: () => void;
}

export function PasteForm({
  onSubmit,
  isProcessing,
  nextSuggestedNumber = 1,
  onCancel,
}: PasteFormProps) {
  const [chapterNumber, setChapterNumber] = useState(
    String(nextSuggestedNumber),
  );
  const [sourceType, setSourceType] = useLocalStorageState<"mtl" | "original">("tme-paste-sourcetype", "mtl");
  const [text, setText] = useState("");

  useEffect(() => {
    if (nextSuggestedNumber) {
      setChapterNumber(String(nextSuggestedNumber));
    }
  }, [nextSuggestedNumber]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!chapterNumber || !text.trim() || isProcessing) return;
    await onSubmit({
      chapter_number: parseInt(chapterNumber, 10),
      source_type: sourceType,
      raw_text: text,
    });
    setText("");
  };

  const charCount = text.trim() ? text.trim().length : 0;
  const wordCount = text.trim()
    ? text.trim().split(/\s+/).filter(Boolean).length
    : 0;

  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-4 p-5 md:p-6 rounded-3xl border shadow-xl glass-surface animate-fade-in"
      style={{
        backgroundColor: "var(--color-surface)",
        borderColor: "var(--color-border)",
      }}
    >
      <div
        className="flex items-center justify-between border-b pb-4"
        style={{ borderColor: "var(--color-border)" }}
      >
        <div className="flex items-center gap-2.5">
          <div
            className="w-8 h-8 rounded-xl flex items-center justify-center text-white"
            style={{
              background:
                "linear-gradient(135deg, var(--color-accent) 0%, #ea580c 100%)",
            }}
          >
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <h3
              className="text-sm md:text-base font-bold font-outfit"
              style={{ color: "var(--color-text)" }}
            >
              Import Chapter to Studio
            </h3>
            <p
              className="text-[11px] opacity-70"
              style={{ color: "var(--color-text-muted)" }}
            >
              Add raw chapter for AI translation memory refinement
            </p>
          </div>
        </div>
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="text-xs font-semibold px-3 py-1.5 rounded-xl border hover:bg-white/5 transition-colors cursor-pointer"
            style={{
              borderColor: "var(--color-border)",
              color: "var(--color-text-muted)",
            }}
          >
            Close Studio
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label
            className="block text-xs font-semibold uppercase tracking-wider mb-1.5"
            style={{ color: "var(--color-text-muted)" }}
          >
            Chapter Number
          </label>
          <div className="relative flex items-center">
            <span
              className="absolute left-3 text-xs font-bold font-mono opacity-50"
              style={{ color: "var(--color-text-muted)" }}
            >
              Ch.
            </span>
            <input
              type="number"
              value={chapterNumber}
              onChange={(e) => setChapterNumber(e.target.value)}
              className="w-full pl-9 pr-4 py-2.5 rounded-xl border text-sm font-bold font-mono focus:outline-none focus:ring-2 transition-all"
              style={{
                backgroundColor: "var(--color-bg)",
                borderColor: "var(--color-border)",
                color: "var(--color-text)",
              }}
              placeholder="1"
              min="1"
              required
            />
          </div>
        </div>

        <div>
          <label
            className="block text-xs font-semibold uppercase tracking-wider mb-1.5 flex items-center gap-1.5"
            style={{ color: "var(--color-text-muted)" }}
          >
            <Languages className="w-3.5 h-3.5 text-[var(--color-accent)]" />
            Source Stream
          </label>
          <div
            className="grid grid-cols-2 gap-1.5 p-1 rounded-xl border bg-black/20"
            style={{ borderColor: "var(--color-border)" }}
          >
            <button
              type="button"
              onClick={() => setSourceType("mtl")}
              className={`py-2 px-3 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                sourceType === "mtl"
                  ? "shadow-sm"
                  : "opacity-60 hover:opacity-100"
              }`}
              style={{
                backgroundColor:
                  sourceType === "mtl"
                    ? "var(--color-surface-hover)"
                    : "transparent",
                color:
                  sourceType === "mtl"
                    ? "var(--color-ai)"
                    : "var(--color-text-muted)",
              }}
            >
              Raw MTL
            </button>
            <button
              type="button"
              onClick={() => setSourceType("original")}
              className={`py-2 px-3 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                sourceType === "original"
                  ? "shadow-sm"
                  : "opacity-60 hover:opacity-100"
              }`}
              style={{
                backgroundColor:
                  sourceType === "original"
                    ? "var(--color-surface-hover)"
                    : "transparent",
                color:
                  sourceType === "original"
                    ? "var(--color-text)"
                    : "var(--color-text-muted)",
              }}
            >
              OG TL (Ref English)
            </button>
          </div>
        </div>
      </div>

      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label
            className="block text-xs font-semibold uppercase tracking-wider"
            style={{ color: "var(--color-text-muted)" }}
          >
            Chapter Content
          </label>
          <span
            className="text-[11px] font-mono opacity-70"
            style={{ color: "var(--color-text-muted)" }}
          >
            {wordCount} words • {charCount} characters
          </span>
        </div>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          className="w-full p-4 rounded-2xl border text-xs md:text-sm font-mono leading-relaxed resize-y min-h-[220px] focus:outline-none focus:ring-2 transition-all"
          style={{
            backgroundColor: "var(--color-bg)",
            borderColor: "var(--color-border)",
            color: "var(--color-text)",
          }}
          placeholder={
            sourceType === "mtl"
              ? "Paste machine translation (MTL) text here. The AI engine will automatically correct tone, grammar, and apply your terminology policies..."
              : "Paste verified reference translation (OG TL - English) here. The engine will mine canonical terminology, names, and style patterns from this reference text..."
          }
          required
        />
      </div>

      <div className="flex items-center justify-between pt-2">
        <p
          className="text-[11px] opacity-70 hidden sm:block max-w-sm"
          style={{ color: "var(--color-text-muted)" }}
        >
          💡 <strong style={{ color: "var(--color-text)" }}>Pro Tip:</strong>{" "}
          Upon processing, new translation policies will be automatically
          extracted and indexed.
        </p>
        <button
          type="submit"
          disabled={!chapterNumber || !text.trim() || isProcessing}
          className="w-full sm:w-auto px-6 py-3 rounded-2xl text-xs md:text-sm font-bold text-white transition-all flex items-center justify-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer shadow-lg glow-accent ml-auto"
          style={{
            background:
              "linear-gradient(135deg, var(--color-accent) 0%, #ea580c 100%)",
          }}
        >
          {isProcessing ? (
            <>
              <RefreshCw className="w-4 h-4 animate-spin" />
              <span>Refining with Engine...</span>
            </>
          ) : (
            <>
              <Sparkles className="w-4 h-4" />
              <span>Process Chapter {chapterNumber}</span>
              <ArrowRight className="w-4 h-4" />
            </>
          )}
        </button>
      </div>
    </form>
  );
}
