import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Cpu,
  Sparkles,
  Search,
  Layers,
  ShieldCheck,
  Database,
  ExternalLink,
  RefreshCw,
  Plus,
  Edit2,
  Trash2,
  X,
} from "lucide-react";
import { api } from "../api/client";
import {
  formatPolicyAction,
  formatAliasesList,
  isIdentityPolicy,
} from "../utils/formatters";

interface MemoryEngineTabProps {
  onSelectNovel?: (novelId: number) => void;
}

export function MemoryEngineTab({ onSelectNovel }: MemoryEngineTabProps) {
  const [selectedNovelId, setSelectedNovelId] = useState<number | "all">("all");
  const [search, setSearch] = useState("");
  const [activeSubTab, setActiveSubTab] = useState<"policies" | "glossary">(
    "policies",
  );

  const { data: novels, isLoading: novelsLoading } = useQuery({
    queryKey: ["novels"],
    queryFn: api.listNovels,
  });

  const queryClient = useQueryClient();
  const [ruleModal, setRuleModal] = useState<{
    isOpen: boolean;
    mode: "add" | "edit";
    policyId?: number;
    trigger: string;
    replacement: string;
    note: string;
  }>({ isOpen: false, mode: "add", trigger: "", replacement: "", note: "" });

  const createMutation = useMutation({
    mutationFn: (data: {
      trigger: string;
      replacement: string;
      note?: string;
    }) => api.createPolicy(targetNovelId as number, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["policies", targetNovelId] });
      setRuleModal((prev) => ({ ...prev, isOpen: false }));
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({
      policyId,
      data,
    }: {
      policyId: number;
      data: { trigger: string; replacement: string; note?: string };
    }) => api.updatePolicy(targetNovelId as number, policyId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["policies", targetNovelId] });
      setRuleModal((prev) => ({ ...prev, isOpen: false }));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (policyId: number) =>
      api.deletePolicy(targetNovelId as number, policyId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["policies", targetNovelId] });
    },
  });
  const targetNovelId =
    selectedNovelId === "all"
      ? novels && novels.length > 0
        ? novels[0].id
        : null
      : selectedNovelId;

  const extractMutation = useMutation({
    mutationFn: (id: number) => api.extractPolicies(id),
    onSuccess: () => {
      // In a real app we'd probably poll or show a toast. For now, it runs in the background.
      alert("Policy regeneration started in the background!");
    },
  });

  const { data: policies, isLoading: policiesLoading } = useQuery({
    queryKey: ["policies", targetNovelId],
    queryFn: () =>
      targetNovelId ? api.listPolicies(targetNovelId) : Promise.resolve([]),
    enabled: !!targetNovelId,
  });

  const { data: glossary, isLoading: glossaryLoading } = useQuery({
    queryKey: ["glossary", targetNovelId],
    queryFn: () =>
      targetNovelId ? api.listGlossary(targetNovelId) : Promise.resolve([]),
    enabled: !!targetNovelId,
  });

  const filteredPolicies =
    policies?.filter((p) => {
      if (!search.trim()) return true;
      const q = search.toLowerCase();
      return (
        p.trigger.toLowerCase().includes(q) ||
        p.action.toLowerCase().includes(q) ||
        p.type.toLowerCase().includes(q) ||
        p.match_forms.toLowerCase().includes(q)
      );
    }) || [];

  const filteredGlossary =
    glossary?.filter((g) => {
      if (!search.trim()) return true;
      const q = search.toLowerCase();
      return (
        g.canonical.toLowerCase().includes(q) ||
        g.aliases.toLowerCase().includes(q) ||
        (g.entity_type && g.entity_type.toLowerCase().includes(q))
      );
    }) || [];

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      {/* Hero Header */}
      <div
        className="p-6 rounded-3xl border relative overflow-hidden glass-surface"
        style={{ borderColor: "var(--color-border)" }}
      >
        <div
          className="absolute top-0 right-0 -mt-8 -mr-8 w-64 h-64 rounded-full opacity-10 pointer-events-none blur-3xl"
          style={{ backgroundColor: "var(--color-ai)" }}
        />

        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 relative z-10">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span
                className="text-xs font-bold px-2.5 py-1 rounded-full uppercase tracking-wider flex items-center gap-1.5"
                style={{
                  backgroundColor: "var(--color-ai-glow)",
                  color: "var(--color-ai)",
                }}
              >
                <Cpu className="w-3.5 h-3.5" />
                AI Memory Engine v1.0
              </span>
              <span
                className="text-xs px-2.5 py-1 rounded-full border opacity-75"
                style={{
                  borderColor: "var(--color-border)",
                  color: "var(--color-text-muted)",
                }}
              >
                Policy & Glossary Matrix
              </span>
            </div>
            <h1
              className="text-xl md:text-2xl font-black font-outfit"
              style={{ color: "var(--color-text)" }}
            >
              Translator Memory & Rules Studio
            </h1>
            <p
              className="text-xs md:text-sm mt-1 max-w-2xl opacity-75"
              style={{ color: "var(--color-text-muted)" }}
            >
              Every translation improvement is continuously captured as dynamic
              AI policies and canonical glossary entities. Inspect and verify
              exact translation behaviors below.
            </p>
          </div>

          {/* Novel Selector & Quick Jump Button */}
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className="text-xs font-semibold opacity-70"
              style={{ color: "var(--color-text-muted)" }}
            >
              Target Novel:
            </span>
            {novelsLoading ? (
              <span className="text-xs opacity-60">Loading novels...</span>
            ) : (
              <select
                value={selectedNovelId}
                onChange={(e) =>
                  setSelectedNovelId(
                    e.target.value === "all" ? "all" : Number(e.target.value),
                  )
                }
                className="px-3.5 py-2 rounded-xl text-xs md:text-sm font-semibold border transition-all cursor-pointer focus:outline-none focus:ring-2"
                style={{
                  backgroundColor: "var(--color-bg)",
                  borderColor: "var(--color-border)",
                  color: "var(--color-text)",
                }}
              >
                <option value="all">All Novels</option>
                {novels?.map((n) => (
                  <option key={n.id} value={n.id}>
                    {n.name} ({n.chapter_count} Chs)
                  </option>
                ))}
              </select>
            )}

            {targetNovelId && onSelectNovel && (
              <button
                onClick={() => onSelectNovel(targetNovelId)}
                title="Open Novel Studio Detail Page"
                className="p-2 rounded-xl border hover:bg-white/10 transition-colors cursor-pointer flex items-center gap-1 text-xs font-bold"
                style={{
                  borderColor: "var(--color-border)",
                  color: "var(--color-accent)",
                }}
              >
                <ExternalLink className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">Studio</span>
              </button>
            )}
          </div>
        </div>

        {/* Quick Stats Bar */}
        <div
          className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-6 pt-6 border-t"
          style={{ borderColor: "var(--color-border)" }}
        >
          <div
            className="p-3 rounded-xl border"
            style={{
              backgroundColor: "var(--color-box-bg)",
              borderColor: "var(--color-border)",
            }}
          >
            <span
              className="text-[11px] font-semibold uppercase opacity-60 block"
              style={{ color: "var(--color-text-muted)" }}
            >
              Active Policies
            </span>
            <span
              className="text-lg font-bold font-mono"
              style={{ color: "var(--color-ai)" }}
            >
              {policies?.length ?? 0} rules
            </span>
          </div>
          <div
            className="p-3 rounded-xl border"
            style={{
              backgroundColor: "var(--color-box-bg)",
              borderColor: "var(--color-border)",
            }}
          >
            <span
              className="text-[11px] font-semibold uppercase opacity-60 block"
              style={{ color: "var(--color-text-muted)" }}
            >
              Glossary Entries
            </span>
            <span
              className="text-lg font-bold font-mono"
              style={{ color: "var(--color-accent)" }}
            >
              {glossary?.length ?? 0} terms
            </span>
          </div>
          <div
            className="p-3 rounded-xl border"
            style={{
              backgroundColor: "var(--color-box-bg)",
              borderColor: "var(--color-border)",
            }}
          >
            <span
              className="text-[11px] font-semibold uppercase opacity-60 block"
              style={{ color: "var(--color-text-muted)" }}
            >
              Average Confidence
            </span>
            <span
              className="text-lg font-bold font-mono"
              style={{ color: "var(--color-success)" }}
            >
              {policies && policies.length > 0
                ? `${Math.round((policies.reduce((a, b) => a + b.confidence, 0) / policies.length) * 100)}%`
                : "98%"}
            </span>
          </div>
          <div
            className="p-3 rounded-xl border"
            style={{
              backgroundColor: "var(--color-box-bg)",
              borderColor: "var(--color-border)",
            }}
          >
            <span
              className="text-[11px] font-semibold uppercase opacity-60 block"
              style={{ color: "var(--color-text-muted)" }}
            >
              Engine Status
            </span>
            <span
              className="text-xs font-bold flex items-center gap-1.5 mt-1"
              style={{ color: "var(--color-success)" }}
            >
              <ShieldCheck className="w-4 h-4" />
              Synced & Enforcing
            </span>
          </div>
        </div>
      </div>

      {/* Sub-tab Navigation and Search Box */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
        <div
          className="flex gap-1 p-1 rounded-xl border"
          style={{
            backgroundColor: "var(--color-box-bg)",
            borderColor: "var(--color-border)",
          }}
        >
          <button
            onClick={() => setActiveSubTab("policies")}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition-all cursor-pointer ${
              activeSubTab === "policies"
                ? "shadow-sm"
                : "opacity-60 hover:opacity-100"
            }`}
            style={{
              backgroundColor:
                activeSubTab === "policies"
                  ? "var(--color-surface-hover)"
                  : "transparent",
              color:
                activeSubTab === "policies"
                  ? "var(--color-ai)"
                  : "var(--color-text-muted)",
            }}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>AI Policies ({policies?.length ?? 0})</span>
          </button>
          <button
            onClick={() => setActiveSubTab("glossary")}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition-all cursor-pointer ${
              activeSubTab === "glossary"
                ? "shadow-sm"
                : "opacity-60 hover:opacity-100"
            }`}
            style={{
              backgroundColor:
                activeSubTab === "glossary"
                  ? "var(--color-surface-hover)"
                  : "transparent",
              color:
                activeSubTab === "glossary"
                  ? "var(--color-accent)"
                  : "var(--color-text-muted)",
            }}
          >
            <Database className="w-3.5 h-3.5" />
            <span>Glossary Matrix ({glossary?.length ?? 0})</span>
          </button>
        </div>

        <div className="flex gap-2">
          {selectedNovelId !== "all" && (
            <button
              onClick={() =>
                setRuleModal({
                  isOpen: true,
                  mode: "add",
                  trigger: "",
                  replacement: "",
                  note: "",
                })
              }
              className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs md:text-sm font-semibold border transition-all hover:bg-white/5 cursor-pointer"
              style={{
                borderColor: "var(--color-border)",
                color: "var(--color-text)",
              }}
            >
              <Plus className="w-3.5 h-3.5" />
              Add Rule
            </button>
          )}
          {selectedNovelId !== "all" && (
            <button
              onClick={() => extractMutation.mutate(selectedNovelId)}
              disabled={extractMutation.isPending}
              className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs md:text-sm font-semibold border transition-all hover:bg-white/5 disabled:opacity-50 cursor-pointer"
              title="Re-run policy mining on all OG TL chapters in this novel"
              style={{
                borderColor: "var(--color-border)",
                color: "var(--color-text)",
              }}
            >
              <RefreshCw
                className={`w-3.5 h-3.5 ${extractMutation.isPending ? "animate-spin" : ""}`}
              />
              {extractMutation.isPending
                ? "Starting Extraction..."
                : "Regenerate Rules"}
            </button>
          )}
          <div className="relative max-w-sm" style={{ width: "250px" }}>
            <Search
              className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 opacity-50"
              style={{ color: "var(--color-text-muted)" }}
            />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={`Filter ${activeSubTab === "policies" ? "rules & actions..." : "glossary entities & aliases..."}`}
              className="w-full pl-10 pr-4 py-2 rounded-xl text-xs md:text-sm border transition-all focus:outline-none focus:ring-2"
              style={{
                backgroundColor: "var(--color-surface)",
                borderColor: "var(--color-border)",
                color: "var(--color-text)",
              }}
            />
          </div>
        </div>
      </div>

      {/* Content Area */}
      {policiesLoading || glossaryLoading ? (
        <div
          className="py-16 text-center text-sm opacity-60"
          style={{ color: "var(--color-text-muted)" }}
        >
          Loading Translator Memory data...
        </div>
      ) : activeSubTab === "policies" ? (
        filteredPolicies.length === 0 ? (
          <div
            className="p-12 text-center rounded-3xl border glass-surface"
            style={{ borderColor: "var(--color-border)" }}
          >
            <Sparkles className="w-10 h-10 mx-auto mb-3 text-[var(--color-ai)] opacity-60 animate-bounce" />
            <h3
              className="text-base font-bold"
              style={{ color: "var(--color-text)" }}
            >
              No translation policies found
            </h3>
            <p
              className="text-xs mt-1 max-w-md mx-auto opacity-70"
              style={{ color: "var(--color-text-muted)" }}
            >
              Process chapters using the AI rewrite engine or select a different
              novel above to inspect policies.
            </p>
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {filteredPolicies.map((p) => (
              <div
                key={p.id}
                className="group p-4 rounded-2xl border transition-all hover:border-[var(--color-ai)] flex flex-col justify-between gap-3"
                style={{
                  backgroundColor: "var(--color-surface)",
                  borderColor: "var(--color-border)",
                }}
              >
                <div>
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <span
                      className="text-[10px] font-black uppercase px-2 py-0.5 rounded-md tracking-wider font-mono"
                      style={{
                        backgroundColor: "var(--color-ai-glow)",
                        color: "var(--color-ai)",
                      }}
                    >
                      {p.type || "RULE"}
                    </span>
                    <span
                      className="text-[11px] font-mono font-semibold px-2 py-0.5 rounded border"
                      style={{
                        borderColor: "var(--color-border)",
                        color: "var(--color-text-muted)",
                      }}
                    >
                      Confidence: {Math.round(p.confidence * 100)}%
                    </span>

                    <div className="flex gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={() =>
                          setRuleModal({
                            isOpen: true,
                            mode: "edit",
                            policyId: p.id,
                            trigger: p.trigger,
                            replacement: JSON.parse(p.action).target || "",
                            note: p.note || "",
                          })
                        }
                        className="p-1 rounded hover:bg-black/20 text-[var(--color-text-muted)] hover:text-white"
                      >
                        <Edit2 className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => {
                          if (window.confirm("Delete this rule?"))
                            deleteMutation.mutate(p.id);
                        }}
                        className="p-1 rounded hover:bg-red-500/20 text-[var(--color-text-muted)] hover:text-red-400"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>

                  <h4
                    className="text-sm font-bold leading-snug mb-1 font-outfit"
                    style={{ color: "var(--color-text)" }}
                  >
                    Trigger:{" "}
                    <span className="text-[var(--color-accent)] font-mono">
                      {p.trigger}
                    </span>
                  </h4>

                  {formatAliasesList(p.match_forms, p.trigger)}

                  {isIdentityPolicy(p.action, p.trigger) ? (
                    <div
                      className="flex items-center gap-1.5 mt-2 text-xs font-sans"
                      style={{ color: "var(--color-text)" }}
                    >
                      <span
                        className="px-2 py-0.5 rounded border font-mono text-[11px] opacity-90"
                        style={{
                          backgroundColor: "var(--color-box-bg)",
                          borderColor: "var(--color-border)",
                          color: "var(--color-accent)",
                        }}
                      >
                        🔒 Protected Exact Canonical Entity
                      </span>
                    </div>
                  ) : (
                    <div
                      className="text-xs p-2.5 rounded-xl border-l-2 leading-relaxed mt-2"
                      style={{
                        backgroundColor: "var(--color-box-bg)",
                        borderColor: "var(--color-ai)",
                        color: "var(--color-text)",
                      }}
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

                {p.note && (
                  <p
                    className="text-[11px] italic opacity-60 border-t pt-2 mt-1"
                    style={{
                      borderColor: "var(--color-border)",
                      color: "var(--color-text-muted)",
                    }}
                  >
                    Note: {p.note}
                  </p>
                )}
              </div>
            ))}
          </div>
        )
      ) : /* Glossary Sub-Tab */
      filteredGlossary.length === 0 ? (
        <div
          className="p-12 text-center rounded-3xl border glass-surface"
          style={{ borderColor: "var(--color-border)" }}
        >
          <Database className="w-10 h-10 mx-auto mb-3 text-[var(--color-accent)] opacity-60 animate-bounce" />
          <h3
            className="text-base font-bold"
            style={{ color: "var(--color-text)" }}
          >
            No glossary entries extracted
          </h3>
          <p
            className="text-xs mt-1 max-w-md mx-auto opacity-70"
            style={{ color: "var(--color-text-muted)" }}
          >
            As the AI translates chapters, canonical terms, names, and
            techniques are saved here automatically.
          </p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3">
          {filteredGlossary.map((g) => (
            <div
              key={g.id}
              className="p-4 rounded-2xl border transition-all hover:border-[var(--color-accent)] flex flex-col justify-between"
              style={{
                backgroundColor: "var(--color-surface)",
                borderColor: "var(--color-border)",
              }}
            >
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span
                    className="text-[10px] font-extrabold uppercase px-2 py-0.5 rounded tracking-wider"
                    style={{
                      backgroundColor: "var(--color-accent-glow)",
                      color: "var(--color-accent)",
                    }}
                  >
                    {g.entity_type || "TERM"}
                  </span>
                  {g.confidence && (
                    <span
                      className="text-[10px] font-mono opacity-70"
                      style={{ color: "var(--color-text-muted)" }}
                    >
                      {Math.round(g.confidence * 100)}% Match
                    </span>
                  )}
                </div>

                <h4
                  className="text-base font-black font-outfit mb-1"
                  style={{ color: "var(--color-text)" }}
                >
                  {g.canonical}
                </h4>

                {formatAliasesList(g.aliases, g.canonical)}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Rule Modal */}
      {ruleModal.isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div
            className="w-full max-w-md p-6 rounded-2xl border shadow-2xl relative"
            style={{
              backgroundColor: "var(--color-surface)",
              borderColor: "var(--color-border)",
            }}
          >
            <button
              onClick={() =>
                setRuleModal((prev) => ({ ...prev, isOpen: false }))
              }
              className="absolute top-4 right-4 p-1 rounded-lg opacity-60 hover:opacity-100 hover:bg-white/10"
            >
              <X className="w-5 h-5" />
            </button>
            <h2
              className="text-xl font-bold mb-4"
              style={{ color: "var(--color-text)" }}
            >
              {ruleModal.mode === "add" ? "Add Custom Rule" : "Edit Rule"}
            </h2>
            <div className="space-y-4">
              <div>
                <label
                  className="block text-xs font-semibold opacity-70 mb-1"
                  style={{ color: "var(--color-text-muted)" }}
                >
                  Target Word / Phrase (MTL)
                </label>
                <input
                  type="text"
                  value={ruleModal.trigger}
                  onChange={(e) =>
                    setRuleModal((p) => ({ ...p, trigger: e.target.value }))
                  }
                  className="w-full px-3 py-2 rounded-xl text-sm border focus:outline-none focus:ring-2"
                  style={{
                    backgroundColor: "var(--color-bg)",
                    borderColor: "var(--color-border)",
                    color: "var(--color-text)",
                  }}
                  placeholder="e.g. Noh Young-joo"
                />
              </div>
              <div>
                <label
                  className="block text-xs font-semibold opacity-70 mb-1"
                  style={{ color: "var(--color-text-muted)" }}
                >
                  Correct Translation
                </label>
                <input
                  type="text"
                  value={ruleModal.replacement}
                  onChange={(e) =>
                    setRuleModal((p) => ({ ...p, replacement: e.target.value }))
                  }
                  className="w-full px-3 py-2 rounded-xl text-sm border focus:outline-none focus:ring-2"
                  style={{
                    backgroundColor: "var(--color-bg)",
                    borderColor: "var(--color-border)",
                    color: "var(--color-text)",
                  }}
                  placeholder="e.g. Lord Noh"
                />
              </div>
              <div>
                <label
                  className="block text-xs font-semibold opacity-70 mb-1"
                  style={{ color: "var(--color-text-muted)" }}
                >
                  Note (Optional)
                </label>
                <input
                  type="text"
                  value={ruleModal.note}
                  onChange={(e) =>
                    setRuleModal((p) => ({ ...p, note: e.target.value }))
                  }
                  className="w-full px-3 py-2 rounded-xl text-sm border focus:outline-none focus:ring-2"
                  style={{
                    backgroundColor: "var(--color-bg)",
                    borderColor: "var(--color-border)",
                    color: "var(--color-text)",
                  }}
                  placeholder="e.g. Title, not a first name"
                />
              </div>
              <button
                onClick={() => {
                  if (ruleModal.mode === "add") {
                    createMutation.mutate({
                      trigger: ruleModal.trigger,
                      replacement: ruleModal.replacement,
                      note: ruleModal.note,
                    });
                  } else {
                    updateMutation.mutate({
                      policyId: ruleModal.policyId!,
                      data: {
                        trigger: ruleModal.trigger,
                        replacement: ruleModal.replacement,
                        note: ruleModal.note,
                      },
                    });
                  }
                }}
                disabled={
                  !ruleModal.trigger ||
                  !ruleModal.replacement ||
                  createMutation.isPending ||
                  updateMutation.isPending
                }
                className="w-full py-2.5 rounded-xl font-bold transition-all hover:opacity-90 disabled:opacity-50 mt-2"
                style={{ backgroundColor: "var(--color-ai)", color: "black" }}
              >
                {createMutation.isPending || updateMutation.isPending
                  ? "Saving..."
                  : "Save Rule"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
