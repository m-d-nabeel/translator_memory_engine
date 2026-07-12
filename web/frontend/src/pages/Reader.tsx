import { useEffect, useState, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { ReaderView } from "../components/ReaderView";
import { ReaderSettingsDrawer } from "../components/ReaderSettingsDrawer";
import { TableOfContentsDrawer } from "../components/TableOfContentsDrawer";
import { useReaderSettings } from "../hooks/useReaderSettings";
import { useLocalStorageState } from "../hooks/useLocalStorageState";
import {
  ArrowLeft,
  ArrowRight,
  Menu,
  Sliders,
  Split,
  Sparkles,
  RefreshCw,
} from "lucide-react";

type ViewMode = "refined" | "mtl" | "original";

export function Reader() {
  const { chapterId } = useParams<{ chapterId: string }>();
  const navigate = useNavigate();
  const id = parseInt(chapterId!, 10);
  const settings = useReaderSettings();
  const queryClient = useQueryClient();

  const [processingTriggeredAt, setProcessingTriggeredAt] = useState<
    number | null
  >(null);

  const reprocessMutation = useMutation({
    mutationFn: (doLlm: boolean) => api.reprocessChapter(id, doLlm),
    onMutate: () => {
      setProcessingTriggeredAt(Date.now());
      queryClient.setQueryData(["chapterStatus", id], (old: any) =>
        old ? { ...old, status: "processing" } : { status: "processing" },
      );
      queryClient.setQueryData(["read", id], (old: any) =>
        old ? { ...old, status: "processing" } : { status: "processing" },
      );
    },
    onSuccess: () => {
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ["read", id] });
        queryClient.invalidateQueries({ queryKey: ["chapterStatus", id] });
        queryClient.invalidateQueries({ queryKey: ["chaptersForNovel"] });
      }, 600);
    },
  });

  const [viewMode, setViewMode] = useLocalStorageState<ViewMode>(
    "tme-reader-viewMode",
    "refined",
  );
  const [splitMode, setSplitMode] = useLocalStorageState(
    "tme-reader-splitMode",
    false,
  );
  const [isControlsVisible, setIsControlsVisible] = useState(true);
  const [showSettings, setShowSettings] = useState(false);
  const [showToc, setShowToc] = useState(false);

  const { data: chapter, isLoading } = useQuery({
    queryKey: ["read", id],
    queryFn: () => api.readChapter(id),
    refetchInterval: (query) =>
      reprocessMutation.isPending ||
      !!processingTriggeredAt ||
      query.state.data?.status === "processing" ||
      query.state.data?.status === "pending"
        ? 1500
        : false,
  });

  const { data: chapterData } = useQuery({
    queryKey: ["chapterStatus", id],
    queryFn: () => api.chapterStatus(id),
    enabled: !isNaN(id),
    refetchInterval: (query) =>
      reprocessMutation.isPending ||
      !!processingTriggeredAt ||
      query.state.data?.status === "processing" ||
      query.state.data?.status === "pending"
        ? 1500
        : false,
  });

  const isCurrentlyProcessing =
    chapterData?.status === "processing" ||
    chapterData?.status === "pending" ||
    chapter?.status === "processing" ||
    chapter?.status === "pending";

  useEffect(() => {
    if (processingTriggeredAt) {
      const isDone =
        chapterData?.status === "completed" ||
        chapterData?.status === "failed" ||
        chapter?.status === "completed" ||
        chapter?.status === "failed";
      if (isDone && Date.now() - processingTriggeredAt > 2000) {
        setProcessingTriggeredAt(null);
      }
    }
  }, [chapterData?.status, chapter?.status, processingTriggeredAt]);

  const isChapterProcessing =
    reprocessMutation.isPending ||
    !!processingTriggeredAt ||
    isCurrentlyProcessing;

  const { data: novel } = useQuery({
    queryKey: ["novel", chapterData?.novel_id],
    queryFn: () =>
      chapterData?.novel_id ? api.getNovel(chapterData.novel_id) : null,
    enabled: !!chapterData?.novel_id,
  });

  const { data: neighbors } = useQuery({
    queryKey: ["neighbors", id],
    queryFn: () =>
      chapterData?.novel_id
        ? api.chapterNeighbors(chapterData.novel_id, id)
        : null,
    enabled: !!chapterData?.novel_id,
  });

  const { data: allChapters } = useQuery({
    queryKey: ["chaptersForNovel", chapterData?.novel_id],
    queryFn: () =>
      chapterData?.novel_id ? api.listChapters(chapterData.novel_id) : null,
    enabled: !!chapterData?.novel_id,
  });

  const [initialModeSetFor, setInitialModeSetFor] = useState<number | null>(
    null,
  );

  useEffect(() => {
    if (chapter && allChapters && initialModeSetFor !== id) {
      const vers = allChapters.filter(
        (c) => c.chapter_number === chapter.chapter_number,
      );
      const mtlVer =
        vers.find((c) => c.source_type === "mtl") ||
        (chapter.source_type === "mtl" ? chapter : undefined);
      const origVer =
        vers.find((c) => c.source_type === "original") ||
        (chapter.source_type === "original" ? chapter : undefined);

      if (origVer) {
        setViewMode("original");
      } else if (mtlVer?.refined_text) {
        setViewMode("refined");
      } else {
        setViewMode("mtl");
      }
      setInitialModeSetFor(id);
    }
  }, [id, chapter, allChapters, initialModeSetFor]);

  const prevStatusRef = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (
      prevStatusRef.current === "processing" &&
      chapter?.status === "completed"
    ) {
      queryClient.invalidateQueries({ queryKey: ["chaptersForNovel"] });
      if (chapter.refined_text) {
        setViewMode("refined");
      }
    }
    prevStatusRef.current = chapter?.status;
  }, [chapter?.status, chapter?.refined_text, queryClient]);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [id]);

  // Keyboard navigation support
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement
      )
        return;
      // CRITICAL: Do not intercept shortcuts with modifier keys (Alt, Ctrl, Meta, Shift)
      // This allows browser navigation like Alt+Left (Back) / Alt+Right (Forward) to function without getting trapped!
      if (e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;

      if (e.key === "ArrowLeft" && neighbors?.prev) {
        navigate(`/read/${neighbors.prev.id}`);
      } else if (e.key === "ArrowRight" && neighbors?.next) {
        navigate(`/read/${neighbors.next.id}`);
      } else if (e.key.toLowerCase() === "v") {
        setViewMode((prev) =>
          prev === "refined" ? "mtl" : prev === "mtl" ? "original" : "refined",
        );
      } else if (e.key === "Escape") {
        if (showSettings) setShowSettings(false);
        else if (showToc) setShowToc(false);
        else if (chapterData?.novel_id)
          navigate(`/novels/${chapterData.novel_id}`);
        else navigate("/");
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [neighbors, navigate, chapterData, showSettings, showToc]);

  // Auto-hide controls when scrolling down, show when scrolling up
  useEffect(() => {
    let lastScrollY = window.scrollY;
    const handleScroll = () => {
      const currentScrollY = window.scrollY;
      if (
        currentScrollY > lastScrollY &&
        currentScrollY > 120 &&
        !showSettings &&
        !showToc
      ) {
        setIsControlsVisible(false);
      } else if (lastScrollY - currentScrollY > 15 || currentScrollY < 40) {
        setIsControlsVisible(true);
      }
      lastScrollY = currentScrollY;
    };
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, [showSettings, showToc]);

  const versions = allChapters
    ? allChapters.filter((c) => c.chapter_number === chapter?.chapter_number)
    : [];

  const mtlVer =
    (chapter?.source_type === "mtl" ? chapter : undefined) ||
    versions.find((c) => c.source_type === "mtl");
  const origVer =
    (chapter?.source_type === "original" ? chapter : undefined) ||
    versions.find((c) => c.source_type === "original");

  const hasOriginal = !!origVer;
  const hasMtl = !!mtlVer;
  const hasRefined = !!mtlVer?.refined_text;

  // Only show the switcher if we have multiple versions to switch between
  const availableModes = [
    ...(hasRefined ? ["refined"] : []),
    ...(hasMtl ? ["mtl"] : []),
    ...(hasOriginal ? ["original"] : []),
  ];
  const showVersionSwitcher = availableModes.length > 1;

  const getDisplayText = () => {
    if (!chapter) return "";
    if (viewMode === "refined" && mtlVer?.refined_text)
      return mtlVer.refined_text;
    if (viewMode === "original" && origVer) return origVer.raw_text;
    if (viewMode === "mtl" && mtlVer) return mtlVer.raw_text;
    // Fallback if the mode is selected but version doesn't exist
    return chapter.raw_text;
  };

  const getCompareText = () => {
    if (!chapter) return "";
    if (viewMode === "refined" && mtlVer) return mtlVer.raw_text;
    if (viewMode === "mtl" && origVer) return origVer.raw_text;
    if (viewMode === "original" && mtlVer?.refined_text)
      return mtlVer.refined_text;
    if (viewMode === "original" && mtlVer) return mtlVer.raw_text;
    return chapter.raw_text;
  };

  if (isLoading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-3 bg-[var(--color-bg)] text-[var(--color-text)]">
        <div className="w-8 h-8 rounded-full border-2 border-t-[var(--color-accent)] border-white/20 animate-spin" />
        <p className="text-xs font-medium text-[var(--color-text-muted)]">
          Loading Webnovel reader...
        </p>
      </div>
    );
  }

  if (!chapter) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-4 bg-[var(--color-bg)] text-[var(--color-text)]">
        <p className="text-sm font-bold">Chapter not found in engine.</p>
        <button
          onClick={() => navigate(-1)}
          className="px-4 py-2 rounded-xl border bg-[var(--color-surface)] text-xs font-semibold cursor-pointer"
        >
          &larr; Return Back
        </button>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col bg-[var(--color-bg)] text-[var(--color-text)] transition-colors duration-200">
      {/* Top Floating Reader App Bar */}
      <header
        className={`fixed top-0 left-0 right-0 z-30 glass-surface border-b transition-all duration-300 px-3 sm:px-6 py-3 ${
          isControlsVisible
            ? "translate-y-0 opacity-100"
            : "-translate-y-full opacity-0 pointer-events-none"
        }`}
        style={{ borderColor: "var(--color-border)" }}
      >
        <div className="max-w-6xl mx-auto flex items-center justify-between gap-3">
          {/* Back & Title Breadcrumb */}
          <div className="flex items-center gap-3 min-w-0">
            <button
              onClick={() =>
                chapterData?.novel_id
                  ? navigate(`/novels/${chapterData.novel_id}`)
                  : navigate("/")
              }
              className="p-2 rounded-xl border hover:bg-white/5 transition-colors shrink-0 cursor-pointer"
              style={{
                borderColor: "var(--color-border)",
                color: "var(--color-text)",
              }}
              title="Return to Novel Studio"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>

            <div className="min-w-0">
              <span
                className="text-[10px] font-bold uppercase tracking-wider block line-clamp-1 opacity-70"
                style={{ color: "var(--color-accent)" }}
              >
                {novel?.name || "Webnovel AI"}
              </span>
              <h1
                className="text-sm font-extrabold font-outfit line-clamp-1"
                style={{ color: "var(--color-text)" }}
              >
                Chapter {chapter.chapter_number}
              </h1>
            </div>
          </div>

          {/* Version Switcher Segmented Control */}
          {showVersionSwitcher && (
            <div
              className="hidden sm:flex gap-1 p-1 rounded-xl border bg-black/30 shrink-0"
              style={{ borderColor: "var(--color-border)" }}
            >
              {hasRefined && (
                <button
                  onClick={() => setViewMode("refined")}
                  className={`px-3 py-1 rounded-lg text-xs font-bold transition-all cursor-pointer flex items-center gap-1 ${
                    viewMode === "refined"
                      ? "shadow-sm bg-[var(--color-accent)] text-white"
                      : "opacity-60 hover:opacity-100"
                  }`}
                >
                  <Sparkles className="w-3 h-3" />
                  <span>AI Refined</span>
                </button>
              )}
              {hasMtl && (
                <button
                  onClick={() => setViewMode("mtl")}
                  className={`px-3 py-1.5 text-xs font-bold rounded-lg transition-all cursor-pointer ${
                    viewMode === "mtl"
                      ? "shadow-sm bg-[var(--color-surface-hover)] text-[var(--color-text)]"
                      : "opacity-60 hover:opacity-100"
                  }`}
                >
                  Raw MTL
                </button>
              )}
              {hasOriginal && (
                <button
                  onClick={() => setViewMode("original")}
                  className={`px-3 py-1 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                    viewMode === "original"
                      ? "shadow-sm bg-[var(--color-surface-hover)] text-[var(--color-text)]"
                      : "opacity-60 hover:opacity-100"
                  }`}
                >
                  OG TL (Ref)
                </button>
              )}
            </div>
          )}

          {/* Right Action Tools */}
          <div className="flex items-center gap-1.5 shrink-0">
            {/* Process Button */}
            <button
              onClick={() => {
                if (isChapterProcessing) return;
                if (
                  confirm(
                    "Process this chapter? It will run through the latest rules again.",
                  )
                ) {
                  reprocessMutation.mutate(true);
                }
              }}
              disabled={isChapterProcessing}
              title="Process Chapter"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-bold transition-all cursor-pointer hover:bg-white/5 disabled:opacity-70 disabled:cursor-not-allowed"
              style={{
                borderColor: "var(--color-border)",
                color: "var(--color-text)",
              }}
            >
              <RefreshCw
                className={`w-3.5 h-3.5 ${isChapterProcessing ? "animate-spin text-[var(--color-accent)]" : ""}`}
              />
              <span className="hidden sm:inline">
                {isChapterProcessing ? "Processing..." : "Process"}
              </span>
            </button>

            {/* Split Compare Button (Desktop / Tablet) */}
            <button
              onClick={() => setSplitMode(!splitMode)}
              title="Toggle Side-by-Side Comparison Mode"
              className={`hidden md:flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-bold transition-all cursor-pointer ${
                splitMode
                  ? "shadow-md glow-accent bg-[var(--color-accent)] text-white border-transparent"
                  : "hover:bg-white/5"
              }`}
              style={{ borderColor: "var(--color-border)" }}
            >
              <Split className="w-3.5 h-3.5" />
              <span>Compare</span>
            </button>

            {/* Quick Font Size Controls */}
            <div
              className="flex items-center gap-1 border rounded-xl p-0.5"
              style={{
                borderColor: "var(--color-border)",
                backgroundColor: "var(--color-surface)",
              }}
            >
              <button
                onClick={settings.decreaseFontSize}
                className="w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold transition-colors hover:bg-white/10 cursor-pointer"
              >
                A-
              </button>
              <button
                onClick={settings.increaseFontSize}
                className="w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold transition-colors hover:bg-white/10 cursor-pointer"
              >
                A+
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Reader Scroll Container (Clicking inside toggles toolbars) */}
      <main
        className="flex-1 pt-20 pb-28 min-h-screen flex flex-col justify-between cursor-pointer"
        onClick={() => setIsControlsVisible(!isControlsVisible)}
      >
        {/* Mobile Version Toggle Bar (Only visible when controls visible on mobile) */}
        {showVersionSwitcher && isControlsVisible && (
          <div
            className="sm:hidden px-4 mb-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div
              className="flex gap-1 p-1 rounded-xl border bg-black/20"
              style={{ borderColor: "var(--color-border)" }}
            >
              {hasRefined && (
                <button
                  onClick={() => setViewMode("refined")}
                  className={`flex-1 py-1.5 text-[11px] font-bold rounded-lg transition-all flex items-center justify-center gap-1 cursor-pointer ${
                    viewMode === "refined"
                      ? "shadow-sm bg-[var(--color-accent)] text-white"
                      : "opacity-60"
                  }`}
                >
                  <Sparkles className="w-3 h-3" />
                  <span>Refined</span>
                </button>
              )}
              {hasMtl && (
                <button
                  onClick={() => setViewMode("mtl")}
                  className={`flex-1 py-1.5 text-[11px] font-bold rounded-lg transition-all cursor-pointer ${
                    viewMode === "mtl"
                      ? "shadow-sm bg-[var(--color-surface-hover)] text-[var(--color-text)]"
                      : "opacity-60"
                  }`}
                >
                  Raw MTL
                </button>
              )}
              {hasOriginal && (
                <button
                  onClick={() => setViewMode("original")}
                  className={`flex-1 py-1.5 text-[11px] font-bold rounded-lg transition-all cursor-pointer ${
                    viewMode === "original"
                      ? "shadow-sm bg-[var(--color-surface-hover)] text-[var(--color-text)]"
                      : "opacity-60"
                  }`}
                >
                  OG TL (Ref)
                </button>
              )}
            </div>
          </div>
        )}

        {/* Reading Article Area (Supports Single or Side-by-Side Split View) */}
        <div
          className={`flex-1 px-2 sm:px-4 ${splitMode ? "grid grid-cols-1 md:grid-cols-2 gap-6 max-w-7xl mx-auto w-full" : ""}`}
        >
          {/* Main Reading Column */}
          <div className="min-w-0">
            {splitMode && (
              <div className="max-w-[720px] mx-auto mb-3 px-4 flex items-center justify-between text-xs font-bold uppercase tracking-wider text-[var(--color-accent)]">
                <span>
                  {viewMode === "refined"
                    ? "✨ AI Refined Translation"
                    : viewMode === "original"
                      ? "📄 Reference Translation (OG TL)"
                      : "🤖 Raw MTL Stream"}
                </span>
              </div>
            )}
            <ReaderView
              text={getDisplayText()}
              fontSize={settings.fontSize}
              font={settings.font}
              lineHeight={settings.lineHeight}
              paraMode={settings.paraMode}
              maxWidth={splitMode ? "full" : settings.maxWidth}
              isProcessing={
                chapter.status === "processing" || chapter.status === "pending"
              }
            />
          </div>

          {/* Side-by-Side Comparison Column (Active in splitMode) */}
          {splitMode && (
            <div
              className="min-w-0 border-t md:border-t-0 md:border-l pt-8 md:pt-0 pl-0 md:pl-6"
              style={{ borderColor: "var(--color-border)" }}
            >
              <div className="max-w-[720px] mx-auto mb-3 px-4 flex items-center justify-between text-xs font-bold uppercase tracking-wider text-[var(--color-ai)]">
                <span>
                  {viewMode === "refined"
                    ? "🤖 Raw Machine Translation (MTL)"
                    : "✨ AI Refined Translation"}
                </span>
              </div>
              <ReaderView
                text={getCompareText()}
                fontSize={settings.fontSize}
                font={settings.font}
                lineHeight={settings.lineHeight}
                paraMode={settings.paraMode}
                maxWidth="full"
              />
            </div>
          )}
        </div>
      </main>

      {/* Bottom Floating Navigation Toolbar */}
      <footer
        className={`fixed bottom-0 left-0 right-0 z-30 glass-surface border-t transition-all duration-300 py-3 px-4 sm:px-6 ${
          isControlsVisible
            ? "translate-y-0 opacity-100"
            : "translate-y-full opacity-0 pointer-events-none"
        }`}
        style={{ borderColor: "var(--color-border)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="max-w-4xl mx-auto flex items-center justify-between gap-4">
          {/* Catalog TOC Drawer Trigger */}
          <button
            onClick={() => setShowToc(true)}
            className="flex items-center gap-2 px-3.5 py-2 rounded-2xl border text-xs font-bold transition-all hover:bg-white/5 cursor-pointer shrink-0"
            style={{
              borderColor: "var(--color-border)",
              color: "var(--color-text)",
            }}
          >
            <Menu className="w-4 h-4 text-[var(--color-accent)]" />
            <span className="hidden sm:inline">Catalog</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-black/30 font-mono opacity-80">
              {allChapters?.length ?? 0}
            </span>
          </button>

          {/* Chapter Scrubber / Prev & Next Controls */}
          <div className="flex items-center gap-2 flex-1 justify-center max-w-sm">
            <button
              onClick={() =>
                neighbors?.prev && navigate(`/read/${neighbors.prev.id}`)
              }
              disabled={!neighbors?.prev}
              className="p-2.5 rounded-xl border flex items-center justify-center text-xs font-bold transition-all cursor-pointer disabled:opacity-20 disabled:cursor-not-allowed hover:bg-white/5"
              style={{
                borderColor: "var(--color-border)",
                color: "var(--color-text)",
              }}
              title="Previous Chapter (Left Arrow key)"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>

            <div
              className="px-4 py-2 rounded-xl bg-black/20 border text-center flex-1 min-w-[110px]"
              style={{ borderColor: "var(--color-border)" }}
            >
              <span
                className="text-xs font-bold block leading-none font-outfit"
                style={{ color: "var(--color-text)" }}
              >
                Chapter {chapter.chapter_number}
              </span>
            </div>

            <button
              onClick={() =>
                neighbors?.next && navigate(`/read/${neighbors.next.id}`)
              }
              disabled={!neighbors?.next}
              className="p-2.5 rounded-xl border flex items-center justify-center text-xs font-bold transition-all cursor-pointer disabled:opacity-20 disabled:cursor-not-allowed hover:bg-white/5"
              style={{
                borderColor: "var(--color-border)",
                color: "var(--color-text)",
              }}
              title="Next Chapter (Right Arrow key)"
            >
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>

          {/* Display Settings Sheet Trigger */}
          <button
            onClick={() => setShowSettings(true)}
            className="flex items-center gap-2 px-3.5 py-2 rounded-2xl border text-xs font-bold transition-all hover:bg-white/5 cursor-pointer shrink-0"
            style={{
              borderColor: "var(--color-border)",
              color: "var(--color-text)",
            }}
          >
            <Sliders className="w-4 h-4 text-[var(--color-accent)]" />
            <span className="hidden sm:inline">Aa Display</span>
          </button>
        </div>
      </footer>

      {/* Reader Settings Drawer Modal */}
      <ReaderSettingsDrawer
        isOpen={showSettings}
        onClose={() => setShowSettings(false)}
        settings={settings}
      />

      {/* Catalog Table of Contents Drawer Modal */}
      <TableOfContentsDrawer
        isOpen={showToc}
        onClose={() => setShowToc(false)}
        chapters={allChapters || []}
        currentChapterId={id}
        onSelectChapter={(targetId) => navigate(`/read/${targetId}`)}
        novelName={novel?.name}
      />
    </div>
  );
}
