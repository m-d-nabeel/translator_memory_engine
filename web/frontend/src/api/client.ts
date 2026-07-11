const API_BASE = "/api/v1";

export interface Novel {
  id: number;
  name: string;
  title: string | null;
  source_language: string;
  created_at: string;
  updated_at: string;
  chapter_count: number;
}

export interface NovelDetail extends Novel {
  chapters: ChapterSummary[];
  policy_count: number;
  glossary_count: number;
}

export interface ChapterSummary {
  id: number;
  chapter_number: number;
  source_type: string;
  status: string;
  created_at: string;
}

export interface Chapter {
  id: number;
  novel_id: number;
  chapter_number: number;
  source_type: string;
  raw_text: string;
  refined_text: string | null;
  status: string;
  error_message: string | null;
  processing_time_ms: number | null;
  created_at: string;
}

export interface ChapterRead {
  id: number;
  chapter_number: number;
  raw_text: string;
  refined_text: string | null;
  status: string;
}

export interface ReadableChapter {
  id: number;
  chapter_number: number;
  source_type: string;
  status: string;
}

export interface ChapterNeighbors {
  prev: { id: number; chapter_number: number } | null;
  next: { id: number; chapter_number: number } | null;
}

export interface Policy {
  id: number;
  novel_id: number;
  policy_id: string;
  type: string;
  trigger: string;
  match_forms: string;
  action: string;
  confidence: number;
  evidence_chapters: string | null;
  applies: string;
  note: string | null;
  created_at: string;
}

export interface GlossaryEntry {
  id: number;
  novel_id: number;
  canonical: string;
  aliases: string;
  entity_type: string | null;
  confidence: number | null;
  created_at: string;
}

export interface ProcessingJob {
  id: number;
  chapter_id: number;
  chapter_number?: number | null;
  job_type: string;
  status: string; // queued, running, completed, failed
  started_at?: string;
  completed_at?: string;
  error_message?: string;
  result_summary?: string; // JSON containing mode, deterministic_count, prompted_count, processing_time_ms, logs[]
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  listNovels: () => request<Novel[]>("/novels"),
  getNovel: (id: number) => request<NovelDetail>(`/novels/${id}`),
  createNovel: (data: { name: string; title?: string; source_language?: string }) =>
    request<Novel>("/novels", { method: "POST", body: JSON.stringify(data) }),
  deleteNovel: (id: number) =>
    request<void>(`/novels/${id}`, { method: "DELETE" }),

  createChapter: (novelId: number, data: { chapter_number: number; source_type: string; raw_text: string }) =>
    request<Chapter>(`/novels/${novelId}/chapters`, { method: "POST", body: JSON.stringify(data) }),
  listChapters: (novelId: number, sourceType?: string) => {
    const params = sourceType ? `?source_type=${sourceType}` : "";
    return request<Chapter[]>(`/novels/${novelId}/chapters${params}`);
  },

  processChapter: (chapterId: number, doLlm = true) =>
    request<Chapter>(`/chapters/${chapterId}/process`, {
      method: "POST",
      body: JSON.stringify({ do_llm: doLlm }),
    }),
  reprocessChapter: (chapterId: number, doLlm = true) =>
    request<Chapter>(`/chapters/${chapterId}/reprocess`, {
      method: "POST",
      body: JSON.stringify({ do_llm: doLlm }),
    }),
  chapterStatus: (chapterId: number) =>
    request<Chapter>(`/chapters/${chapterId}/status`),
  readChapter: (chapterId: number) =>
    request<ChapterRead>(`/chapters/${chapterId}/read`),
  readableChapters: (novelId: number) =>
    request<ReadableChapter[]>(`/novels/${novelId}/readable`),
  chapterNeighbors: (novelId: number, chapterId: number) =>
    request<ChapterNeighbors>(`/novels/${novelId}/neighbors/${chapterId}`),

  listPolicies: (novelId: number) =>
    request<Policy[]>(`/novels/${novelId}/policies`),
  listGlossary: (novelId: number) =>
    request<GlossaryEntry[]>(`/novels/${novelId}/glossary`),

  listChapterJobs: (chapterId: number) =>
    request<ProcessingJob[]>(`/jobs/chapter/${chapterId}`),
  listNovelJobs: (novelId: number) =>
    request<ProcessingJob[]>(`/jobs/novel/${novelId}`),
};
