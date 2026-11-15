import type {
  ProjectSummary, ProjectData, PipelineStatus, LoudnessResult,
  YoutubeUploadPayload, VoicevoxHealth, DirectorScriptEntry, YoutubeAuthStatus,
  ApiHealth, IdeateResult, SourcesResult, IngestResult, ValidateResult, QaResult,
  NotebooklmVerifyResult, DevPackResult, DevApplyStatus,
  ClipsState, ClipIngestStatus,
  PackagingData, PackagingPair, PackagingAxis
} from './types.ts';

interface TauriInternals {
  invoke?: <T = unknown>(cmd: string, args?: Record<string, unknown>) => Promise<T>;
}

declare global {
  interface Window {
    __TAURI_INTERNALS__?: TauriInternals;
  }
}

let cachedApiBaseUrl = '';
let initBaseUrlPromise: Promise<string> | null = null;

export function isTauriRuntime(): boolean {
  return typeof window !== 'undefined' && typeof window.__TAURI_INTERNALS__?.invoke === 'function';
}

export function setApiBaseUrl(url: string): void {
  cachedApiBaseUrl = url.replace(/\/+$/, '');
}

export function getApiBaseUrl(): string {
  return cachedApiBaseUrl;
}

export async function initApiBaseUrl(): Promise<string> {
  if (cachedApiBaseUrl) {
    return cachedApiBaseUrl;
  }
  if (!isTauriRuntime()) {
    return '';
  }
  if (!initBaseUrlPromise) {
    initBaseUrlPromise = window.__TAURI_INTERNALS__!.invoke!<string>('get_api_base_url')
      .then((url) => {
        if (typeof url === 'string' && url.trim()) {
          setApiBaseUrl(url.trim());
        }
        return cachedApiBaseUrl;
      })
      .catch((err) => {
        console.warn('Failed to resolve Tauri API base URL, falling back to relative paths:', err);
        initBaseUrlPromise = null;
        return '';
      });
  }
  return initBaseUrlPromise;
}

export function apiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) {
    return path;
  }
  const normalized = path.startsWith('/') ? path : `/${path}`;
  return cachedApiBaseUrl ? `${cachedApiBaseUrl}${normalized}` : normalized;
}

export class APIError extends Error {
  status: number;
  data: any;

  constructor(status: number, data: any, message: string) {
    super(message);
    this.status = status;
    this.data = data;
    this.name = 'APIError';
  }
}

async function fetchAPI<T>(endpoint: string, options?: RequestInit): Promise<T> {
  await initApiBaseUrl();
  const res = await fetch(apiUrl(endpoint), options);
  if (!res.ok) {
    let errorData = null;
    try {
      errorData = await res.json();
    } catch (e) {
      errorData = await res.text();
    }
    throw new APIError(res.status, errorData, res.statusText);
  }
  return res.json();
}

export const api = {
  getProjects: () => fetchAPI<{ projects: ProjectSummary[] }>('/api/projects'),

  createProject: (name: string) => fetchAPI<{ success: boolean; name: string }>('/api/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name })
  }),

  getProject: (name: string) => fetchAPI<ProjectData>(`/api/projects/${encodeURIComponent(name)}`),

  getProjectHistory: (name: string) => fetchAPI<{
    history: Array<{
      id: string;
      timestamp: string;
      cut_count: number;
      total_chars: number;
      preview: string;
      reason: string;
      has_broll: boolean;
      size_bytes: number;
    }>;
  }>(`/api/projects/${encodeURIComponent(name)}/history`),

  restoreProjectHistory: (name: string, historyId: string) => fetchAPI<{
    success: boolean;
    restored_id: string;
    pre_restore_backup_id: string | null;
    cut_count: number;
    restored_broll: boolean;
    cleaned_audio_count: number;
  }>(`/api/projects/${encodeURIComponent(name)}/history/restore`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ history_id: historyId })
  }),

  saveProjectScript: (name: string, script: DirectorScriptEntry[], broll_manifest?: any[]) => fetchAPI<{ success: boolean; warnings?: string[]; valid?: boolean; errors?: string[]; reprompt_block?: string; backup_created?: string }>(`/api/projects/${encodeURIComponent(name)}/script`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ script, broll_manifest })
  }),

  splitScript: (name: string, script: DirectorScriptEntry[], maxChars: number = 40) => fetchAPI<{ script: DirectorScriptEntry[] }>(`/api/projects/${encodeURIComponent(name)}/script/split`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ script, max_chars: maxChars })
  }),

  packEditProject: (name: string, task: string) => fetchAPI<{ bundle: string; chars: number; files: string[] }>(`/api/projects/${encodeURIComponent(name)}/pack-edit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task })
  }),

  applyEditProject: (name: string, reply: string) => fetchAPI<{ success: boolean; message?: string; reprompt_block?: string; backup_created?: string; error?: string }>(`/api/projects/${encodeURIComponent(name)}/apply-edit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reply })
  }),

  ideate: (topic: string, archetype: string, projectName?: string) => fetchAPI<IdeateResult>('/api/ideate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ topic, archetype, project_name: projectName || undefined })
  }),

  getSources: (name: string) => fetchAPI<SourcesResult>(`/api/projects/${encodeURIComponent(name)}/sources`),

  addSourceUrl: (name: string, url: string, title?: string) => fetchAPI<SourcesResult>(`/api/projects/${encodeURIComponent(name)}/sources`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, title })
  }),

  addSourceFile: (name: string, filename: string, contentBase64: string) => fetchAPI<SourcesResult>(`/api/projects/${encodeURIComponent(name)}/sources`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename, content_base64: contentBase64 })
  }),

  ingestProject: (name: string, payload: { evidence_markdown?: string; dialogue_markdown?: string }) => fetchAPI<IngestResult>(`/api/projects/${encodeURIComponent(name)}/ingest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }),

  validateProject: (name: string) => fetchAPI<ValidateResult>(`/api/projects/${encodeURIComponent(name)}/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({})
  }),

  runProjectQa: (name: string) => fetchAPI<QaResult>(`/api/projects/${encodeURIComponent(name)}/qa`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({})
  }),

  getClips: (name: string) => fetchAPI<ClipsState>(`/api/projects/${encodeURIComponent(name)}/clips`),

  uploadClip: (name: string, filename: string, contentBase64: string) => fetchAPI<ClipsState>(`/api/projects/${encodeURIComponent(name)}/clips/upload`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename, content_base64: contentBase64 })
  }),

  startClipIngest: (name: string, manifestText?: string) => fetchAPI<{ success: boolean; job_id?: string; mode?: string; error?: string }>(`/api/projects/${encodeURIComponent(name)}/clips/ingest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ manifest_text: manifestText || undefined })
  }),

  clipIngestStatus: (name: string, jobId: string) => fetchAPI<ClipIngestStatus>(`/api/projects/${encodeURIComponent(name)}/clips/ingest/status`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ job_id: jobId })
  }),

  generateNotebooklmPrompt: (name: string) => fetchAPI<{ success: boolean; prompt?: string; error?: string }>(`/api/projects/${encodeURIComponent(name)}/notebooklm/prompt`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({})
  }),

  verifyNotebooklm: (name: string, auditMd: string) => fetchAPI<NotebooklmVerifyResult>(`/api/projects/${encodeURIComponent(name)}/notebooklm/verify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ audit_md: auditMd })
  }),

  devSessionStart: () => fetchAPI<{ success: boolean; text?: string; error?: string }>('/api/dev/session-start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({})
  }),

  devPack: (payload: { task: string; files: string[]; mode: 'full' | 'edit'; test?: string }) => fetchAPI<DevPackResult>('/api/dev/pack', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }),

  devApply: (payload: { reply: string; mode: 'full' | 'edit'; pack_id?: string; allow_tests?: boolean; test?: string }) => fetchAPI<{ success: boolean; job_id?: string; error?: string }>('/api/dev/apply', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }),

  devApplyStatus: (jobId: string) => fetchAPI<DevApplyStatus>('/api/dev/apply/status', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ job_id: jobId })
  }),

  getAIPrompt: () => fetchAPI<{ prompt_markdown: string; json_schema: any }>('/api/ai-prompt'),

  getHealth: () => fetchAPI<ApiHealth>('/api/health'),

  waitForBackendReady: async (maxAttempts: number = 30, intervalMs: number = 500): Promise<ApiHealth | null> => {
    await initApiBaseUrl();
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      try {
        return await fetchAPI<ApiHealth>('/api/health');
      } catch {
        if (attempt < maxAttempts - 1) {
          await new Promise((resolve) => setTimeout(resolve, intervalMs));
        }
      }
    }
    return null;
  },

  getWorkspace: () => fetchAPI<{ workspace: string }>('/api/workspace'),

  setWorkspace: (workspace: string) => fetchAPI<{ success: boolean; workspace: string }>('/api/workspace', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ workspace })
  }),

  getVoicevoxHealth: () => fetchAPI<VoicevoxHealth>('/api/voicevox/health'),

  auditionVoice: async (text: string, character: string, speed: number = 1.0, signal?: AbortSignal) => {
    await initApiBaseUrl();
    const res = await fetch(apiUrl('/api/voicevox/audition'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, character, speed }),
      signal
    });
    if (!res.ok) {
        throw new Error('Failed to audition voice');
    }
    return res.blob();
  },

  runPipeline: (name: string, useTts: boolean = true) => fetchAPI<{ success: boolean; message: string }>(`/api/projects/${encodeURIComponent(name)}/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ use_tts: useTts })
  }),

  getPipelineStatus: (name: string) => fetchAPI<PipelineStatus>(`/api/projects/${encodeURIComponent(name)}/status`),

  launchYMM4: (name: string) => fetchAPI<any>(`/api/projects/${encodeURIComponent(name)}/ymm4`, { method: 'POST' }),

  normalizeAudio: (name: string) => fetchAPI<LoudnessResult>(`/api/projects/${encodeURIComponent(name)}/normalize`, { method: 'POST' }),

  generateThumbnail: (name: string) => fetchAPI<any>(`/api/projects/${encodeURIComponent(name)}/thumbnail`, { method: 'POST' }),

  getPackaging: (name: string) => fetchAPI<{ success: boolean; packaging: PackagingData | null }>(`/api/projects/${encodeURIComponent(name)}/packaging`),

  generatePackaging: (name: string) => fetchAPI<{ success: boolean; packaging: PackagingData }>(`/api/projects/${encodeURIComponent(name)}/packaging`, { method: 'POST' }),

  selectPackagingPair: (name: string, axis: PackagingAxis) => fetchAPI<{ success: boolean; selected: PackagingPair }>(`/api/projects/${encodeURIComponent(name)}/packaging/select`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ axis })
  }),

  uploadToYoutube: (name: string, payload: YoutubeUploadPayload) => fetchAPI<any>(`/api/projects/${encodeURIComponent(name)}/youtube`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }),

  getYoutubeAuthStatus: (includeChannel: boolean = true) =>
    fetchAPI<YoutubeAuthStatus>(`/api/youtube/auth/status?include_channel=${includeChannel ? '1' : '0'}`),

  saveYoutubeClientSecrets: (clientSecrets: any) => // pragma: allowlist secret
    fetchAPI<{ success: boolean; status: YoutubeAuthStatus }>('/api/youtube/auth/client-secrets', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: typeof clientSecrets === 'string' // pragma: allowlist secret
        ? JSON.stringify({ client_secrets_json: clientSecrets }) // pragma: allowlist secret
        : JSON.stringify(clientSecrets)
    }),

  connectYoutubeAuth: () =>
    fetchAPI<{ success: boolean; status: YoutubeAuthStatus }>('/api/youtube/auth/connect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    }),

  revokeYoutubeAuth: () =>
    fetchAPI<{ success: boolean; status: YoutubeAuthStatus }>('/api/youtube/auth/revoke', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    })
};
