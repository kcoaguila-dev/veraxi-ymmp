import {
  ProjectSummary, ProjectData, PipelineStatus, LoudnessResult,
  YoutubeUploadPayload, VoicevoxHealth, DirectorScriptEntry
} from './types';

export class APIError extends Error {
  constructor(public status: number, public data: any, message: string) {
    super(message);
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

  saveProjectScript: (name: string, script: DirectorScriptEntry[], broll_manifest?: any[]) => fetchAPI<{ success: boolean; warnings?: string[]; valid?: boolean; errors?: string[]; reprompt_block?: string }>(`/api/projects/${encodeURIComponent(name)}/script`, {
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

  auditionVoice: async (text: string, character: string, speed: number = 1.0) => {
    const res = await fetch('/api/voicevox/audition', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, character, speed })
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
  })
};
