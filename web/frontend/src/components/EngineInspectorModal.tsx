import { useState, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type ProcessingJob } from "../api/client";
import {
  Terminal,
  RefreshCw,
  X,
  CheckCircle2,
  AlertCircle,
  Clock,
  Cpu,
  Layers,
  Sparkles,
} from "lucide-react";

interface EngineInspectorModalProps {
  novelId: number;
  chapterId?: number | null; // If provided, initially focus/select jobs for this chapter
  onClose: () => void;
}

export function EngineInspectorModal({
  novelId,
  chapterId,
  onClose,
}: EngineInspectorModalProps) {
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null);
  const [filterMode, setFilterMode] = useState<"all" | "chapter">("all");
  const [autoScroll, setAutoScroll] = useState(true);
  const terminalEndRef = useRef<HTMLDivElement>(null);

  // Poll jobs list every 1.5s for live feedback
  const {
    data: novelJobs = [] as ProcessingJob[],
    isLoading,
    refetch,
    isRefetching,
  } = useQuery({
    queryKey: ["novelJobs", novelId],
    queryFn: () => api.listNovelJobs(novelId),
    refetchInterval: 1500, // Live polling while modal is open
  });

  // Filtered jobs
  const displayedJobs: ProcessingJob[] =
    filterMode === "chapter" && chapterId
      ? novelJobs.filter((j) => j.chapter_id === chapterId)
      : novelJobs;

  // Auto-select latest job if none selected
  useEffect(() => {
    if (!selectedJobId && displayedJobs.length > 0) {
      // If chapterId provided, try to select that chapter's latest job first
      if (chapterId) {
        const chJob = displayedJobs.find((j) => j.chapter_id === chapterId);
        if (chJob) setSelectedJobId(chJob.id);
        else setSelectedJobId(displayedJobs[0].id);
      } else {
        setSelectedJobId(displayedJobs[0].id);
      }
    }
  }, [displayedJobs, selectedJobId, chapterId]);

  const activeJob =
    displayedJobs.find((j) => j.id === selectedJobId) || displayedJobs[0];

  // Parse result_summary JSON if present
  let jobSummary: {
    mode?: string;
    deterministic_count?: number;
    prompted_count?: number;
    processing_time_ms?: number;
    logs?: string[];
  } = {};

  if (activeJob?.result_summary) {
    try {
      jobSummary = JSON.parse(activeJob.result_summary);
    } catch (e) {
      console.error("Failed to parse result_summary:", e);
    }
  }

  const logs = jobSummary.logs || [];

  // Auto scroll effect
  useEffect(() => {
    if (autoScroll && terminalEndRef.current) {
      terminalEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs, activeJob, autoScroll]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-black/80 backdrop-blur-md animate-in fade-in duration-200">
      <div
        className="w-full max-w-5xl h-[85vh] flex flex-col rounded-3xl border shadow-2xl overflow-hidden"
        style={{
          backgroundColor: "#0d0e12",
          borderColor: "var(--color-border)",
          boxShadow:
            "0 25px 50px -12px rgba(0,0,0,0.8), 0 0 40px rgba(234,88,12,0.1)",
        }}
      >
        {/* Header Bar */}
        <div
          className="px-5 py-4 border-b flex items-center justify-between gap-4 shrink-0"
          style={{
            backgroundColor: "var(--color-surface-hover)",
            borderColor: "var(--color-border)",
          }}
        >
          <div className="flex items-center gap-3 min-w-0">
            <div className="p-2 rounded-2xl bg-gradient-to-tr from-[var(--color-accent)] to-amber-500 text-white shadow-md shadow-orange-500/20">
              <Terminal className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3
                  className="text-base font-bold font-outfit"
                  style={{ color: "var(--color-text)" }}
                >
                  Translator Memory Engine Logs
                </h3>
                <span
                  className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-mono font-bold border"
                  style={{
                    backgroundColor: "var(--color-box-bg)",
                    color: "var(--color-success)",
                    borderColor: "var(--color-border)",
                  }}
                >
                  <span
                    className="w-1.5 h-1.5 rounded-full animate-pulse"
                    style={{ backgroundColor: "var(--color-success)" }}
                  ></span>
                  LIVE TELEMETRY
                </span>
              </div>
              <p className="text-xs text-[var(--color-text-muted)] truncate">
                Real-time execution pipeline, terminology prepasses, and AI
                context rewrites
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={() => refetch()}
              className="p-2 rounded-xl border border-[var(--color-border)] hover:bg-white/5 text-[var(--color-text-muted)] transition-colors cursor-pointer"
              title="Refresh logs now"
            >
              <RefreshCw
                className={`w-4 h-4 ${isRefetching ? "animate-spin text-[var(--color-accent)]" : ""}`}
              />
            </button>
            <button
              onClick={onClose}
              className="p-2 rounded-xl border border-[var(--color-border)] hover:bg-white/10 text-[var(--color-text-muted)] hover:text-white transition-colors cursor-pointer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Filter & Subheader */}
        <div
          className="px-5 py-2.5 border-b bg-white/[0.02] flex flex-wrap items-center justify-between gap-3 text-xs"
          style={{ borderColor: "var(--color-border)" }}
        >
          <div className="flex items-center gap-2">
            <span className="text-[var(--color-text-muted)] font-medium">
              Scope:
            </span>
            <button
              onClick={() => setFilterMode("all")}
              className={`px-3 py-1 rounded-lg font-semibold transition-all cursor-pointer ${
                filterMode === "all"
                  ? "bg-[var(--color-accent)] text-white shadow-sm"
                  : "bg-white/5 text-[var(--color-text-muted)] hover:bg-white/10"
              }`}
            >
              All Novel Jobs ({novelJobs.length})
            </button>
            {chapterId && (
              <button
                onClick={() => setFilterMode("chapter")}
                className={`px-3 py-1 rounded-lg font-semibold transition-all cursor-pointer flex items-center gap-1.5 ${
                  filterMode === "chapter"
                    ? "bg-[var(--color-accent)] text-white shadow-sm"
                    : "bg-white/5 text-[var(--color-text-muted)] hover:bg-white/10"
                }`}
              >
                <span>Current Ch. #{chapterId}</span>
              </button>
            )}
          </div>

          <div className="flex items-center gap-4 text-[var(--color-text-muted)]">
            <div className="flex items-center gap-1.5">
              <Cpu className="w-3.5 h-3.5" style={{ color: "var(--color-warning)" }} />
              <span>
                Engine Status:{" "}
                <strong style={{ color: "var(--color-text)" }}>Active (Worker Pool)</strong>
              </span>
            </div>
          </div>
        </div>

        {/* Main Split Content */}
        <div className="flex-1 grid grid-cols-1 md:grid-cols-12 min-h-0 divide-y md:divide-y-0 md:divide-x divide-[var(--color-border)]">
          {/* Left Sidebar: Jobs List */}
          <div className="md:col-span-4 lg:col-span-3 flex flex-col min-h-0 bg-black/20 overflow-y-auto p-3 gap-2">
            <div className="text-xs font-bold text-[var(--color-text-muted)] px-2 py-1 uppercase tracking-wider font-mono flex items-center justify-between">
              <span>Execution History</span>
              <span>{displayedJobs.length}</span>
            </div>

            {isLoading ? (
              <div className="flex-1 flex flex-col items-center justify-center text-center p-6 text-[var(--color-text-muted)]">
                <RefreshCw className="w-6 h-6 animate-spin mb-2 opacity-50" />
                <span className="text-xs">Loading telemetry...</span>
              </div>
            ) : displayedJobs.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center text-center p-6 text-[var(--color-text-muted)]">
                <Layers className="w-8 h-8 mb-2 opacity-30" />
                <span className="text-xs">No processing jobs logged yet.</span>
                <span className="text-[10px] opacity-60 mt-1">
                  Press "Reprocess" or "Process" on any chapter to start!
                </span>
              </div>
            ) : (
              displayedJobs.map((job) => {
                const isSelected = activeJob?.id === job.id;
                let summary: any = {};
                if (job.result_summary) {
                  try {
                    summary = JSON.parse(job.result_summary);
                  } catch (e) {}
                }

                return (
                  <button
                    key={job.id}
                    onClick={() => setSelectedJobId(job.id)}
                    className={`p-3 rounded-2xl text-left border transition-all cursor-pointer flex flex-col gap-1.5 ${
                      isSelected
                        ? "bg-white/10 border-[var(--color-accent)] shadow-md"
                        : "bg-white/[0.02] border-white/5 hover:bg-white/[0.05] hover:border-white/10"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-bold flex items-center gap-1.5" style={{ color: "var(--color-text)" }}>
                        <span className="font-mono" style={{ color: "var(--color-warning)" }}>
                          #{job.id}
                        </span>
                        <span>Ch. {job.chapter_number ?? job.chapter_id}</span>
                      </span>

                      <span
                        className="text-[10px] px-2 py-0.5 rounded-full font-bold font-mono tracking-wider uppercase flex items-center gap-1 border"
                        style={{
                          backgroundColor:
                            job.status === "completed"
                              ? "var(--color-box-bg)"
                              : job.status === "running"
                                ? "var(--color-warning-subtle)"
                                : job.status === "failed"
                                  ? "var(--color-box-bg)"
                                  : "var(--color-box-bg)",
                          color:
                            job.status === "completed"
                              ? "var(--color-success)"
                              : job.status === "running"
                                ? "var(--color-warning)"
                                : job.status === "failed"
                                  ? "var(--color-error)"
                                  : "var(--color-text-muted)",
                          borderColor: "var(--color-border)",
                        }}
                      >
                        {job.status === "completed" ? (
                          <>
                            <CheckCircle2 className="w-3 h-3" /> Done
                          </>
                        ) : job.status === "running" ? (
                          <>
                            <RefreshCw className="w-3 h-3 animate-spin" />{" "}
                            Running
                          </>
                        ) : job.status === "failed" ? (
                          <>
                            <AlertCircle className="w-3 h-3" /> Failed
                          </>
                        ) : (
                          <Clock className="w-3 h-3" />
                        )}
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-[11px] text-[var(--color-text-muted)]">
                      <span className="capitalize font-mono text-[10px]">
                        {job.job_type} • {summary.mode || "pipeline"}
                      </span>
                      <span className="font-mono">
                        {summary.processing_time_ms
                          ? `${summary.processing_time_ms}ms`
                          : job.started_at
                            ? new Date(job.started_at).toLocaleTimeString([], {
                                hour: "2-digit",
                                minute: "2-digit",
                                second: "2-digit",
                              })
                            : ""}
                      </span>
                    </div>
                  </button>
                );
              })
            )}
          </div>

          {/* Right Area: Terminal Logs & Metrics */}
          <div className="md:col-span-8 lg:col-span-9 flex flex-col min-h-0 bg-[#07080a]">
            {activeJob ? (
              <>
                {/* Job Metrics Bar */}
                <div className="px-5 py-3 border-b border-white/5 bg-white/[0.015] flex flex-wrap items-center justify-between gap-4 text-xs">
                  <div className="flex items-center gap-4 flex-wrap">
                    <div>
                      <span className="text-[var(--color-text-muted)] block text-[10px] uppercase font-mono">
                        Status
                      </span>
                      <span
                        className="font-bold uppercase font-mono"
                        style={{
                          color:
                            activeJob.status === "completed"
                              ? "var(--color-success)"
                              : activeJob.status === "running"
                                ? "var(--color-warning)"
                                : activeJob.status === "failed"
                                  ? "var(--color-error)"
                                  : "var(--color-text)",
                        }}
                      >
                        {activeJob.status}
                      </span>
                    </div>

                    <div>
                      <span className="text-[var(--color-text-muted)] block text-[10px] uppercase font-mono">
                        Pre-Pass Replacements
                      </span>
                      <span className="font-bold font-mono" style={{ color: "var(--color-warning)" }}>
                        {jobSummary.deterministic_count ?? 0} terms matched
                      </span>
                    </div>

                    <div>
                      <span className="text-[var(--color-text-muted)] block text-[10px] uppercase font-mono">
                        Context Corrections
                      </span>
                      <span className="font-bold text-sky-400 font-mono flex items-center gap-1">
                        <Sparkles className="w-3 h-3" />
                        {jobSummary.prompted_count ?? 0} semantic rules
                      </span>
                    </div>

                    <div>
                      <span className="text-[var(--color-text-muted)] block text-[10px] uppercase font-mono">
                        Processing Time
                      </span>
                      <span className="font-bold text-white font-mono">
                        {jobSummary.processing_time_ms
                          ? `${jobSummary.processing_time_ms} ms`
                          : activeJob.status === "running"
                            ? "Running..."
                            : "N/A"}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <label className="flex items-center gap-1.5 text-[11px] text-[var(--color-text-muted)] cursor-pointer select-none">
                      <input
                        type="checkbox"
                        checked={autoScroll}
                        onChange={(e) => setAutoScroll(e.target.checked)}
                        className="rounded bg-white/10 border-white/20 text-[var(--color-accent)] focus:ring-0"
                      />
                      <span>Auto-scroll</span>
                    </label>
                  </div>
                </div>

                {/* Terminal Window */}
                <div
                  className="flex-1 overflow-y-auto p-5 font-mono text-xs leading-relaxed space-y-2 selection:bg-[var(--color-accent)]/30 border-t"
                  style={{
                    backgroundColor: "var(--color-box-bg)",
                    borderColor: "var(--color-border)",
                    color: "var(--color-text)",
                  }}
                >
                  <div
                    className="pb-2 border-b mb-3"
                    style={{
                      borderColor: "var(--color-border)",
                      color: "var(--color-text-muted)",
                    }}
                  >
                    === translator_memory_engine telemetry session [Job #
                    {activeJob.id}] ===
                  </div>

                  {logs.length === 0 ? (
                    <div className="py-12 text-center text-[var(--color-text-muted)]">
                      {activeJob.status === "running" ? (
                        <div className="flex flex-col items-center gap-3">
                          <RefreshCw className="w-6 h-6 animate-spin text-[var(--color-accent)]" />
                          <span>
                            Engine pipeline initializing for Chapter{" "}
                            {activeJob.chapter_number ?? activeJob.chapter_id}
                            ...
                          </span>
                        </div>
                      ) : (
                        <span>
                          No detailed log stream available for this job record.
                        </span>
                      )}
                    </div>
                  ) : (
                    logs.map((line, idx) => {
                      const isError =
                        line.includes("❌") ||
                        line.includes("ERROR") ||
                        line.includes("failed");
                      const isSuccess =
                        line.includes("✅") ||
                        line.includes("completed successfully");
                      const isEngine =
                        line.includes("📚") ||
                        line.includes("⚡") ||
                        line.includes("🧹");

                      return (
                        <div
                          key={idx}
                          className="flex items-start gap-2.5 py-0.5 rounded px-2"
                          style={{
                            backgroundColor:
                              isError || isSuccess
                                ? "var(--color-surface)"
                                : "transparent",
                            color: isError
                              ? "var(--color-error)"
                              : isSuccess
                                ? "var(--color-success)"
                                : isEngine
                                  ? "var(--color-warning)"
                                  : "var(--color-text)",
                            borderLeft: isError
                              ? "2px solid var(--color-error)"
                              : isSuccess
                                ? "2px solid var(--color-success)"
                                : isEngine
                                  ? "2px solid var(--color-warning)"
                                  : "none",
                          }}
                        >
                          <span
                            className="select-none shrink-0 mt-0.5"
                            style={{
                              color: "var(--color-text-muted)",
                              opacity: 0.7,
                            }}
                          >
                            {idx + 1 < 10 ? `0${idx + 1}` : idx + 1}
                          </span>
                          <span className="break-all whitespace-pre-wrap flex-1">
                            {line}
                          </span>
                        </div>
                      );
                    })
                  )}

                  {activeJob.error_message &&
                    !logs.some((l) => l.includes(activeJob.error_message!)) && (
                      <div className="bg-red-500/15 border border-red-500/40 rounded-xl p-4 text-red-300 mt-4 space-y-1">
                        <div className="font-bold flex items-center gap-2">
                          <AlertCircle className="w-4 h-4 text-red-400" />
                          <span>Exception Stack Trace & Error Detail:</span>
                        </div>
                        <p className="font-mono text-[11px] break-all">
                          {activeJob.error_message}
                        </p>
                      </div>
                    )}

                  <div ref={terminalEndRef} />
                </div>
              </>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center p-8 text-center text-[var(--color-text-muted)]">
                <Terminal className="w-12 h-12 mb-3 opacity-20" />
                <span className="text-sm font-semibold text-white">
                  Select a job from the left to view live telemetry
                </span>
                <span className="text-xs opacity-60 mt-1">
                  Watch exact pre-pass translations and LLM context polish in
                  action.
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Footer Info Box */}
        <div
          className="px-5 py-3 border-t bg-black/40 flex flex-wrap items-center justify-between gap-3 text-[11px] text-[var(--color-text-muted)] shrink-0"
          style={{ borderColor: "var(--color-border)" }}
        >
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: "var(--color-warning)" }}></span>
            <span>
              <strong>How it works:</strong> When you press <em>Reprocess</em>,
              the backend queues an async pipeline worker that cleans text,
              loads current AI terminology rules, runs deterministic
              replacements, and performs contextual LLM refinement.
            </span>
          </div>
          <div className="font-mono opacity-70">v2.4.0 Engine Telemetry</div>
        </div>
      </div>
    </div>
  );
}
