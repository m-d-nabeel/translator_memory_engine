import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { User, Edit2, Check, X, AlertTriangle, Eye, ArrowRight, Sparkles, RefreshCw, CheckSquare, Square, ChevronDown, BookOpen, Lock, Unlock, GitMerge, Link2, Quote, Search } from "lucide-react";
import { api, type GlossaryEntry } from "../api/client";

interface LoreTabProps {
  novelId: number;
}

export function LoreTab({ novelId }: LoreTabProps) {
  const queryClient = useQueryClient();
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState({ gender: "", race_or_identity: "", speech_style: "" });
  const [extractingMsg, setExtractingMsg] = useState<string | null>(null);
  const [onlyOgTl, setOnlyOgTl] = useState<boolean>(true);
  const [selectedChapterIds, setSelectedChapterIds] = useState<number[]>([]);
  const [showChapterPicker, setShowChapterPicker] = useState<boolean>(false);
  const [bypassReview, setBypassReview] = useState<boolean>(false);

  const [showDuplicatesModal, setShowDuplicatesModal] = useState<boolean>(false);
  const [linkingTarget, setLinkingTarget] = useState<GlossaryEntry | null>(null);
  const [selectedMergeIds, setSelectedMergeIds] = useState<number[]>([]);
  const [expandedQuotesId, setExpandedQuotesId] = useState<number | null>(null);

  const { data: chapters } = useQuery({
    queryKey: ["chapters", novelId],
    queryFn: () => api.listChapters(novelId),
  });

  const { data: glossary, isLoading: isGlossaryLoading } = useQuery({
    queryKey: ["glossary", novelId],
    queryFn: () => api.listGlossary(novelId),
  });

  const { data: policies } = useQuery({
    queryKey: ["policies", novelId],
    queryFn: () => api.listPolicies(novelId),
  });

  const { data: duplicates, isLoading: isDuplicatesLoading } = useQuery({
    queryKey: ["glossaryDuplicates", novelId],
    queryFn: () => api.listGlossaryDuplicates(novelId),
    enabled: showDuplicatesModal,
  });

  const mergeMutation = useMutation({
    mutationFn: ({ targetId, sourceIds }: { targetId: number; sourceIds: number[] }) =>
      api.mergeGlossaryEntries(novelId, targetId, sourceIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["glossary", novelId] });
      queryClient.invalidateQueries({ queryKey: ["glossaryDuplicates", novelId] });
      queryClient.invalidateQueries({ queryKey: ["policies", novelId] });
      setSelectedMergeIds([]);
      setLinkingTarget(null);
    },
  });

  const handleToggleChapter = (chId: number) => {
    setSelectedChapterIds((prev) =>
      prev.includes(chId) ? prev.filter((id) => id !== chId) : [...prev, chId]
    );
  };

  const handleSelectAllChapters = () => {
    if (!chapters) return;
    setSelectedChapterIds(chapters.map((c) => c.id));
  };

  const handleClearChapterSelection = () => {
    setSelectedChapterIds([]);
  };

  const extractLoreMutation = useMutation({
    mutationFn: (opts?: { onlyOgTl?: boolean; chapterIds?: number[]; bypassReview?: boolean }) => {
      const isOg = opts?.onlyOgTl ?? onlyOgTl;
      const chIds = opts?.chapterIds !== undefined ? opts.chapterIds : (selectedChapterIds.length > 0 ? selectedChapterIds : undefined);
      const isBypass = opts?.bypassReview ?? bypassReview;
      return api.extractLore(novelId, { onlyOgTl: isOg, chapterIds: chIds, bypassReview: isBypass });
    },
    onSuccess: (_, variables) => {
      const isOg = variables?.onlyOgTl ?? onlyOgTl;
      const chIds = variables?.chapterIds !== undefined ? variables.chapterIds : (selectedChapterIds.length > 0 ? selectedChapterIds : undefined);
      const isBypass = variables?.bypassReview ?? bypassReview;
      const modeText = chIds && chIds.length > 0
        ? `${chIds.length} selected chapter${chIds.length > 1 ? "s" : ""} (${isOg ? "OG TL" : "Best TL"}${isBypass ? " + Auto-Verify" : ""})`
        : (isOg ? `All Original Translation (OG TL) chapters${isBypass ? " + Auto-Verify" : ""}` : `All chapters${isBypass ? " + Auto-Verify" : ""}`);
      setExtractingMsg(`Background lore extraction triggered for ${modeText}! Check back in a few moments.`);
      setTimeout(() => setExtractingMsg(null), 7000);
      setShowChapterPicker(false);
    },
  });

  const updateMetaMutation = useMutation({
    mutationFn: ({
      entryId,
      metadata_json,
      needs_review,
      apply_proposed
    }: {
      entryId: number;
      metadata_json: string;
      needs_review: boolean;
      apply_proposed: boolean;
    }) => api.updateGlossaryMetadata(novelId, entryId, { metadata_json, needs_review, apply_proposed }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["glossary", novelId] });
      queryClient.invalidateQueries({ queryKey: ["policies", novelId] });
      setEditingId(null);
    },
  });

  const handleEdit = (entry: GlossaryEntry) => {
    const meta = entry.metadata_json ? JSON.parse(entry.metadata_json) : {};
    setEditForm({
      gender: meta.gender || "",
      race_or_identity: meta.race_or_identity || "",
      speech_style: meta.speech_style || ""
    });
    setEditingId(entry.id);
  };

  const handleSave = (entry: GlossaryEntry) => {
    let meta = entry.metadata_json ? JSON.parse(entry.metadata_json) : {};
    meta = { ...meta, ...editForm };
    updateMetaMutation.mutate({
      entryId: entry.id,
      metadata_json: JSON.stringify(meta),
      needs_review: false,
      apply_proposed: false,
    });
  };

  const handleAcceptProposed = (entry: GlossaryEntry) => {
    updateMetaMutation.mutate({
      entryId: entry.id,
      metadata_json: entry.metadata_json || "{}",
      needs_review: false,
      apply_proposed: true,
    });
  };

  const handleRejectProposed = (entry: GlossaryEntry) => {
    let meta = entry.metadata_json ? JSON.parse(entry.metadata_json) : {};
    if (meta.proposed_updates) {
      delete meta.proposed_updates;
    }
    updateMetaMutation.mutate({
      entryId: entry.id,
      metadata_json: JSON.stringify(meta),
      needs_review: false,
      apply_proposed: false,
    });
  };

  const handleVerifyNew = (entry: GlossaryEntry) => {
    updateMetaMutation.mutate({
      entryId: entry.id,
      metadata_json: entry.metadata_json || "{}",
      needs_review: false,
      apply_proposed: false,
    });
  };

  const handleToggleLock = (entry: GlossaryEntry, currentlyLocked: boolean) => {
    updateMetaMutation.mutate({
      entryId: entry.id,
      metadata_json: entry.metadata_json || "{}",
      needs_review: currentlyLocked, // if currently locked (needs_review=false), set needs_review=true. If unverified (needs_review=true), set needs_review=false.
      apply_proposed: false,
    });
  };

  if (isGlossaryLoading || !glossary || !policies) {
    return (
      <div className="p-8 text-center text-sm opacity-60" style={{ color: "var(--color-text-muted)" }}>
        Loading character lore...
      </div>
    );
  }

  // Filter for characters (entity type) and merge with policy needs_review status
  const characters = glossary
    .filter(g => g.entity_type === "entity" || g.metadata_json)
    .map(g => {
      const p = policies.find(p => p.trigger?.trim().toLowerCase() === g.canonical?.trim().toLowerCase());
      const meta = g.metadata_json ? JSON.parse(g.metadata_json) : {};
      const isReviewNeeded = p ? (p.needs_review === "true" || (p.needs_review as any) === true) : Boolean(meta.proposed_updates);
      return {
        ...g,
        needs_review: isReviewNeeded,
        meta
      };
    });

  return (
    <div className="space-y-6">
      <div className="space-y-4 border-b pb-5" style={{ borderColor: "var(--color-border)" }}>
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2" style={{ color: "var(--color-text)" }}>
            <User className="h-5 w-5" style={{ color: "var(--color-accent)" }} />
            Character Lore Database
          </h2>
          <p className="text-xs mt-1" style={{ color: "var(--color-text-muted)" }}>
            The engine autonomously extracts character metadata during translation. Unverified entries and character arc shifts are flagged below.
          </p>
        </div>

        <div 
          className="p-3 rounded-2xl border flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-3 shadow-sm transition-all"
          style={{ backgroundColor: "var(--color-box-bg)", borderColor: "var(--color-border)" }}
        >
          <div className="flex items-center gap-2.5 flex-wrap">
            <button
              onClick={() => setShowChapterPicker(!showChapterPicker)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-bold transition-all cursor-pointer shadow-sm"
              style={{
                backgroundColor: selectedChapterIds.length > 0 ? "var(--color-accent-subtle, rgba(234, 88, 12, 0.15))" : "var(--color-surface)",
                borderColor: selectedChapterIds.length > 0 ? "var(--color-accent)" : "var(--color-border)",
                color: selectedChapterIds.length > 0 ? "var(--color-accent)" : "var(--color-text)",
              }}
            >
              <BookOpen className="w-3.5 h-3.5" />
              <span>{selectedChapterIds.length > 0 ? `${selectedChapterIds.length} Chapters Selected` : "Select Chapters"}</span>
              <ChevronDown className={`w-3.5 h-3.5 transition-transform ${showChapterPicker ? "rotate-180" : ""}`} />
            </button>

            <label className="flex items-center gap-2 cursor-pointer text-xs font-bold px-3 py-1.5 rounded-xl border select-none transition-all" style={{ backgroundColor: "var(--color-surface)", borderColor: "var(--color-border)", color: "var(--color-text)" }}>
              <input
                type="checkbox"
                checked={onlyOgTl}
                onChange={(e) => setOnlyOgTl(e.target.checked)}
                className="rounded accent-[var(--color-accent)] w-4 h-4 cursor-pointer"
              />
              <span>Extract from OG TL only</span>
            </label>

            <label 
              title="Automatically approve & overwrite character traits without requiring manual review confirmation"
              className="flex items-center gap-2 cursor-pointer text-xs font-bold px-3 py-1.5 rounded-xl border select-none transition-all" 
              style={{ 
                backgroundColor: bypassReview ? "rgba(234, 88, 12, 0.12)" : "var(--color-surface)", 
                borderColor: bypassReview ? "var(--color-accent)" : "var(--color-border)", 
                color: bypassReview ? "var(--color-accent)" : "var(--color-text)" 
              }}
            >
              <input
                type="checkbox"
                checked={bypassReview}
                onChange={(e) => setBypassReview(e.target.checked)}
                className="rounded accent-[var(--color-accent)] w-4 h-4 cursor-pointer"
              />
              <span>Bypass Review (Auto-Verify)</span>
            </label>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={() => setShowDuplicatesModal(true)}
              className="flex items-center justify-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold border transition-transform hover:scale-[1.02] active:scale-[0.98] cursor-pointer shadow-sm"
              style={{
                backgroundColor: "var(--color-surface)",
                borderColor: "var(--color-accent)",
                color: "var(--color-accent)",
              }}
              title="Scan and verify potential duplicate characters using semantic blocking & evidence quotes"
            >
              <Search className="w-4 h-4" />
              <span>Detect Duplicates 🔍</span>
            </button>

            <button
              onClick={() => extractLoreMutation.mutate({ onlyOgTl, chapterIds: selectedChapterIds.length > 0 ? selectedChapterIds : undefined, bypassReview })}
              disabled={extractLoreMutation.isPending}
              className="flex items-center justify-center gap-2 px-5 py-2 rounded-xl text-xs font-bold transition-transform hover:scale-[1.02] active:scale-[0.98] cursor-pointer shadow-md text-white flex-shrink-0"
              style={{
                background: "linear-gradient(135deg, var(--color-accent) 0%, #ea580c 100%)",
              }}
            >
              {extractLoreMutation.isPending ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                <Sparkles className="w-4 h-4" />
              )}
              <span>
                {extractLoreMutation.isPending
                  ? "Starting Extraction..."
                  : selectedChapterIds.length > 0
                  ? `Extract Lore (${selectedChapterIds.length} Ch.)`
                  : `Extract Lore (${onlyOgTl ? "OG TL" : "All Chapters"})`}
              </span>
            </button>
          </div>
        </div>
      </div>

      {showChapterPicker && (
        <div 
          className="p-4 rounded-2xl border shadow-lg flex flex-col gap-3 transition-all"
          style={{ backgroundColor: "var(--color-box-bg)", borderColor: "var(--color-accent)" }}
        >
          <div className="flex items-center justify-between pb-2 border-b" style={{ borderColor: "var(--color-border)" }}>
            <div className="flex items-center gap-2">
              <BookOpen className="w-4 h-4" style={{ color: "var(--color-accent)" }} />
              <h4 className="text-xs font-bold" style={{ color: "var(--color-text)" }}>Select Chapters for Lore Extraction</h4>
              {selectedChapterIds.length > 0 && (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-extrabold text-white" style={{ backgroundColor: "var(--color-accent)" }}>
                  {selectedChapterIds.length} selected
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleSelectAllChapters}
                className="text-[11px] font-bold px-2 py-1 rounded transition hover:opacity-80 cursor-pointer"
                style={{ color: "var(--color-accent)" }}
              >
                Select All
              </button>
              <button
                onClick={handleClearChapterSelection}
                className="text-[11px] font-bold px-2 py-1 rounded transition hover:opacity-80 cursor-pointer"
                style={{ color: "var(--color-text-muted)" }}
              >
                Clear
              </button>
              <button
                onClick={() => setShowChapterPicker(false)}
                className="p-1 rounded-lg transition hover:bg-black/10 cursor-pointer"
                style={{ color: "var(--color-text-muted)" }}
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          <div className="max-h-52 overflow-y-auto pr-1 grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-2">
            {!chapters || chapters.length === 0 ? (
              <div className="col-span-full py-4 text-center text-xs" style={{ color: "var(--color-text-muted)" }}>
                No chapters found in this novel.
              </div>
            ) : (
              chapters.map((ch) => {
                const isSelected = selectedChapterIds.includes(ch.id);
                return (
                  <button
                    key={ch.id}
                    onClick={() => handleToggleChapter(ch.id)}
                    className="flex items-center justify-between px-2.5 py-1.5 rounded-xl border text-xs font-semibold transition-all cursor-pointer text-left"
                    style={{
                      backgroundColor: isSelected ? "var(--color-accent-subtle, rgba(234, 88, 12, 0.15))" : "var(--color-surface)",
                      borderColor: isSelected ? "var(--color-accent)" : "var(--color-border)",
                      color: isSelected ? "var(--color-accent)" : "var(--color-text)",
                    }}
                  >
                    <span className="truncate">Ch. {ch.chapter_number}</span>
                    {isSelected ? <CheckSquare className="w-3.5 h-3.5 flex-shrink-0" /> : <Square className="w-3.5 h-3.5 flex-shrink-0 opacity-40" />}
                  </button>
                );
              })
            )}
          </div>

          <div className="flex flex-col sm:flex-row sm:items-center justify-between pt-2 border-t gap-2 text-xs font-medium" style={{ borderColor: "var(--color-border)", color: "var(--color-text-muted)" }}>
            <span>
              {onlyOgTl ? "Extracting from Original Translation (OG TL / Raw Text)" : "Extracting from Refined / Best Translation"}
            </span>
            <div className="flex items-center gap-2 self-end sm:self-auto">
              <button
                onClick={() => setShowChapterPicker(false)}
                className="px-3 py-1 rounded-xl border text-xs font-semibold cursor-pointer transition hover:opacity-80"
                style={{ borderColor: "var(--color-border)", color: "var(--color-text)" }}
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      {extractingMsg && (
        <div 
          className="p-3.5 rounded-xl text-xs font-medium border flex items-center justify-between"
          style={{
            backgroundColor: "var(--color-surface)",
            borderColor: "var(--color-accent)",
            color: "var(--color-text)",
          }}
        >
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4" style={{ color: "var(--color-accent)" }} />
            <span>{extractingMsg}</span>
          </div>
          <button 
            onClick={() => queryClient.invalidateQueries({ queryKey: ["glossary", novelId] })}
            className="underline text-xs opacity-80 hover:opacity-100 cursor-pointer"
          >
            Refresh Now
          </button>
        </div>
      )}

      <div className="columns-1 lg:columns-2 gap-4 space-y-4">
        {characters.map((char) => (
          <div
            key={char.id}
            className="rounded-2xl border p-5 shadow-sm transition-all relative flex flex-col justify-between break-inside-avoid inline-block w-full mb-4 h-fit"
            style={{
              backgroundColor: char.needs_review ? "var(--color-box-bg)" : "var(--color-surface)",
              borderColor: char.needs_review ? "var(--color-accent)" : "var(--color-border)",
            }}
          >
            <div>
              <div className="mb-4 flex items-start justify-between">
                <div>
                  <h3 className="text-lg font-bold flex items-center gap-2" style={{ color: "var(--color-text)" }}>
                    {char.canonical}
                    {!char.needs_review && !char.meta.proposed_updates && (
                      <span title="Verified & Locked Profile" className="text-xs font-semibold px-2 py-0.5 rounded-full inline-flex items-center gap-1 border" style={{ backgroundColor: "var(--color-success-subtle, rgba(16, 185, 129, 0.12))", color: "var(--color-success)", borderColor: "var(--color-success)" }}>
                        <Lock className="w-3 h-3" /> Locked
                      </span>
                    )}
                  </h3>
                  {char.needs_review && !char.meta.proposed_updates && (
                    <span 
                      className="mt-1.5 inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold border"
                      style={{
                        backgroundColor: "var(--color-warning-subtle)",
                        color: "var(--color-warning)",
                        borderColor: "var(--color-warning)",
                      }}
                    >
                      <AlertTriangle className="mr-1 h-3 w-3" /> New Character (Unverified)
                    </span>
                  )}
                  {Boolean(char.meta.proposed_updates) && (
                    <span 
                      className="mt-1.5 inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold border"
                      style={{
                        backgroundColor: "var(--color-ai-glow)",
                        color: "var(--color-ai)",
                        borderColor: "var(--color-ai)",
                      }}
                    >
                      <Eye className="mr-1 h-3 w-3" /> Character Arc Shift
                    </span>
                  )}
                </div>
                
                <div className="flex items-center space-x-2">
                  {editingId === char.id ? (
                    <>
                      <button
                        onClick={() => handleSave(char)}
                        className="rounded-lg p-2 text-white hover:opacity-90 cursor-pointer shadow-sm"
                        style={{ backgroundColor: "var(--color-success)" }}
                        title="Save Changes"
                      >
                        <Check className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => setEditingId(null)}
                        className="rounded-lg p-2 border hover:opacity-80 cursor-pointer"
                        style={{ 
                          backgroundColor: "var(--color-box-bg)", 
                          borderColor: "var(--color-border)",
                          color: "var(--color-text)" 
                        }}
                        title="Cancel"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        onClick={() => handleToggleLock(char, !char.needs_review)}
                        className="rounded-lg p-2 border hover:opacity-80 cursor-pointer transition-colors"
                        style={{ 
                          backgroundColor: char.needs_review ? "rgba(234, 88, 12, 0.12)" : "rgba(16, 185, 129, 0.12)", 
                          borderColor: char.needs_review ? "var(--color-accent)" : "var(--color-success)",
                          color: char.needs_review ? "var(--color-accent)" : "var(--color-success)" 
                        }}
                        title={char.needs_review ? "Unverified (Click to Lock & Verify Profile)" : "Verified & Locked (Click to Unlock)"}
                      >
                        {char.needs_review ? <Unlock className="h-4 w-4" /> : <Lock className="h-4 w-4" />}
                      </button>
                      <button
                        onClick={() => handleEdit(char)}
                        className="rounded-lg p-2 border hover:opacity-80 cursor-pointer transition-colors"
                        style={{ 
                          backgroundColor: "var(--color-box-bg)", 
                          borderColor: "var(--color-border)",
                          color: "var(--color-text)" 
                        }}
                        title="Edit Profile"
                      >
                        <Edit2 className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => {
                          setLinkingTarget(char);
                          setSelectedMergeIds([]);
                        }}
                        className="rounded-lg p-2 border hover:opacity-80 cursor-pointer transition-colors"
                        style={{ 
                          backgroundColor: "var(--color-box-bg)", 
                          borderColor: "var(--color-border)",
                          color: "var(--color-accent)" 
                        }}
                        title="Link / Merge other character cards into this entry"
                      >
                        <Link2 className="h-4 w-4" />
                      </button>
                    </>
                  )}
                </div>
              </div>

              {Boolean(char.meta.proposed_updates) && (
                 <div 
                   className="mb-4 rounded-xl p-3.5 border"
                   style={{
                     backgroundColor: "var(--color-box-bg)",
                     borderColor: "var(--color-ai)",
                   }}
                 >
                   <h4 className="text-xs font-bold uppercase tracking-wider mb-2" style={{ color: "var(--color-ai)" }}>
                     Proposed Arc Updates
                   </h4>
                   {char.meta.proposed_updates.race_or_identity && (
                      <div className="text-xs mb-2 flex items-start" style={{ color: "var(--color-text)" }}>
                        <span className="w-16 flex-shrink-0 font-semibold opacity-70">Identity:</span>
                        <div className="flex-1">
                          <span className="line-through opacity-50 mr-2">{char.meta.race_or_identity || "None"}</span>
                          <ArrowRight className="inline h-3 w-3 mx-1 opacity-60"/>
                          <span className="font-semibold" style={{ color: "var(--color-success)" }}>{char.meta.proposed_updates.race_or_identity}</span>
                        </div>
                      </div>
                   )}
                   {char.meta.proposed_updates.speech_style && (
                      <div className="text-xs flex items-start" style={{ color: "var(--color-text)" }}>
                        <span className="w-16 flex-shrink-0 font-semibold opacity-70">Style:</span>
                        <div className="flex-1">
                          <span className="line-through opacity-50 mr-2">{char.meta.speech_style || "None"}</span>
                          <ArrowRight className="inline h-3 w-3 mx-1 opacity-60"/>
                          <span className="font-semibold" style={{ color: "var(--color-success)" }}>{char.meta.proposed_updates.speech_style}</span>
                        </div>
                      </div>
                   )}
                   <div className="mt-3 flex space-x-2">
                     <button 
                       onClick={() => handleAcceptProposed(char)} 
                       className="flex-1 rounded-lg py-1.5 text-xs font-bold text-white shadow-sm cursor-pointer hover:opacity-90 transition-opacity"
                       style={{ backgroundColor: "var(--color-ai)" }}
                     >
                       Accept Growth
                     </button>
                     <button 
                       onClick={() => handleRejectProposed(char)} 
                       className="flex-1 rounded-lg py-1.5 text-xs font-bold border cursor-pointer hover:opacity-80 transition-opacity"
                       style={{
                         backgroundColor: "var(--color-surface)",
                         borderColor: "var(--color-border)",
                         color: "var(--color-text)"
                       }}
                     >
                       Reject
                     </button>
                   </div>
                 </div>
              )}

              <div className="space-y-3 text-sm">
                {editingId === char.id ? (
                  <div className="space-y-3 pt-1">
                    <div>
                      <label className="text-xs font-bold uppercase tracking-wider" style={{ color: "var(--color-text-muted)" }}>Gender</label>
                      <input
                        type="text"
                        className="mt-1 block w-full rounded-lg border px-3 py-1.5 text-sm focus:outline-none"
                        style={{
                          backgroundColor: "var(--color-box-bg)",
                          borderColor: "var(--color-accent)",
                          color: "var(--color-text)",
                        }}
                        value={editForm.gender}
                        onChange={(e) => setEditForm({ ...editForm, gender: e.target.value })}
                        placeholder="e.g. Male, Female, Non-binary"
                      />
                    </div>
                    <div>
                      <label className="text-xs font-bold uppercase tracking-wider" style={{ color: "var(--color-text-muted)" }}>Identity & Role</label>
                      <textarea
                        rows={2}
                        className="mt-1 block w-full rounded-lg border px-3 py-1.5 text-sm focus:outline-none resize-none"
                        style={{
                          backgroundColor: "var(--color-box-bg)",
                          borderColor: "var(--color-accent)",
                          color: "var(--color-text)",
                        }}
                        value={editForm.race_or_identity}
                        onChange={(e) => setEditForm({ ...editForm, race_or_identity: e.target.value })}
                        placeholder="e.g. Human protagonist, blacksmith apprentice..."
                      />
                    </div>
                    <div>
                      <label className="text-xs font-bold uppercase tracking-wider" style={{ color: "var(--color-text-muted)" }}>Speech Style</label>
                      <textarea
                        rows={2}
                        className="mt-1 block w-full rounded-lg border px-3 py-1.5 text-sm focus:outline-none resize-none"
                        style={{
                          backgroundColor: "var(--color-box-bg)",
                          borderColor: "var(--color-accent)",
                          color: "var(--color-text)",
                        }}
                        value={editForm.speech_style}
                        onChange={(e) => setEditForm({ ...editForm, speech_style: e.target.value })}
                        placeholder="e.g. Speaks with archaic formality, polite tone..."
                      />
                    </div>
                  </div>
                ) : (
                  <div className="space-y-2.5 pt-1">
                    <div className="flex items-baseline">
                      <span className="w-24 flex-shrink-0 text-xs font-semibold" style={{ color: "var(--color-text-muted)" }}>Gender:</span>
                      <span className="font-medium" style={{ color: "var(--color-text)" }}>{char.meta.gender || <span className="opacity-40 italic">Not extracted</span>}</span>
                    </div>
                    <div className="flex items-baseline">
                      <span className="w-24 flex-shrink-0 text-xs font-semibold" style={{ color: "var(--color-text-muted)" }}>Identity:</span>
                      <span className="font-medium leading-relaxed" style={{ color: "var(--color-text)" }}>{char.meta.race_or_identity || <span className="opacity-40 italic">Not extracted</span>}</span>
                    </div>
                    <div className="flex items-baseline">
                      <span className="w-24 flex-shrink-0 text-xs font-semibold" style={{ color: "var(--color-text-muted)" }}>Speech Style:</span>
                      <span className="font-medium leading-relaxed" style={{ color: "var(--color-text)" }}>{char.meta.speech_style || <span className="opacity-40 italic">Not extracted</span>}</span>
                    </div>

                    {(() => {
                      try {
                        const arr = JSON.parse(char.aliases || "[]");
                        if (Array.isArray(arr) && arr.length > 0) {
                          return (
                            <div className="flex items-baseline pt-1">
                              <span className="w-24 flex-shrink-0 text-xs font-semibold" style={{ color: "var(--color-text-muted)" }}>Aliases:</span>
                              <div className="flex flex-wrap gap-1">
                                {arr.map((al: string, idx: number) => (
                                  <span key={idx} className="px-2 py-0.5 rounded-md text-[11px] font-medium border" style={{ backgroundColor: "var(--color-surface)", borderColor: "var(--color-border)", color: "var(--color-text-muted)" }}>
                                    {al}
                                  </span>
                                ))}
                              </div>
                            </div>
                          );
                        }
                      } catch { /* ignore */ }
                      return null;
                    })()}

                    {(() => {
                      try {
                        const quotes = JSON.parse(char.evidence_contexts || "[]");
                        if (Array.isArray(quotes) && quotes.length > 0) {
                          return (
                            <div className="pt-1">
                              <button
                                onClick={() => setExpandedQuotesId(expandedQuotesId === char.id ? null : char.id)}
                                className="flex items-center gap-1.5 text-xs font-bold hover:underline cursor-pointer transition-opacity"
                                style={{ color: "var(--color-accent)" }}
                              >
                                <Quote className="w-3.5 h-3.5" />
                                <span>Verbatim Intro Quotes ({quotes.length})</span>
                                <ChevronDown className={`w-3.5 h-3.5 transition-transform ${expandedQuotesId === char.id ? "rotate-180" : ""}`} />
                              </button>

                              {expandedQuotesId === char.id && (
                                <div className="mt-2 space-y-2 pl-2">
                                  {quotes.map((q: string, idx: number) => (
                                    <blockquote key={idx} className="border-l-2 pl-2.5 py-1 text-xs italic leading-relaxed opacity-90" style={{ borderColor: "var(--color-accent)", color: "var(--color-text)" }}>
                                      "{q}"
                                    </blockquote>
                                  ))}
                                </div>
                              )}
                            </div>
                          );
                        }
                      } catch { /* ignore */ }
                      return null;
                    })()}
                  </div>
                )}
              </div>
            </div>

            {char.needs_review && !char.meta.proposed_updates && editingId !== char.id && (
              <div className="mt-5 pt-3 border-t flex justify-end" style={{ borderColor: "var(--color-border)" }}>
                <button
                  onClick={() => handleVerifyNew(char)}
                  className="w-full sm:w-auto px-4 py-2 rounded-xl text-xs font-bold cursor-pointer transition-transform hover:scale-[1.02] active:scale-[0.98] shadow-sm flex items-center justify-center gap-1.5"
                  style={{
                    background: "linear-gradient(135deg, var(--color-warning) 0%, #d97706 100%)",
                    color: "#ffffff"
                  }}
                >
                  <Check className="w-3.5 h-3.5" />
                  Verify & Lock Profile
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      {characters.length === 0 && (
        <div 
          className="py-16 text-center border-2 border-dashed rounded-3xl p-8 flex flex-col items-center justify-center max-w-xl mx-auto my-8"
          style={{ borderColor: "var(--color-border)", backgroundColor: "var(--color-box-bg)" }}
        >
          <Sparkles className="w-10 h-10 mb-3 opacity-60" style={{ color: "var(--color-accent)" }} />
          <h3 className="text-base font-bold mb-1" style={{ color: "var(--color-text)" }}>No Character Lore Found Yet</h3>
          <p className="text-xs leading-relaxed max-w-md mb-6" style={{ color: "var(--color-text-muted)" }}>
            The lore engine extracts character traits across chapters. Choose whether to scan Original Translation (OG TL) or all chapters below to populate this database!
          </p>
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5 flex-wrap justify-center w-full max-w-lg">
            <button
              onClick={() => setShowChapterPicker(!showChapterPicker)}
              className="flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl border text-xs font-bold transition-all cursor-pointer shadow-sm"
              style={{
                backgroundColor: selectedChapterIds.length > 0 ? "var(--color-accent-subtle, rgba(234, 88, 12, 0.15))" : "var(--color-surface)",
                borderColor: selectedChapterIds.length > 0 ? "var(--color-accent)" : "var(--color-border)",
                color: selectedChapterIds.length > 0 ? "var(--color-accent)" : "var(--color-text)",
              }}
            >
              <BookOpen className="w-3.5 h-3.5" />
              <span>{selectedChapterIds.length > 0 ? `${selectedChapterIds.length} Chapters Selected` : "Select Chapters"}</span>
              <ChevronDown className={`w-3.5 h-3.5 transition-transform ${showChapterPicker ? "rotate-180" : ""}`} />
            </button>

            <label className="flex items-center justify-center gap-2 cursor-pointer text-xs font-bold px-3 py-2 rounded-xl border select-none transition-all" style={{ backgroundColor: "var(--color-surface)", borderColor: "var(--color-border)", color: "var(--color-text)" }}>
              <input
                type="checkbox"
                checked={onlyOgTl}
                onChange={(e) => setOnlyOgTl(e.target.checked)}
                className="rounded accent-[var(--color-accent)] w-4 h-4 cursor-pointer"
              />
              <span>Extract from OG TL only</span>
            </label>

            <label 
              title="Automatically approve & overwrite character traits without requiring manual review confirmation"
              className="flex items-center justify-center gap-2 cursor-pointer text-xs font-bold px-3 py-2 rounded-xl border select-none transition-all" 
              style={{ 
                backgroundColor: bypassReview ? "rgba(234, 88, 12, 0.12)" : "var(--color-surface)", 
                borderColor: bypassReview ? "var(--color-accent)" : "var(--color-border)", 
                color: bypassReview ? "var(--color-accent)" : "var(--color-text)" 
              }}
            >
              <input
                type="checkbox"
                checked={bypassReview}
                onChange={(e) => setBypassReview(e.target.checked)}
                className="rounded accent-[var(--color-accent)] w-4 h-4 cursor-pointer"
              />
              <span>Bypass Review (Auto-Verify)</span>
            </label>

            <button
              onClick={() => extractLoreMutation.mutate({ onlyOgTl, chapterIds: selectedChapterIds.length > 0 ? selectedChapterIds : undefined, bypassReview })}
              disabled={extractLoreMutation.isPending}
              className="px-5 py-2 rounded-xl text-xs font-bold transition-transform hover:scale-105 active:scale-95 cursor-pointer shadow-md text-white flex items-center justify-center gap-2 w-full sm:w-auto"
              style={{
                background: "linear-gradient(135deg, var(--color-accent) 0%, #ea580c 100%)",
              }}
            >
              {extractLoreMutation.isPending ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                <Sparkles className="w-4 h-4" />
              )}
              <span>
                {extractLoreMutation.isPending
                  ? "Extracting Lore..."
                  : selectedChapterIds.length > 0
                  ? `Scan & Extract Lore (${selectedChapterIds.length} Ch.)`
                  : `Scan & Extract Lore (${onlyOgTl ? "OG TL" : "All Chapters"})`}
              </span>
            </button>
          </div>
        </div>
      )}

      {linkingTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-2xl rounded-3xl border p-6 shadow-2xl max-h-[85vh] flex flex-col overflow-hidden" style={{ backgroundColor: "var(--color-surface)", borderColor: "var(--color-border)", color: "var(--color-text)" }}>
            <div className="flex items-center justify-between border-b pb-4 mb-4" style={{ borderColor: "var(--color-border)" }}>
              <div className="flex items-center gap-2">
                <Link2 className="w-5 h-5" style={{ color: "var(--color-accent)" }} />
                <h3 className="text-lg font-bold">Link & Merge Aliases into "{linkingTarget.canonical}"</h3>
              </div>
              <button onClick={() => setLinkingTarget(null)} className="p-1.5 rounded-lg hover:opacity-80 cursor-pointer border" style={{ borderColor: "var(--color-border)" }}>
                <X className="w-4 h-4" />
              </button>
            </div>
            <p className="text-xs mb-4" style={{ color: "var(--color-text-muted)" }}>
              Select all duplicate or variation cards below to merge into <strong>{linkingTarget.canonical}</strong>. Their aliases and introduction quotes will be preserved, and the duplicate entries will be absorbed.
            </p>
            <div className="flex-1 overflow-y-auto space-y-2 pr-2 mb-4">
              {characters
                .filter((c) => c.id !== linkingTarget.id)
                .map((c) => {
                  const isChecked = selectedMergeIds.includes(c.id);
                  return (
                    <label key={c.id} className="flex items-start gap-3 p-3 rounded-2xl border cursor-pointer transition-all hover:opacity-90" style={{ backgroundColor: isChecked ? "var(--color-accent-subtle, rgba(234,88,12,0.15))" : "var(--color-box-bg)", borderColor: isChecked ? "var(--color-accent)" : "var(--color-border)" }}>
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => {
                          setSelectedMergeIds((prev) =>
                            isChecked ? prev.filter((id) => id !== c.id) : [...prev, c.id]
                          );
                        }}
                        className="mt-1 w-4 h-4 rounded accent-[var(--color-accent)] cursor-pointer"
                      />
                      <div className="flex-1">
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-sm">{c.canonical}</span>
                          <span className="text-xs opacity-70">{c.meta.gender || ""}</span>
                        </div>
                        <p className="text-xs mt-0.5 opacity-80 line-clamp-1">{c.meta.race_or_identity || "No identity noted"}</p>
                      </div>
                    </label>
                  );
                })}
            </div>
            <div className="flex items-center justify-end gap-3 pt-3 border-t" style={{ borderColor: "var(--color-border)" }}>
              <button onClick={() => setLinkingTarget(null)} className="px-4 py-2 rounded-xl text-xs font-bold border cursor-pointer hover:opacity-80" style={{ borderColor: "var(--color-border)" }}>
                Cancel
              </button>
              <button
                disabled={selectedMergeIds.length === 0 || mergeMutation.isPending}
                onClick={() => mergeMutation.mutate({ targetId: linkingTarget.id, sourceIds: selectedMergeIds })}
                className="px-5 py-2 rounded-xl text-xs font-bold text-white shadow-md transition-transform hover:scale-105 active:scale-95 cursor-pointer disabled:opacity-50"
                style={{ background: "linear-gradient(135deg, var(--color-accent) 0%, #ea580c 100%)" }}
              >
                {mergeMutation.isPending ? "Merging..." : `Confirm Merge (${selectedMergeIds.length})`}
              </button>
            </div>
          </div>
        </div>
      )}

      {showDuplicatesModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-4xl rounded-3xl border p-6 shadow-2xl max-h-[88vh] flex flex-col overflow-hidden" style={{ backgroundColor: "var(--color-surface)", borderColor: "var(--color-border)", color: "var(--color-text)" }}>
            <div className="flex items-center justify-between border-b pb-4 mb-4" style={{ borderColor: "var(--color-border)" }}>
              <div className="flex items-center gap-2.5">
                <Search className="w-5 h-5" style={{ color: "var(--color-accent)" }} />
                <div>
                  <h3 className="text-lg font-bold">Automated Entity Deduplication</h3>
                  <p className="text-xs opacity-70">Semantic blocking & evidence verification across character cards</p>
                </div>
              </div>
              <button onClick={() => setShowDuplicatesModal(false)} className="p-1.5 rounded-lg hover:opacity-80 cursor-pointer border" style={{ borderColor: "var(--color-border)" }}>
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto space-y-4 pr-2 mb-4">
              {isDuplicatesLoading ? (
                <div className="p-12 text-center text-sm opacity-60">Scanning character lore for candidate clusters...</div>
              ) : !duplicates || duplicates.length === 0 ? (
                <div className="p-12 text-center border-2 border-dashed rounded-2xl flex flex-col items-center justify-center" style={{ borderColor: "var(--color-border)" }}>
                  <Check className="w-8 h-8 mb-2" style={{ color: "var(--color-success)" }} />
                  <span className="font-bold text-sm">No duplicate clusters found!</span>
                  <span className="text-xs opacity-70 mt-1">All character names are unique according to semantic blocking rules.</span>
                </div>
              ) : (
                duplicates.map((cluster) => {
                  const targetQuotes = (() => {
                    try { return JSON.parse(cluster.target.evidence_contexts || "[]"); } catch { return []; }
                  })();
                  return (
                    <div key={cluster.cluster_id} className="rounded-2xl border p-4 shadow-sm" style={{ backgroundColor: "var(--color-box-bg)", borderColor: "var(--color-border)" }}>
                      <div className="flex items-start justify-between flex-wrap gap-2 mb-3">
                        <div>
                          <span className="text-xs font-bold uppercase tracking-wider px-2 py-0.5 rounded-md border" style={{ borderColor: "var(--color-accent)", color: "var(--color-accent)" }}>
                            Candidate Cluster
                          </span>
                          <span className="text-xs font-medium ml-2 opacity-80">Reason: {cluster.reason}</span>
                        </div>
                        <button
                          disabled={mergeMutation.isPending}
                          onClick={() => mergeMutation.mutate({ targetId: cluster.target.id, sourceIds: cluster.candidates.map((c) => c.id) })}
                          className="px-4 py-1.5 rounded-xl text-xs font-bold text-white shadow-sm transition-transform hover:scale-105 active:scale-95 cursor-pointer disabled:opacity-50 flex items-center gap-1.5"
                          style={{ background: "linear-gradient(135deg, var(--color-accent) 0%, #ea580c 100%)" }}
                        >
                          <GitMerge className="w-3.5 h-3.5" />
                          <span>Merge into "{cluster.target.canonical}"</span>
                        </button>
                      </div>

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
                        <div className="p-3 rounded-xl border" style={{ backgroundColor: "var(--color-surface)", borderColor: "var(--color-success)" }}>
                          <div className="text-xs font-bold uppercase mb-1 flex items-center gap-1" style={{ color: "var(--color-success)" }}>
                            <Check className="w-3.5 h-3.5" /> Target Canonical: {cluster.target.canonical}
                          </div>
                          <p className="text-xs opacity-80 mt-1">{cluster.target.metadata_json ? JSON.parse(cluster.target.metadata_json).race_or_identity || "" : ""}</p>
                          {targetQuotes.length > 0 && (
                            <blockquote className="mt-2 border-l-2 pl-2 text-xs italic opacity-90 border-[var(--color-success)]">
                              "{targetQuotes[0]}"
                            </blockquote>
                          )}
                        </div>

                        <div className="p-3 rounded-xl border space-y-2" style={{ backgroundColor: "var(--color-surface)", borderColor: "var(--color-border)" }}>
                          <div className="text-xs font-bold uppercase mb-1" style={{ color: "var(--color-text-muted)" }}>
                            Candidates to Absorb ({cluster.candidates.length})
                          </div>
                          {cluster.candidates.map((c) => {
                            const cQuotes = (() => {
                              try { return JSON.parse(c.evidence_contexts || "[]"); } catch { return []; }
                            })();
                            return (
                              <div key={c.id} className="text-xs border-t pt-1.5" style={{ borderColor: "var(--color-border)" }}>
                                <span className="font-bold">{c.canonical}</span>
                                {cQuotes.length > 0 && (
                                  <blockquote className="mt-1 border-l-2 pl-2 text-[11px] italic opacity-80 border-[var(--color-border)]">
                                    "{cQuotes[0]}"
                                  </blockquote>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            <div className="flex justify-end pt-3 border-t" style={{ borderColor: "var(--color-border)" }}>
              <button onClick={() => setShowDuplicatesModal(false)} className="px-5 py-2 rounded-xl text-xs font-bold border cursor-pointer hover:opacity-80" style={{ borderColor: "var(--color-border)" }}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

