import type { ChapterSummary } from "../api/client";

interface ChapterListProps {
  chapters: ChapterSummary[];
  onRead: (chapterId: number) => void;
}

const statusColors: Record<string, string> = {
  pending: "var(--color-text-muted)",
  unprocessed: "var(--color-text-muted)",
  processing: "var(--color-warning)",
  completed: "var(--color-success)",
  failed: "var(--color-error)",
};

const statusLabels: Record<string, string> = {
  pending: "Pending",
  unprocessed: "Unprocessed",
  processing: "Processing...",
  completed: "Completed",
  failed: "Failed",
};

export function ChapterList({ chapters, onRead }: ChapterListProps) {
  if (chapters.length === 0) {
    return (
      <p
        className="text-center py-8"
        style={{ color: "var(--color-text-muted)" }}
      >
        No chapters yet. Paste some text above to get started.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {chapters.map((ch) => (
        <div
          key={ch.id}
          className="flex items-center justify-between p-3 rounded-lg border"
          style={{
            backgroundColor: "var(--color-surface)",
            borderColor: "var(--color-border)",
          }}
        >
          <div className="flex items-center gap-3">
            <span
              className="font-mono text-sm font-semibold"
              style={{ color: "var(--color-accent)" }}
            >
              Ch. {ch.chapter_number}
            </span>
            <span
              className="text-xs px-2 py-0.5 rounded-full"
              style={{
                backgroundColor: `${statusColors[ch.status]}20`,
                color: statusColors[ch.status],
              }}
            >
              {statusLabels[ch.status]}
            </span>
            <span
              className="text-xs"
              style={{ color: "var(--color-text-muted)" }}
            >
              {ch.source_type}
            </span>
          </div>
          {ch.status === "completed" && (
            <button
              onClick={() => onRead(ch.id)}
              className="text-sm px-3 py-1 rounded-lg font-medium transition-colors"
              style={{
                backgroundColor: "var(--color-accent)",
                color: "var(--color-bg)",
              }}
            >
              Read
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
