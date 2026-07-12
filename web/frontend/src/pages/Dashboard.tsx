import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { useLocalStorageState } from "../hooks/useLocalStorageState";
import { NovelCard } from "../components/NovelCard";
import { Header } from "../components/Header";
import { BottomNav, type NavTab } from "../components/BottomNav";
import { CreateNovelModal } from "../components/CreateNovelModal";
import { MemoryEngineTab } from "../components/MemoryEngineTab";
import { SettingsTab } from "../components/SettingsTab";
import {
  BookOpen,
  Sparkles,
  Plus,
  Grid,
  List,
  Cpu,
  ArrowRight,
} from "lucide-react";

export function Dashboard() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useLocalStorageState<NavTab>(
    "tme-dashboard-tab",
    "bookshelf",
  );
  const [showCreate, setShowCreate] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedLang, setSelectedLang] = useLocalStorageState<string>(
    "tme-dashboard-lang",
    "all",
  );
  const [layoutMode, setLayoutMode] = useLocalStorageState<"grid" | "list">(
    "tme-dashboard-layout",
    "grid",
  );

  const { data: novels, isLoading } = useQuery({
    queryKey: ["novels"],
    queryFn: api.listNovels,
  });

  const createMutation = useMutation({
    mutationFn: (data: {
      name: string;
      title?: string;
      source_language?: string;
    }) => api.createNovel(data),
    onSuccess: (newNovel) => {
      queryClient.invalidateQueries({ queryKey: ["novels"] });
      setShowCreate(false);
      // Automatically navigate to the new novel studio right away!
      navigate(`/novels/${newNovel.id}`);
    },
  });

  const filteredNovels =
    novels?.filter((n) => {
      const matchesQuery =
        !searchQuery.trim() ||
        n.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (n.title && n.title.toLowerCase().includes(searchQuery.toLowerCase()));
      const matchesLang =
        selectedLang === "all" ||
        n.source_language.toLowerCase() === selectedLang;
      return matchesQuery && matchesLang;
    }) || [];

  const totalChapters =
    novels?.reduce((acc, n) => acc + (n.chapter_count || 0), 0) ?? 0;

  return (
    <div className="min-h-screen flex flex-col md:pl-64 transition-all duration-200 bg-[var(--color-bg)] text-[var(--color-text)]">
      {/* Top Application Header */}
      <Header
        onOpenCreateNovel={() => setShowCreate(true)}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
      />

      {/* Main Container Area */}
      <main className="flex-1 p-4 md:p-6 lg:p-8 max-w-7xl mx-auto w-full">
        {/* Bookshelf or Explore View */}
        {(activeTab === "bookshelf" || activeTab === "explore") && (
          <div className="space-y-6 animate-fade-in pb-16">
            {/* Hero Banner (Only on Bookshelf) */}
            {activeTab === "bookshelf" &&
              !searchQuery &&
              selectedLang === "all" && (
                <div
                  className="rounded-3xl p-6 md:p-8 relative overflow-hidden shadow-2xl glass-surface border flex flex-col justify-between"
                  style={{
                    background:
                      "linear-gradient(135deg, rgba(249, 115, 22, 0.12) 0%, rgba(56, 189, 248, 0.08) 100%)",
                    borderColor: "var(--color-border)",
                  }}
                >
                  {/* Decorative Glowing Sphere */}
                  <div
                    className="absolute -top-12 -right-12 w-64 h-64 rounded-full blur-3xl opacity-20 pointer-events-none"
                    style={{ backgroundColor: "var(--color-accent)" }}
                  />

                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 relative z-10">
                    <div className="max-w-2xl">
                      <div className="flex items-center gap-2 mb-3">
                        <span className="text-xs font-black uppercase px-2.5 py-1 rounded-full tracking-wider bg-[var(--color-accent)] text-white shadow-md">
                          Mobile Studio v2.0
                        </span>
                        <span
                          className="text-xs font-semibold px-2.5 py-1 rounded-full border flex items-center gap-1.5"
                          style={{
                            borderColor: "var(--color-border)",
                            color: "var(--color-ai)",
                          }}
                        >
                          <Sparkles className="w-3.5 h-3.5" />
                          Live Memory Injection
                        </span>
                      </div>

                      <h1 className="text-2xl md:text-4xl font-black tracking-tight leading-tight font-outfit">
                        Next-Gen Webnovel{" "}
                        <span style={{ color: "var(--color-accent)" }}>
                          AI Memory Engine
                        </span>
                      </h1>

                      <p
                        className="text-xs md:text-sm mt-2 leading-relaxed opacity-80"
                        style={{ color: "var(--color-text-muted)" }}
                      >
                        Experience your novels with continuous context
                        retention, custom terminology policies, and real-time
                        MTL refinement. Built exclusively for mobile and desktop
                        reading immersion.
                      </p>
                    </div>

                    {/* Quick Action Box */}
                    <div className="shrink-0 flex flex-col sm:flex-row gap-3">
                      <button
                        onClick={() => setShowCreate(true)}
                        className="px-5 py-3.5 rounded-2xl font-bold text-sm text-white flex items-center justify-center gap-2 shadow-lg transition-transform hover:scale-105 active:scale-95 cursor-pointer glow-accent"
                        style={{
                          background:
                            "linear-gradient(135deg, var(--color-accent) 0%, #ea580c 100%)",
                        }}
                      >
                        <Plus className="w-5 h-5" strokeWidth={2.5} />
                        <span>Add Webnovel</span>
                      </button>
                      <button
                        onClick={() => setActiveTab("memory")}
                        className="px-4 py-3.5 rounded-2xl font-semibold text-sm border flex items-center justify-center gap-2 transition-colors hover:bg-white/5 cursor-pointer"
                        style={{
                          borderColor: "var(--color-border)",
                          color: "var(--color-text)",
                        }}
                      >
                        <Cpu className="w-4 h-4 text-[var(--color-ai)]" />
                        <span>Inspect Engine</span>
                      </button>
                    </div>
                  </div>

                  {/* Statistics Bar */}
                  <div
                    className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-6 pt-6 border-t"
                    style={{ borderColor: "var(--color-border)" }}
                  >
                    <div>
                      <span
                        className="text-[11px] font-semibold uppercase opacity-60 block"
                        style={{ color: "var(--color-text-muted)" }}
                      >
                        Bookshelf Novels
                      </span>
                      <span
                        className="text-xl font-bold font-mono"
                        style={{ color: "var(--color-text)" }}
                      >
                        {novels?.length ?? 0}
                      </span>
                    </div>
                    <div>
                      <span
                        className="text-[11px] font-semibold uppercase opacity-60 block"
                        style={{ color: "var(--color-text-muted)" }}
                      >
                        Total Chapters
                      </span>
                      <span
                        className="text-xl font-bold font-mono"
                        style={{ color: "var(--color-accent)" }}
                      >
                        {totalChapters}
                      </span>
                    </div>
                    <div>
                      <span
                        className="text-[11px] font-semibold uppercase opacity-60 block"
                        style={{ color: "var(--color-text-muted)" }}
                      >
                        Language Support
                      </span>
                      <span className="text-xs font-bold block mt-1">
                        🇰🇷 KR • 🇨🇳 CN • 🇯🇵 JP
                      </span>
                    </div>
                    <div>
                      <span
                        className="text-[11px] font-semibold uppercase opacity-60 block"
                        style={{ color: "var(--color-text-muted)" }}
                      >
                        Refine Quality
                      </span>
                      <span
                        className="text-xs font-bold block mt-1"
                        style={{ color: "var(--color-success)" }}
                      >
                        ✨ Human-Grade Context
                      </span>
                    </div>
                  </div>
                </div>
              )}

            {/* Filter and View Mode Switcher Bar */}
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
              {/* Language Chips */}
              <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar pb-1 sm:pb-0">
                {[
                  { id: "all", label: "All Novels", flag: "📚" },
                  { id: "korean", label: "Korean", flag: "🇰🇷" },
                  { id: "chinese", label: "Chinese", flag: "🇨🇳" },
                  { id: "japanese", label: "Japanese", flag: "🇯🇵" },
                ].map((lang) => {
                  const isSel = selectedLang === lang.id;
                  return (
                    <button
                      key={lang.id}
                      onClick={() => setSelectedLang(lang.id)}
                      className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 shrink-0 cursor-pointer ${
                        isSel
                          ? "shadow-md glow-accent"
                          : "opacity-65 hover:opacity-100"
                      }`}
                      style={{
                        backgroundColor: isSel
                          ? "var(--color-surface-hover)"
                          : "var(--color-surface)",
                        borderColor: isSel
                          ? "var(--color-accent)"
                          : "var(--color-border)",
                        borderWidth: "1px",
                        color: isSel
                          ? "var(--color-text)"
                          : "var(--color-text-muted)",
                      }}
                    >
                      <span>{lang.flag}</span>
                      <span>{lang.label}</span>
                    </button>
                  );
                })}
              </div>

              {/* Layout Mode Toggle */}
              <div className="flex items-center justify-between sm:justify-end gap-3">
                <span
                  className="text-xs font-semibold opacity-60"
                  style={{ color: "var(--color-text-muted)" }}
                >
                  Showing {filteredNovels.length}{" "}
                  {filteredNovels.length === 1 ? "novel" : "novels"}
                </span>

                <div
                  className="flex gap-1 p-1 rounded-xl border bg-black/20"
                  style={{ borderColor: "var(--color-border)" }}
                >
                  <button
                    onClick={() => setLayoutMode("grid")}
                    title="Grid Card View"
                    className={`p-1.5 rounded-lg transition-colors cursor-pointer ${layoutMode === "grid" ? "text-[var(--color-accent)] bg-white/10" : "opacity-50 hover:opacity-100"}`}
                  >
                    <Grid className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => setLayoutMode("list")}
                    title="Compact List View"
                    className={`p-1.5 rounded-lg transition-colors cursor-pointer ${layoutMode === "list" ? "text-[var(--color-accent)] bg-white/10" : "opacity-50 hover:opacity-100"}`}
                  >
                    <List className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>

            {/* Novels List / Grid Content */}
            {isLoading ? (
              <div className="py-20 text-center flex flex-col items-center justify-center gap-3">
                <div className="w-8 h-8 rounded-full border-2 border-t-[var(--color-accent)] border-white/20 animate-spin" />
                <p
                  className="text-xs font-medium opacity-60"
                  style={{ color: "var(--color-text-muted)" }}
                >
                  Loading your Webnovel studio...
                </p>
              </div>
            ) : filteredNovels.length > 0 ? (
              layoutMode === "grid" ? (
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {filteredNovels.map((novel) => (
                    <NovelCard
                      key={novel.id}
                      novel={novel}
                      onClick={() => navigate(`/novels/${novel.id}`)}
                      onQuickRead={() => navigate(`/novels/${novel.id}`)}
                    />
                  ))}
                </div>
              ) : (
                <div className="space-y-2">
                  {filteredNovels.map((novel) => (
                    <div
                      key={novel.id}
                      onClick={() => navigate(`/novels/${novel.id}`)}
                      className="p-4 rounded-2xl border transition-all hover:translate-x-1 flex items-center justify-between gap-4 cursor-pointer"
                      style={{
                        backgroundColor: "var(--color-surface)",
                        borderColor: "var(--color-border)",
                      }}
                    >
                      <div className="flex items-center gap-3.5 min-w-0">
                        <div
                          className="w-10 h-10 rounded-xl flex items-center justify-center font-bold text-xs text-white uppercase shrink-0 shadow-sm"
                          style={{
                            background:
                              "linear-gradient(135deg, var(--color-accent) 0%, #ea580c 100%)",
                          }}
                        >
                          {novel.source_language === "korean"
                            ? "KR"
                            : novel.source_language === "chinese"
                              ? "CN"
                              : "JP"}
                        </div>
                        <div className="min-w-0">
                          <h3
                            className="text-sm font-bold line-clamp-1 font-outfit"
                            style={{ color: "var(--color-text)" }}
                          >
                            {novel.name}
                          </h3>
                          {novel.title && (
                            <p
                              className="text-xs opacity-70 line-clamp-1 mt-0.5"
                              style={{ color: "var(--color-text-muted)" }}
                            >
                              {novel.title}
                            </p>
                          )}
                        </div>
                      </div>

                      <div className="flex items-center gap-4 shrink-0">
                        <span
                          className="text-xs font-semibold px-2.5 py-1 rounded-lg bg-black/20 font-mono"
                          style={{ color: "var(--color-text-muted)" }}
                        >
                          {novel.chapter_count} Chs
                        </span>
                        <ArrowRight className="w-4 h-4 opacity-50 text-[var(--color-accent)]" />
                      </div>
                    </div>
                  ))}
                </div>
              )
            ) : (
              /* Empty Bookshelf State */
              <div
                className="p-12 md:p-16 rounded-3xl border text-center glass-surface"
                style={{ borderColor: "var(--color-border)" }}
              >
                <div
                  className="w-16 h-16 rounded-2xl mx-auto mb-4 flex items-center justify-center bg-[var(--color-surface-hover)] border"
                  style={{ borderColor: "var(--color-border)" }}
                >
                  <BookOpen className="w-8 h-8 text-[var(--color-accent)]" />
                </div>
                <h3
                  className="text-lg font-bold font-outfit"
                  style={{ color: "var(--color-text)" }}
                >
                  {searchQuery || selectedLang !== "all"
                    ? "No matching novels found"
                    : "Your bookshelf is empty"}
                </h3>
                <p
                  className="text-xs md:text-sm mt-1.5 max-w-md mx-auto leading-relaxed opacity-70"
                  style={{ color: "var(--color-text-muted)" }}
                >
                  {searchQuery || selectedLang !== "all"
                    ? "Try adjusting your search query or language filter above."
                    : "Import your first Webnovel to start refining raw machine translations with the AI memory engine."}
                </p>
                <button
                  onClick={() => {
                    if (searchQuery || selectedLang !== "all") {
                      setSearchQuery("");
                      setSelectedLang("all");
                    } else {
                      setShowCreate(true);
                    }
                  }}
                  className="mt-5 px-5 py-2.5 rounded-xl text-xs font-bold text-white shadow-md transition-transform hover:scale-105 active:scale-95 cursor-pointer inline-flex items-center gap-2 glow-accent"
                  style={{
                    background:
                      "linear-gradient(135deg, var(--color-accent) 0%, #ea580c 100%)",
                  }}
                >
                  <Plus className="w-4 h-4" />
                  <span>
                    {searchQuery || selectedLang !== "all"
                      ? "Clear Filters"
                      : "Add Your First Novel"}
                  </span>
                </button>
              </div>
            )}
          </div>
        )}

        {/* Memory Engine Studio Tab */}
        {activeTab === "memory" && (
          <MemoryEngineTab onSelectNovel={(id) => navigate(`/novels/${id}`)} />
        )}

        {/* Reader Settings Tab */}
        {activeTab === "settings" && <SettingsTab />}
      </main>

      {/* Persistent SPA Bottom Dock / Desktop Sidebar */}
      <BottomNav
        activeTab={activeTab}
        onSelectTab={(tab) => setActiveTab(tab)}
      />

      {/* New Novel Creation Modal */}
      <CreateNovelModal
        isOpen={showCreate}
        onClose={() => setShowCreate(false)}
        onSubmit={async (data) => {
          await createMutation.mutateAsync(data);
        }}
        isPending={createMutation.isPending}
      />
    </div>
  );
}
