export type Emotion = 'normal' | 'neutral' | 'happy' | 'angry' | 'sad' | 'surprised' | 'confused' | 'scared' | 'excited' | 'disgusted' | 'smug' | 'crying' | 'blushing';
export type Motion = 'none' | 'jump' | 'nod';
export type CharacterPosition = 'left' | 'center' | 'right';
export type SubtitlePosition = 'top_center' | 'center' | 'bottom_center';
export type SubtitleStyle = 'default' | 'outlined';

export interface DirectorScriptEntry {
  type?: string;
  character?: string;
  text?: string;
  path?: string;
  volume?: number;
  emotion?: Emotion;
  motion?: Motion;
  bgm?: string | null;
  sfx?: string | null;
  image?: string | null;
  bg?: string | null;
  character_position?: CharacterPosition;
  subtitle_position?: SubtitlePosition;
  subtitle_style?: SubtitleStyle;
  [key: string]: any;
}

export interface ProjectSummary {
  name: string;
  path: string;
  has_script: boolean;
  has_broll_manifest: boolean;
  has_qa_video: boolean;
  has_thumbnail: boolean;
}

export interface ProjectData {
  name: string;
  script: DirectorScriptEntry[];
  broll_manifest: any[];
  qa_video_path: string | null;
  thumbnail_path: string | null;
  ymmp_path: string | null;
  premiere_xml: string | null;
}

export interface PipelineStatus {
  status: 'idle' | 'running' | 'complete' | 'error';
  stage?: string;
  progress?: number;
  message?: string;
  result?: any;
  error?: string;
}

export interface LoudnessResult {
  output_path: string;
  target_lufs: number;
  measured_i: number;
  measured_tp: number;
}

export interface YoutubeUploadPayload {
  title: string;
  description: string;
  tags?: string[];
  privacy_status: 'private' | 'unlisted' | 'public';
  publish_at?: string;
  mock_upload: boolean;
}

export interface VoicevoxHealth {
  available: boolean;
  url: string;
  speakers: any[];
}

export interface YoutubeAuthStatus {
  has_client_secrets: boolean;
  has_token: boolean;
  authenticated: boolean;
  expired: boolean;
  scopes: string[];
  client_secrets_path: string | null;
  token_path: string | null;
  channel?: {
    id: string;
    title: string;
    custom_url?: string;
    subscriber_count?: number;
    video_count?: number;
  };
}
