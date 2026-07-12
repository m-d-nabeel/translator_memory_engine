import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Edit2, Trash2, X, Brush } from "lucide-react";
import { api } from "../api/client";

interface StyleBankTabProps {
  novelId: number;
}

export function StyleBankTab({ novelId }: StyleBankTabProps) {
  const queryClient = useQueryClient();
  const [modal, setModal] = useState<{
    isOpen: boolean;
    mode: "add" | "edit";
    snippetId?: number;
    text: string;
    note: string;
  }>({ isOpen: false, mode: "add", text: "", note: "" });

  const { data: snippets, isLoading } = useQuery({
    queryKey: ["styleSnippets", novelId],
    queryFn: () => api.listStyleSnippets(novelId),
  });

  const createMutation = useMutation({
    mutationFn: (data: { text: string; note?: string }) =>
      api.createStyleSnippet(novelId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["styleSnippets", novelId] });
      setModal((prev) => ({ ...prev, isOpen: false }));
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({
      snippetId,
      data,
    }: {
      snippetId: number;
      data: { text: string; note?: string };
    }) => api.updateStyleSnippet(novelId, snippetId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["styleSnippets", novelId] });
      setModal((prev) => ({ ...prev, isOpen: false }));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (snippetId: number) =>
      api.deleteStyleSnippet(novelId, snippetId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["styleSnippets", novelId] });
    },
  });

  const handleSave = () => {
    if (!modal.text.trim()) return;
    if (modal.mode === "add") {
      createMutation.mutate({ text: modal.text, note: modal.note });
    } else if (modal.snippetId) {
      updateMutation.mutate({
        snippetId: modal.snippetId,
        data: { text: modal.text, note: modal.note },
      });
    }
  };

  return (
    <div className="space-y-4 animate-fade-in">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2
            className="text-xl font-bold flex items-center gap-2"
            style={{ color: "var(--color-text)" }}
          >
            <Brush className="w-5 h-5 text-[var(--color-accent)]" />
            Language Memory (Style Bank)
          </h2>
          <p
            className="text-sm mt-1"
            style={{ color: "var(--color-text-muted)" }}
          >
            Provide manual excerpts to anchor the LLM's stylistic voice for this
            novel.
          </p>
        </div>
        <button
          onClick={() =>
            setModal({ isOpen: true, mode: "add", text: "", note: "" })
          }
          className="flex items-center gap-2 px-4 py-2 text-white rounded-xl text-xs font-bold transition-transform hover:scale-105 active:scale-95 cursor-pointer shadow-sm glow-accent"
          style={{
            background:
              "linear-gradient(135deg, var(--color-accent) 0%, #ea580c 100%)",
          }}
        >
          <Plus className="w-4 h-4" />
          Add Snippet
        </button>
      </div>

      {isLoading ? (
        <div
          className="py-16 text-center text-xs opacity-60"
          style={{ color: "var(--color-text-muted)" }}
        >
          Loading snippets...
        </div>
      ) : snippets && snippets.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {snippets.map((snippet) => (
            <div
              key={snippet.id}
              className="border rounded-2xl p-4 flex flex-col gap-3 group relative overflow-hidden transition-all hover:shadow-md"
              style={{
                backgroundColor: "var(--color-surface)",
                borderColor: "var(--color-border)",
              }}
            >
              <div
                className="text-sm italic whitespace-pre-wrap leading-relaxed"
                style={{ color: "var(--color-text)" }}
              >
                "{snippet.text}"
              </div>
              {snippet.note && (
                <div
                  className="text-xs border-t pt-2 mt-auto font-medium"
                  style={{
                    borderColor: "var(--color-border)",
                    color: "var(--color-text-muted)",
                  }}
                >
                  {snippet.note}
                </div>
              )}
              <div className="absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity bg-[var(--color-surface)] shadow-sm rounded-lg border border-[var(--color-border)] overflow-hidden">
                <button
                  onClick={() =>
                    setModal({
                      isOpen: true,
                      mode: "edit",
                      snippetId: snippet.id,
                      text: snippet.text,
                      note: snippet.note || "",
                    })
                  }
                  className="p-1.5 hover:bg-black/5 transition-colors cursor-pointer"
                  style={{ color: "var(--color-text-muted)" }}
                >
                  <Edit2 className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => {
                    if (confirm("Delete this snippet?")) {
                      deleteMutation.mutate(snippet.id);
                    }
                  }}
                  className="p-1.5 hover:bg-red-500/10 hover:text-red-500 transition-colors cursor-pointer"
                  style={{ color: "var(--color-text-muted)" }}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div
          className="text-center py-12 border border-dashed rounded-3xl glass-surface"
          style={{ borderColor: "var(--color-border)" }}
        >
          <Brush className="w-10 h-10 mx-auto mb-3 opacity-30 text-[var(--color-accent)]" />
          <h3
            className="text-base font-bold"
            style={{ color: "var(--color-text)" }}
          >
            No Style Snippets
          </h3>
          <p
            className="text-xs mt-1"
            style={{ color: "var(--color-text-muted)" }}
          >
            Add some examples of the translator's voice.
          </p>
        </div>
      )}

      {/* Modal */}
      {modal.isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4 animate-fade-in">
          <div
            className="w-full max-w-lg rounded-3xl border border-[var(--color-border)] p-6 shadow-2xl glass-surface animate-slide-up"
            style={{ backgroundColor: "var(--color-surface)" }}
          >
            <div
              className="flex items-center justify-between mb-6 border-b pb-4"
              style={{ borderColor: "var(--color-border)" }}
            >
              <div className="flex items-center gap-2.5">
                <div
                  className="w-9 h-9 rounded-xl flex items-center justify-center text-white"
                  style={{
                    background:
                      "linear-gradient(135deg, var(--color-accent) 0%, #ea580c 100%)",
                  }}
                >
                  <Brush className="w-5 h-5" />
                </div>
                <div>
                  <h3
                    className="text-base font-bold"
                    style={{ color: "var(--color-text)" }}
                  >
                    {modal.mode === "add"
                      ? "Add Style Snippet"
                      : "Edit Style Snippet"}
                  </h3>
                  <p
                    className="text-xs opacity-70"
                    style={{ color: "var(--color-text-muted)" }}
                  >
                    Provide reference material for AI
                  </p>
                </div>
              </div>
              <button
                onClick={() => setModal({ ...modal, isOpen: false })}
                className="w-8 h-8 rounded-full flex items-center justify-center opacity-60 hover:opacity-100 hover:bg-black/5 transition-colors cursor-pointer"
                style={{ color: "var(--color-text)" }}
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label
                  className="block text-xs font-semibold uppercase tracking-wider mb-1.5"
                  style={{ color: "var(--color-text-muted)" }}
                >
                  Text Excerpt (
                  <span className="text-[var(--color-error)]">*</span>)
                </label>
                <textarea
                  className="w-full rounded-xl p-3 text-sm focus:outline-none focus:ring-2 border"
                  style={{
                    backgroundColor: "var(--color-bg)",
                    borderColor: "var(--color-border)",
                    color: "var(--color-text)",
                  }}
                  placeholder="Paste a well-translated sentence or paragraph here..."
                  value={modal.text}
                  onChange={(e) => setModal({ ...modal, text: e.target.value })}
                  rows={5}
                />
              </div>
              <div>
                <label
                  className="block text-xs font-semibold uppercase tracking-wider mb-1.5"
                  style={{ color: "var(--color-text-muted)" }}
                >
                  Note (Optional)
                </label>
                <input
                  type="text"
                  className="w-full rounded-xl p-3 text-sm focus:outline-none focus:ring-2 border"
                  style={{
                    backgroundColor: "var(--color-bg)",
                    borderColor: "var(--color-border)",
                    color: "var(--color-text)",
                  }}
                  placeholder="e.g. Gritty internal monologue"
                  value={modal.note}
                  onChange={(e) => setModal({ ...modal, note: e.target.value })}
                />
              </div>
              <div
                className="flex justify-end gap-3 pt-6 mt-6 border-t"
                style={{ borderColor: "var(--color-border)" }}
              >
                <button
                  onClick={() => setModal({ ...modal, isOpen: false })}
                  className="px-5 py-2.5 rounded-xl text-xs font-bold transition-colors hover:bg-black/5 cursor-pointer border"
                  style={{
                    borderColor: "var(--color-border)",
                    color: "var(--color-text-muted)",
                  }}
                >
                  Cancel
                </button>
                <button
                  onClick={handleSave}
                  disabled={
                    !modal.text.trim() ||
                    createMutation.isPending ||
                    updateMutation.isPending
                  }
                  className="px-5 py-2.5 rounded-xl text-xs font-bold text-white shadow-lg transition-transform hover:scale-105 active:scale-95 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed glow-accent"
                  style={{
                    background:
                      "linear-gradient(135deg, var(--color-accent) 0%, #ea580c 100%)",
                  }}
                >
                  {modal.mode === "add" ? "Save Snippet" : "Update Snippet"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
