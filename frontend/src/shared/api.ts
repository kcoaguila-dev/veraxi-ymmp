import type {
  ProjectSummary, ProjectData, PipelineStatus, LoudnessResult,
  YoutubeUploadPayload, VoicevoxHealth, DirectorScriptEntry, YoutubeAuthStatus
} from './types.ts';

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
  const res = await fetch(endpoint, options);
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

  getAIPrompt: () => fetchAPI<{ prompt_markdown: string; json_schema: any }>('/api/ai-prompt'),

  getVoicevoxHealth: () => fetchAPI<VoicevoxHealth>('/api/voicevox/health'),

  auditionVoice: async (text: string, character: string, speed: number = 1.0, signal?: AbortSignal) => {
    const res = await fetch('/api/voicevox/audition', {
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
