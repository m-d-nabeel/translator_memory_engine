import { useEffect, useState, useRef, useMemo } from "react";
import { Sparkles } from "lucide-react";
import {
  type ReaderFont,
  type ReaderLineHeight,
  type ReaderParaMode,
  type ReaderWidth,
} from "../hooks/useReaderSettings";

interface ReaderViewProps {
  text: string;
  fontSize: number;
  font?: ReaderFont;
  lineHeight?: ReaderLineHeight;
  paraMode?: ReaderParaMode;
  maxWidth?: ReaderWidth;
  isProcessing?: boolean;
}

export function ReaderView({
  text,
  fontSize,
  font = "sans",
  lineHeight = 1.8,
  paraMode = "indent",
  maxWidth = "normal",
  isProcessing = false,
}: ReaderViewProps) {
  const [streamCount, setStreamCount] = useState<number | null>(null);
  const prevTextRef = useRef(text);
  const prevProcessingRef = useRef(isProcessing);

  // Split by double line break or single line break with indents/blank lines
  const targetParagraphs = useMemo(() => {
    return text
      .split(/\r?\n(?:\s*\r?\n)+|\r?\n/)
      .map((p) => p.trim())
      .filter((p) => p.length > 0);
  }, [text]);

  // Effect 1: Detect transitions (e.g. finished processing vs normal tab switch)
  useEffect(() => {
    const justFinishedProcessing =
      prevProcessingRef.current && !isProcessing && prevTextRef.current !== text;

    if (justFinishedProcessing) {
      setStreamCount(1); // Start streaming
    } else if (prevTextRef.current !== text) {
      setStreamCount(null); // Normal tab switch, no streaming
    }

    prevProcessingRef.current = isProcessing;
    prevTextRef.current = text;
  }, [text, isProcessing]);

  // Effect 2: Run the stream if active
  useEffect(() => {
    if (streamCount !== null && streamCount < targetParagraphs.length) {
      const timer = setTimeout(() => {
        setStreamCount((s) => (s !== null ? s + 1 : null));
      }, 50); // fast stream
      return () => clearTimeout(timer);
    } else if (streamCount !== null && streamCount >= targetParagraphs.length) {
      setStreamCount(null); // Stream finished
    }
  }, [streamCount, targetParagraphs.length]);

  const displayedParagraphs =
    streamCount !== null ? targetParagraphs.slice(0, streamCount) : targetParagraphs;
  const isStreaming = streamCount !== null;

  const fontStyle =
    {
      sans: "var(--font-sans)",
      serif: "var(--font-serif)",
      outfit: "var(--font-outfit)",
      mono: "var(--font-mono)",
    }[font] || "var(--font-sans)";

  const containerWidthClass =
    {
      compact: "max-w-[600px]",
      normal: "max-w-[720px]",
      full: "max-w-4xl",
    }[maxWidth] || "max-w-[720px]";

  return (
    <div className="relative">
      {/* Overlay when processing */}
      {isProcessing && (
        <div className="absolute top-0 left-0 right-0 z-10 flex justify-center sticky top-24">
          <div
            className="inline-flex items-center justify-center px-4 py-2 rounded-full bg-[var(--color-surface)] border shadow-lg shadow-[var(--color-ai)]/20 animate-bounce"
            style={{ borderColor: "var(--color-ai)" }}
          >
            <Sparkles className="w-4 h-4 text-[var(--color-ai)] mr-2 animate-pulse" />
            <span className="text-xs font-bold text-[var(--color-ai)]">
              AI is Rewriting...
            </span>
          </div>
        </div>
      )}

      <article
        className={`${containerWidthClass} mx-auto transition-all duration-200 select-text px-2 sm:px-4 ${isProcessing ? "opacity-40 grayscale-[50%] blur-[1px] animate-pulse" : ""}`}
        style={{
          fontSize: `${fontSize}px`,
          lineHeight: String(lineHeight),
          fontFamily: fontStyle,
          color: "var(--color-text)",
        }}
      >
        {displayedParagraphs.map((para, i) => {
          const isFirst = i === 0;
          const isDialogue =
            para.startsWith('"') ||
            para.startsWith("“") ||
            para.startsWith("'") ||
            para.startsWith("‘") ||
            para.startsWith("- ");
          const indentStyle =
            paraMode === "indent" && !isFirst && !isDialogue ? "2em" : "0";
          const marginClass = paraMode === "block" ? "mb-6" : "mb-4.5";

          return (
            <p
              key={i}
              className={`${marginClass} tracking-[0.01em] transition-colors ${isStreaming && i === displayedParagraphs.length - 1 ? "animate-slide-up animate-fade-in" : ""}`}
              style={{ textIndent: indentStyle }}
            >
              {para}
            </p>
          );
        })}

        {/* End of Chapter Divider Ornament */}
        {!isStreaming && displayedParagraphs.length > 0 && (
          <div className="pt-12 pb-6 flex items-center justify-center gap-3 opacity-40">
            <div className="w-12 h-px bg-current" />
            <span className="text-sm font-serif">◈</span>
            <div className="w-12 h-px bg-current" />
          </div>
        )}
      </article>
    </div>
  );
}
