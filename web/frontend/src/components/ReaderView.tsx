import { type ReaderFont, type ReaderLineHeight, type ReaderParaMode, type ReaderWidth } from "../hooks/useReaderSettings";

interface ReaderViewProps {
  text: string;
  fontSize: number;
  font?: ReaderFont;
  lineHeight?: ReaderLineHeight;
  paraMode?: ReaderParaMode;
  maxWidth?: ReaderWidth;
}

export function ReaderView({
  text,
  fontSize,
  font = "sans",
  lineHeight = 1.8,
  paraMode = "indent",
  maxWidth = "normal",
}: ReaderViewProps) {
  // Split by double line break or single line break with indents/blank lines
  const paragraphs = text
    .split(/\r?\n(?:\s*\r?\n)+|\r?\n/)
    .map((p) => p.trim())
    .filter((p) => p.length > 0);

  const fontStyle = {
    sans: "var(--font-sans)",
    serif: "var(--font-serif)",
    outfit: "var(--font-outfit)",
    mono: "var(--font-mono)",
  }[font] || "var(--font-sans)";

  const containerWidthClass = {
    compact: "max-w-[600px]",
    normal: "max-w-[720px]",
    full: "max-w-4xl",
  }[maxWidth] || "max-w-[720px]";

  return (
    <article
      className={`${containerWidthClass} mx-auto transition-all duration-200 select-text px-2 sm:px-4`}
      style={{
        fontSize: `${fontSize}px`,
        lineHeight: String(lineHeight),
        fontFamily: fontStyle,
        color: "var(--color-text)",
      }}
    >
      {paragraphs.map((para, i) => {
        const isFirst = i === 0;
        const isDialogue = para.startsWith('"') || para.startsWith("“") || para.startsWith("'") || para.startsWith("‘") || para.startsWith("- ");
        const indentStyle = paraMode === "indent" && !isFirst && !isDialogue ? "2em" : "0";
        const marginClass = paraMode === "block" ? "mb-6" : "mb-4.5";

        return (
          <p
            key={i}
            className={`${marginClass} tracking-[0.01em] transition-colors`}
            style={{ textIndent: indentStyle }}
          >
            {para}
          </p>
        );
      })}

      {/* End of Chapter Divider Ornament */}
      <div className="pt-12 pb-6 flex items-center justify-center gap-3 opacity-40">
        <div className="w-12 h-px bg-current" />
        <span className="text-sm font-serif">◈</span>
        <div className="w-12 h-px bg-current" />
      </div>
    </article>
  );
}
