import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type Chapter } from "../api/client";
import { PasteForm } from "../components/PasteForm";
import { Header } from "../components/Header";
import { formatPolicyAction, formatAliasesList, isIdentityPolicy } from "../utils/formatters";
import { BottomNav, type NavTab } from "../components/BottomNav";
import {
  BookOpen,
  Sparkles,
  Layers,
  Database,
  Plus,
  Play,
  ArrowLeft,
  Search,
  RefreshCw,
  AlertCircle,
  FileText,
  ChevronDown,
  ChevronUp,
  Terminal,
} from "lucide-react";
import { EngineInspectorModal } from "../components/EngineInspectorModal";

// Helper to generate deterministic rich gradient cover matching NovelCard
function getBookCoverStyle(id: number, name: string) {
  const gradients = [
    { from: "#3b82f6", to: "#1d4ed8", accent: "#60a5fa" },
    { from: "#f97316", to: "#c2410c", accent: "#fb923c" },
    { from: "#8b5cf6", to: "#5b21b6", accent: "#a78bfa" },
    { from: "#10b981", to: "#047857", accent: "#34d399" },
    { from: "#ec4899", to: "#be185d", accent: "#f472b6" },
    { from: "#6366f1", to: "#312e81", accent: "#818cf8" },
  ];
  return gradients[(id + name.length) % gradients.length];
}

export function NovelView() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const novelId = parseInt(id!, 10);

  const [activeTab, setActiveTab] = useState<
    "catalog" | "policies" | "glossary" | "import"
  >("catalog");
  const [activeBottomNav, setActiveBottomNav] = useState<NavTab>("bookshelf");
  const [isProcessing, setIsProcessing] = useState(false);
  const [reprocessingId, setReprocessingId] = useState<number | null>(null);
  const [chapterSearch, setChapterSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("asc");
  const [showInspector, setShowInspector] = useState(false);
  const [inspectChapterId, setInspectChapterId] = useState<number | null>(null);

  const { data: novel, isLoading: novelLoading } = useQuery({
    queryKey: ["novel", novelId],
    queryFn: () => api.getNovel(novelId),
  });

  const { data: chapters, isLoading: chaptersLoading } = useQuery({
    queryKey: ["chapters", novelId],
    queryFn: () => api.listChapters(novelId),
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return false;
      const hasProcessing = data.some(
        (ch) => ch.status === "processing" || ch.status === "pending",
      );
      return hasProcessing ? 2000 : false;
    },
  });

  const { data: policies, isLoading: policiesLoading } = useQuery({
    queryKey: ["policies", novelId],
    queryFn: () => api.listPolicies(novelId),
    enabled: activeTab === "policies",
  });

  const { data: glossary, isLoading: glossaryLoading } = useQuery({
    queryKey: ["glossary", novelId],
    queryFn: () => api.listGlossary(novelId),
    enabled: activeTab === "glossary",
  });

  const createAndProcessMutation = useMutation({
    mutationFn: async (data: {
      chapter_number: number;
      source_type: string;
      raw_text: string;
    }) => {
      const chapter = await api.createChapter(novelId, data);
      return api.processChapter(chapter.id);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["novel", novelId] });
      queryClient.invalidateQueries({ queryKey: ["chapters", novelId] });
      setIsProcessing(false);
      // Switch back to catalog or navigate to reading after import!
      setActiveTab("catalog");
    },
    onError: () => {
      setIsProcessing(false);
    },
  });

  const handleProcess = async (data: {
    chapter_number: number;
    source_type: string;
    raw_text: string;
  }) => {
    setIsProcessing(true);
    createAndProcessMutation.mutate(data);
  };

  const handleReprocess = async (chapterId: number, chNum: number) => {
    if (!confirm(`Reprocess Chapter ${chNum} with latest AI memory policies?`))
      return;
    setReprocessingId(chapterId);
    try {
      await api.reprocessChapter(chapterId);
      queryClient.invalidateQueries({ queryKey: ["chapters", novelId] });
      queryClient.invalidateQueries({ queryKey: ["novel", novelId] });
      setInspectChapterId(chapterId);
      setShowInspector(true);
    } catch (err) {
      console.error("Reprocess failed:", err);
    } finally {
      setReprocessingId(null);
    }
  };

  if (novelLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--color-bg)]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 rounded-full border-2 border-t-[var(--color-accent)] border-white/20 animate-spin" />
          <p className="text-xs text-[var(--color-text-muted)] font-medium">
            Loading Webnovel studio...
          </p>
        </div>
      </div>
    );
  }

  if (!novel) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-4 bg-[var(--color-bg)] text-[var(--color-text)]">
        <AlertCircle className="w-12 h-12 text-[var(--color-error)]" />
        <h2 className="text-lg font-bold">Novel Not Found</h2>
        <button
          onClick={() => navigate("/")}
          className="px-4 py-2 rounded-xl bg-[var(--color-surface)] border border-[var(--color-border)] text-xs font-semibold cursor-pointer"
        >
          &larr; Back to Bookshelf
        </button>
      </div>
    );
  }

  const cover = getBookCoverStyle(novel.id, novel.name);

  // Group chapters by chapter_number
  const grouped = chapters
    ? chapters.reduce<Record<number, Chapter[]>>((acc, ch) => {
        if (!acc[ch.chapter_number]) acc[ch.chapter_number] = [];
        acc[ch.chapter_number].push(ch);
        return acc;
      }, {})
    : {};

  const allSortedNums = Object.keys(grouped)
    .map(Number)
    .sort((a, b) => (sortOrder === "desc" ? b - a : a - b));

  const filteredChapterNums = allSortedNums.filter((chNum) => {
    const entries = grouped[chNum];
    const mtl = entries.find((e) => e.source_type === "mtl");
    if (!mtl) return true;

    if (chapterSearch && !String(chNum).includes(chapterSearch)) return false;
    if (statusFilter === "completed" && mtl.status !== "completed")
      return false;
    if (
      statusFilter === "processing" &&
      mtl.status !== "processing" &&
      mtl.status !== "pending"
    )
      return false;
    if (statusFilter === "failed" && mtl.status !== "failed") return false;
    return true;
  });

  const firstCompleted = chapters?.find(
    (c) => c.status === "completed" && c.source_type === "mtl",
  );
  const nextNumberToSuggest =
    chapters && chapters.length > 0
      ? Math.max(...chapters.map((c) => c.chapter_number)) + 1
      : 1;

  const flagMap: Record<string, string> = {
    korean: "🇰🇷 Korean (KR)",
    chinese: "🇨🇳 Chinese (CN)",
    japanese: "🇯🇵 Japanese (JP)",
  };

  return (
    <div className="min-h-screen flex flex-col md:pl-64 transition-all duration-200 bg-[var(--color-bg)] text-[var(--color-text)] pb-24">
      {/* Top Application Header */}
      <Header onOpenCreateNovel={() => navigate("/")} />

      {/* Main Content Area */}
      <main className="flex-1 max-w-6xl mx-auto w-full">
        {/* Webnovel Book Detail Header / Cover Hero */}
        <div
          className="relative overflow-hidden border-b pb-8 pt-6 px-4 md:px-8 glass-surface"
          style={{ borderColor: "var(--color-border)" }}
        >
          {/* Blurred Background Glow */}
          <div
            className="absolute -top-32 -right-32 w-96 h-96 rounded-full blur-3xl opacity-15 pointer-events-none"
            style={{ backgroundColor: cover.from }}
          />

          {/* Back Nav */}
          <button
            onClick={() => navigate("/")}
            className="inline-flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-xl border mb-6 transition-all hover:bg-white/5 cursor-pointer relative z-10"
            style={{
              borderColor: "var(--color-border)",
              color: "var(--color-text-muted)",
            }}
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Bookshelf</span>
          </button>

          <div className="flex flex-col sm:flex-row items-center sm:items-start gap-6 relative z-10">
            {/* Book Cover Container */}
            <div
              className="w-32 h-48 sm:w-36 sm:h-52 shrink-0 rounded-2xl shadow-2xl flex flex-col justify-between p-3.5 relative overflow-hidden transition-transform hover:scale-105"
              style={{
                background: `linear-gradient(135deg, ${cover.from} 0%, ${cover.to} 100%)`,
              }}
            >
              <div className="absolute top-0 bottom-0 left-3 w-0.5 bg-white/20" />
              <div className="flex justify-between items-center z-10">
                <span className="text-[10px] font-black uppercase px-1.5 py-0.5 rounded bg-black/40 text-white backdrop-blur-sm font-mono">
                  STUDIO
                </span>
                <Sparkles className="w-4 h-4 text-white/90" />
              </div>
              <div className="z-10 mt-auto">
                <p className="text-xs sm:text-sm font-black text-white leading-tight line-clamp-3 drop-shadow-md font-outfit">
                  {novel.title || novel.name}
                </p>
              </div>
            </div>

            {/* Book Info and Action Button Bar */}
            <div className="flex-1 text-center sm:text-left min-w-0 flex flex-col justify-between h-full">
              <div>
                <div className="flex items-center justify-center sm:justify-start gap-2 mb-2 flex-wrap">
                  <span
                    className="text-xs font-semibold px-2.5 py-0.5 rounded-md border"
                    style={{
                      backgroundColor: "var(--color-surface)",
                      borderColor: "var(--color-border)",
                      color: "var(--color-text-muted)",
                    }}
                  >
                    {flagMap[novel.source_language.toLowerCase()] ||
                      novel.source_language}
                  </span>
                  <span
                    className="text-xs font-semibold px-2.5 py-0.5 rounded-md flex items-center gap-1"
                    style={{
                      backgroundColor: "var(--color-ai-glow)",
                      color: "var(--color-ai)",
                    }}
                  >
                    <Layers className="w-3.5 h-3.5" />
                    <span>Translator Memory Enforcing</span>
                  </span>
                </div>

                <h1 className="text-2xl sm:text-3xl lg:text-4xl font-black leading-tight font-outfit mb-1">
                  {novel.name}
                </h1>

                {novel.title && novel.title !== novel.name && (
                  <p
                    className="text-sm sm:text-base opacity-75 max-w-xl"
                    style={{ color: "var(--color-text-muted)" }}
                  >
                    {novel.title}
                  </p>
                )}
              </div>

              {/* Stats & Quick Actions Bar */}
              <div
                className="mt-6 pt-5 border-t flex flex-col sm:flex-row items-center justify-between gap-4"
                style={{ borderColor: "var(--color-border)" }}
              >
                <div
                  className="flex items-center gap-5 text-xs font-semibold"
                  style={{ color: "var(--color-text-muted)" }}
                >
                  <span className="flex items-center gap-1.5">
                    <BookOpen className="w-4 h-4 text-[var(--color-accent)]" />
                    <strong style={{ color: "var(--color-text)" }}>
                      {novel.chapter_count}
                    </strong>{" "}
                    Chapters
                  </span>
                  <span className="flex items-center gap-1.5">
                    <Layers className="w-4 h-4 text-[var(--color-ai)]" />
                    <strong style={{ color: "var(--color-text)" }}>
                      {novel.policy_count}
                    </strong>{" "}
                    Policies
                  </span>
                  <span className="flex items-center gap-1.5">
                    <Database className="w-4 h-4" style={{ color: "var(--color-success)" }} />
                    <strong style={{ color: "var(--color-text)" }}>
                      {novel.glossary_count}
                    </strong>{" "}
                    Glossary
                  </span>
                </div>

                {/* Main Read / Add Action Buttons */}
                <div className="flex items-center gap-2.5 w-full sm:w-auto">
                  {firstCompleted ? (
                    <button
                      onClick={() => navigate(`/read/${firstCompleted.id}`)}
                      className="flex-1 sm:flex-initial px-5 py-2.5 rounded-xl text-xs font-bold text-white shadow-lg flex items-center justify-center gap-2 transition-transform hover:scale-105 active:scale-95 cursor-pointer glow-accent"
                      style={{
                        background:
                          "linear-gradient(135deg, var(--color-accent) 0%, #ea580c 100%)",
                      }}
                    >
                      <Play className="w-4 h-4 fill-white" />
                      <span>
                        Start Reading Ch. {firstCompleted.chapter_number}
                      </span>
                    </button>
                  ) : (
                    <button
                      onClick={() => setActiveTab("import")}
                      className="flex-1 sm:flex-initial px-5 py-2.5 rounded-xl text-xs font-bold text-white shadow-lg flex items-center justify-center gap-2 transition-transform hover:scale-105 active:scale-95 cursor-pointer glow-accent"
                      style={{
                        background:
                          "linear-gradient(135deg, var(--color-accent) 0%, #ea580c 100%)",
                      }}
                    >
                      <Plus className="w-4 h-4" strokeWidth={2.5} />
                      <span>Import Chapter 1</span>
                    </button>
                  )}

                  <button
                    onClick={() => {
                      setInspectChapterId(null);
                      setShowInspector(true);
                    }}
                    className="px-4 py-2.5 rounded-xl text-xs font-bold border transition-all hover:bg-white/10 cursor-pointer flex items-center gap-1.5 shadow-sm"
                    style={{
                      borderColor: "var(--color-border)",
                      color: "var(--color-accent)",
                      backgroundColor: "rgba(234, 88, 12, 0.1)",
                    }}
                    title="Live Translator Memory Engine Logs"
                  >
                    <Terminal className="w-4 h-4" />
                    <span>Engine Logs</span>
                  </button>

                  <button
                    onClick={() =>
                      setActiveTab(
                        activeTab === "import" ? "catalog" : "import",
                      )
                    }
                    className="px-4 py-2.5 rounded-xl text-xs font-bold border transition-colors hover:bg-white/5 cursor-pointer flex items-center gap-1.5"
                    style={{
                      borderColor:
                        activeTab === "import"
                          ? "var(--color-accent)"
                          : "var(--color-border)",
                      color:
                        activeTab === "import"
                          ? "var(--color-accent)"
                          : "var(--color-text)",
                    }}
                  >
                    <Plus className="w-4 h-4" />
                    <span>
                      {activeTab === "import" ? "Hide Studio" : "Add Chapter"}
                    </span>
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* SPA Sub-Tabs Bar inside Book Detail */}
          <div
            className="mt-8 flex gap-1.5 overflow-x-auto no-scrollbar border-b pb-0"
            style={{ borderColor: "var(--color-border)" }}
          >
            {[
              {
                id: "catalog",
                label: `Catalog (${novel.chapter_count})`,
                icon: BookOpen,
              },
              {
                id: "policies",
                label: `AI Policies (${novel.policy_count})`,
                icon: Layers,
              },
              {
                id: "glossary",
                label: `Glossary Matrix (${novel.glossary_count})`,
                icon: Database,
              },
              { id: "import", label: "Studio Import (+)", icon: Plus },
            ].map((tab) => {
              const Icon = tab.icon;
              const isSel = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id as any)}
                  className={`flex items-center gap-2 px-4 py-3 text-xs md:text-sm font-bold border-b-2 transition-all shrink-0 cursor-pointer ${
                    isSel
                      ? "border-[var(--color-accent)] text-[var(--color-accent)]"
                      : "border-transparent text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Tab Content Area */}
        <div className="p-4 md:p-8 animate-fade-in">
          {/* TAB 1: Catalog / Chapters View */}
          {activeTab === "catalog" && (
            <div className="space-y-4">
              {/* Filter and Sort Bar */}
              <div
                className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 p-4 rounded-2xl border bg-black/10"
                style={{ borderColor: "var(--color-border)" }}
              >
                <div className="flex items-center gap-2 overflow-x-auto no-scrollbar">
                  {[
                    { id: "all", label: "All Status" },
                    { id: "completed", label: "✨ Refined Done" },
                    { id: "processing", label: "⏳ Processing" },
                    { id: "failed", label: "⚠️ Failed" },
                  ].map((s) => (
                    <button
                      key={s.id}
                      onClick={() => setStatusFilter(s.id)}
                      className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all shrink-0 cursor-pointer ${
                        statusFilter === s.id
                          ? "bg-[var(--color-surface-hover)] text-[var(--color-text)] border border-[var(--color-border)]"
                          : "opacity-60 hover:opacity-100"
                      }`}
                    >
                      {s.label}
                    </button>
                  ))}
                </div>

                <div className="flex items-center gap-2">
                  <div className="relative flex-1 sm:w-48">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 opacity-50 text-[var(--color-text-muted)]" />
                    <input
                      type="text"
                      value={chapterSearch}
                      onChange={(e) => setChapterSearch(e.target.value)}
                      placeholder="Ch. number..."
                      className="w-full pl-8 pr-3 py-1.5 rounded-xl text-xs border bg-[var(--color-bg)] text-[var(--color-text)] focus:outline-none focus:ring-1"
                      style={{ borderColor: "var(--color-border)" }}
                    />
                  </div>

                  <button
                    onClick={() =>
                      setSortOrder(sortOrder === "desc" ? "asc" : "desc")
                    }
                    className="px-3 py-1.5 rounded-xl border text-xs font-bold flex items-center gap-1.5 shrink-0 transition-colors hover:bg-white/5 cursor-pointer"
                    style={{
                      borderColor: "var(--color-border)",
                      color: "var(--color-text)",
                    }}
                  >
                    <span>
                      Sort:{" "}
                      {sortOrder === "asc"
                        ? "Oldest (1 → N)"
                        : "Newest (N → 1)"}
                    </span>
                    {sortOrder === "asc" ? (
                      <ChevronUp className="w-3.5 h-3.5 text-[var(--color-accent)]" />
                    ) : (
                      <ChevronDown className="w-3.5 h-3.5 text-[var(--color-accent)]" />
                    )}
                  </button>
                </div>
              </div>

              {/* Chapters List */}
              {chaptersLoading ? (
                <div className="py-16 text-center text-xs opacity-60">
                  Loading chapter catalog...
                </div>
              ) : filteredChapterNums.length === 0 ? (
                <div
                  className="p-12 text-center rounded-3xl border glass-surface"
                  style={{ borderColor: "var(--color-border)" }}
                >
                  <FileText className="w-10 h-10 mx-auto mb-3 text-[var(--color-accent)] opacity-60" />
                  <h3 className="text-base font-bold">No Chapters Found</h3>
                  <p className="text-xs opacity-70 mt-1">
                    {chapterSearch || statusFilter !== "all"
                      ? "No chapters match your search query."
                      : "No chapters have been imported yet."}
                  </p>
                  <button
                    onClick={() => setActiveTab("import")}
                    className="mt-4 px-4 py-2 rounded-xl bg-[var(--color-accent)] text-white text-xs font-bold cursor-pointer"
                  >
                    + Import First Chapter
                  </button>
                </div>
              ) : (
                <div className="flex flex-col gap-2.5">
                  {filteredChapterNums.map((chNum) => {
                    const entries = grouped[chNum];
                    const mtl = entries.find((e) => e.source_type === "mtl");
                    const orig = entries.find(
                      (e) => e.source_type === "original",
                    );
                    const isReprocessing = mtl
                      ? reprocessingId === mtl.id
                      : false;
                    const isItemProcessing =
                      mtl &&
                      (mtl.status === "processing" || mtl.status === "pending");

                    return (
                      <div
                        key={chNum}
                        onClick={() => {
                          if (mtl?.status === "completed") {
                            navigate(`/read/${mtl.id}`);
                          }
                        }}
                        className={`p-4 rounded-2xl border transition-all flex items-center justify-between gap-3 ${
                          mtl?.status === "completed"
                            ? "hover:border-[var(--color-accent)] cursor-pointer hover:shadow-md"
                            : "opacity-90"
                        }`}
                        style={{
                          backgroundColor: "var(--color-surface)",
                          borderColor: "var(--color-border)",
                        }}
                      >
                        <div className="flex items-center gap-3.5 min-w-0">
                          <div
                            className={`w-10 h-10 rounded-xl flex items-center justify-center font-bold text-sm shrink-0 ${
                              mtl?.status === "completed"
                                ? "bg-[var(--color-accent-glow)] text-[var(--color-accent)]"
                                : mtl?.status === "failed"
                                  ? "bg-red-500/20 text-red-400"
                                  : "bg-black/20 text-[var(--color-text-muted)]"
                            }`}
                          >
                            {chNum}
                          </div>

                          <div className="min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span
                                className="text-sm font-bold leading-none font-outfit"
                                style={{ color: "var(--color-text)" }}
                              >
                                Chapter {chNum}
                              </span>

                              {orig && (
                                <span className="text-[10px] px-1.5 py-0.5 rounded border font-mono opacity-80" style={{ backgroundColor: "var(--color-box-bg)", borderColor: "var(--color-border)", color: "var(--color-text)" }}>
                                  OG TL (Ref)
                                </span>
                              )}

                              {mtl && (
                                <span
                                  className="text-[10px] px-2 py-0.5 rounded font-bold uppercase tracking-wider font-mono border"
                                  style={{
                                    backgroundColor:
                                      mtl.status === "completed"
                                        ? "var(--color-box-bg)"
                                        : mtl.status === "failed"
                                          ? "var(--color-box-bg)"
                                          : "var(--color-warning-subtle)",
                                    color:
                                      mtl.status === "completed"
                                        ? "var(--color-success)"
                                        : mtl.status === "failed"
                                          ? "var(--color-error)"
                                          : "var(--color-warning)",
                                    borderColor: "var(--color-border)",
                                  }}
                                >
                                  {mtl.status === "completed"
                                    ? "Refined ✨"
                                    : mtl.status === "failed"
                                      ? "Failed"
                                      : "Processing..."}
                                </span>
                              )}
                            </div>

                            <span
                              className="text-[11px] opacity-60 block mt-1 line-clamp-1"
                              style={{ color: "var(--color-text-muted)" }}
                            >
                              {mtl?.status === "completed"
                                ? "AI translation memory injected & polished"
                                : mtl?.status === "processing"
                                  ? "Applying rules & rewriting..."
                                  : "Awaiting processing"}
                            </span>
                          </div>
                        </div>

                        {/* Action Buttons */}
                        <div
                          className="flex items-center gap-1.5 shrink-0"
                          onClick={(e) => e.stopPropagation()}
                        >
                          {mtl?.status === "completed" && (
                            <button
                              onClick={() => navigate(`/read/${mtl.id}`)}
                              className="px-3 py-1.5 rounded-xl text-xs font-bold text-white transition-transform hover:scale-105 active:scale-95 cursor-pointer flex items-center gap-1 shadow-sm"
                              style={{
                                background:
                                  "linear-gradient(135deg, var(--color-accent) 0%, #ea580c 100%)",
                              }}
                            >
                              <Play className="w-3 h-3 fill-white" />
                              <span className="hidden sm:inline">Read</span>
                            </button>
                          )}

                          {mtl && (
                            <button
                              onClick={() => {
                                setInspectChapterId(mtl.id);
                                setShowInspector(true);
                              }}
                              title="View Engine Logs & Replacements"
                              className="p-2 rounded-xl text-xs font-semibold border transition-colors cursor-pointer"
                              style={{
                                backgroundColor: "var(--color-box-bg)",
                                borderColor: "var(--color-border)",
                                color: "var(--color-text)",
                              }}
                            >
                              <Terminal className="w-3.5 h-3.5" />
                            </button>
                          )}

                          {mtl && !isItemProcessing && (
                            <button
                              onClick={() => handleReprocess(mtl.id, chNum)}
                              disabled={isReprocessing}
                              title="Reprocess Chapter with Latest AI Policies"
                              className="p-2 rounded-xl text-xs font-semibold border transition-colors hover:bg-white/5 cursor-pointer disabled:opacity-40"
                              style={{
                                borderColor: "var(--color-border)",
                                color: "var(--color-text-muted)",
                              }}
                            >
                              <RefreshCw
                                className={`w-3.5 h-3.5 ${isReprocessing ? "animate-spin" : ""}`}
                              />
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* TAB 2: Memory Policies Tab */}
          {activeTab === "policies" && (
            <div className="space-y-4">
              {policiesLoading ? (
                <div className="py-16 text-center text-xs opacity-60">
                  Loading translation memory rules...
                </div>
              ) : !policies || policies.length === 0 ? (
                <div
                  className="p-12 text-center rounded-3xl border glass-surface"
                  style={{ borderColor: "var(--color-border)" }}
                >
                  <Layers className="w-10 h-10 mx-auto mb-3 text-[var(--color-ai)] opacity-60" />
                  <h3 className="text-base font-bold">
                    No Policies Extracted Yet
                  </h3>
                  <p className="text-xs opacity-70 mt-1 max-w-md mx-auto">
                    When chapters are imported and refined, the AI automatically
                    learns formatting rules and terms specific to {novel.name}.
                  </p>
                </div>
              ) : (
                <div className="grid gap-3 sm:grid-cols-2">
                  {policies.map((p) => (
                    <div
                      key={p.id}
                      className="p-4 rounded-2xl border transition-all hover:border-[var(--color-ai)] flex flex-col justify-between gap-3"
                      style={{
                        backgroundColor: "var(--color-surface)",
                        borderColor: "var(--color-border)",
                      }}
                    >
                      <div>
                        <div className="flex items-center justify-between gap-2 mb-2">
                          <span
                            className="text-[10px] font-black uppercase px-2 py-0.5 rounded tracking-wider font-mono"
                            style={{
                              backgroundColor: "var(--color-ai-glow)",
                              color: "var(--color-ai)",
                            }}
                          >
                            {p.type || "RULE"}
                          </span>
                          <span className="text-[11px] font-mono opacity-70">
                            Confidence: {Math.round(p.confidence * 100)}%
                          </span>
                        </div>
                        <h4 className="text-sm font-bold font-outfit mb-1" style={{ color: "var(--color-text)" }}>
                          Trigger:{" "}
                          <span className="text-[var(--color-accent)] font-mono">
                            {p.trigger}
                          </span>
                        </h4>
                        {isIdentityPolicy(p.action, p.trigger) ? (
                          <div className="flex items-center gap-1.5 mt-2 text-xs font-sans" style={{ color: "var(--color-text)" }}>
                            <span className="px-2 py-0.5 rounded border font-mono text-[11px] opacity-90" style={{ backgroundColor: "var(--color-box-bg)", borderColor: "var(--color-border)", color: "var(--color-accent)" }}>
                              🔒 Protected Exact Canonical Entity
                            </span>
                          </div>
                        ) : (
                          <div
                            className="text-xs p-2.5 rounded-xl border-l-2 mt-2 leading-relaxed"
                            style={{ backgroundColor: "var(--color-box-bg)", borderColor: "var(--color-ai)", color: "var(--color-text)" }}
                          >
                            <strong
                              className="block text-[10px] uppercase opacity-65 mb-0.5"
                              style={{ color: "var(--color-ai)" }}
                            >
                              AI Enforcement Action
                            </strong>
                            {formatPolicyAction(p.action, p.trigger)}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* TAB 3: Glossary Terms Tab */}
          {activeTab === "glossary" && (
            <div className="space-y-4">
              {glossaryLoading ? (
                <div className="py-16 text-center text-xs opacity-60">
                  Loading glossary terms...
                </div>
              ) : !glossary || glossary.length === 0 ? (
                <div
                  className="p-12 text-center rounded-3xl border glass-surface"
                  style={{ borderColor: "var(--color-border)" }}
                >
                  <Database className="w-10 h-10 mx-auto mb-3 text-[var(--color-accent)] opacity-60" />
                  <h3 className="text-base font-bold">No Glossary Terms Yet</h3>
                  <p className="text-xs opacity-70 mt-1 max-w-md mx-auto">
                    Canonical entity names and martial/magical terminology will
                    populate here automatically.
                  </p>
                </div>
              ) : (
                <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3">
                  {glossary.map((g) => (
                    <div
                      key={g.id}
                      className="p-4 rounded-2xl border transition-all hover:border-[var(--color-accent)]"
                      style={{
                        backgroundColor: "var(--color-surface)",
                        borderColor: "var(--color-border)",
                      }}
                    >
                      <span
                        className="text-[10px] font-extrabold uppercase px-2 py-0.5 rounded tracking-wider block w-fit mb-2"
                        style={{
                          backgroundColor: "var(--color-accent-glow)",
                          color: "var(--color-accent)",
                        }}
                      >
                        {g.entity_type || "TERM"}
                      </span>
                      <h4 className="text-base font-black font-outfit mb-1">
                        {g.canonical}
                      </h4>
                      {formatAliasesList(g.aliases, g.canonical)}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* TAB 4: Studio Import View */}
          {activeTab === "import" && (
            <div className="max-w-2xl mx-auto">
              <PasteForm
                onSubmit={handleProcess}
                isProcessing={isProcessing}
                nextSuggestedNumber={nextNumberToSuggest}
                onCancel={() => setActiveTab("catalog")}
              />
            </div>
          )}
        </div>
      </main>

      {showInspector && (
        <EngineInspectorModal
          novelId={novelId}
          chapterId={inspectChapterId}
          onClose={() => setShowInspector(false)}
        />
      )}

      {/* Persistent SPA Bottom Dock */}
      <BottomNav
        activeTab={activeBottomNav}
        onSelectTab={(tab) => {
          setActiveBottomNav(tab);
          navigate("/");
        }}
      />
    </div>
  );
}
