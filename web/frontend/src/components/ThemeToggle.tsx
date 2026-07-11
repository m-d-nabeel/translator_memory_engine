import { Moon, Sun, Laptop } from "lucide-react";
import {
  useReaderSettings,
  type ReaderTheme,
} from "../hooks/useReaderSettings";

export function ThemeToggle() {
  const { theme, setTheme } = useReaderSettings();

  const cycleTheme = () => {
    const order: ReaderTheme[] = ["dark", "oled", "light", "sepia", "cyber"];
    const nextIdx = (order.indexOf(theme) + 1) % order.length;
    setTheme(order[nextIdx]);
  };

  return (
    <button
      onClick={cycleTheme}
      className="p-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)] transition-colors hover:bg-[var(--color-surface-hover)] cursor-pointer flex items-center gap-1.5"
      title={`Current Theme: ${theme}. Click to change.`}
    >
      {theme === "light" ? (
        <Sun className="w-4 h-4" style={{ color: "var(--color-warning)" }} />
      ) : theme === "sepia" ? (
        <Laptop className="w-4 h-4" style={{ color: "var(--color-warning)" }} />
      ) : (
        <Moon className="w-4 h-4 text-[var(--color-accent)]" />
      )}
      <span className="text-xs font-mono uppercase hidden sm:inline">
        {theme}
      </span>
    </button>
  );
}
