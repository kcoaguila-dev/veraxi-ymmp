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

export interface ApiHealth {
  status: string;
  version: string;
  workspace: string;
  ffmpeg_available: boolean;
}

export interface IdeateResult {
  success: boolean;
  project_name: string;
  dossier_markdown: string;
  sources_manifest: Record<string, any>;
}

export interface SourceFileEntry {
  name: string;
  size: number;
  sha256: string;
  extension: string;
}

export interface SourcesResult {
  success: boolean;
  sources: SourceFileEntry[];
  sources_manifest: Record<string, any>;
}

export interface IngestResult {
  success: boolean;
  cut_count: number;
  claim_count: number;
  script: DirectorScriptEntry[];
}

export interface PacingViolation {
  rule_name: string;
  severity: string;
  character: string | null;
  message: string;
  remedy: string;
}

export interface FactClaimResult {
  id: string;
  cut_index: number;
  text: string;
  verdict: 'SUPPORTED' | 'UNSUPPORTED' | 'INSUFFICIENT';
  verdict_raw: string;
  reason: string;
  quote_errors: string[];
  evidence_quotes: string[];
}

export interface ValidateResult {
  success: boolean;
  passed: boolean;
  retention_score: number;
  pacing_is_healthy: boolean;
  pacing_summary: string;
  cast_balance: Record<string, number>;
  character_stats: Record<string, any>;
  pacing_violations: PacingViolation[];
  fact_summary: {
    supported: number;
    unsupported: number;
    insufficient: number;
    total: number;
    claims: FactClaimResult[];
  };
  fact_blocked: boolean;
  fact_report: string | null;
  fact_error: string | null;
}

export interface QaCheck {
  name: string;
  passed: boolean;
  detail: string;
}

export interface QaFrame {
  key: string;
  label: string;
  url: string;
  cut_index: number | null;
  timestamp_sec: number | null;
  speaker: string | null;
  text: string | null;
}

export interface QaResult {
  success: boolean;
  passed: boolean;
  checks: QaCheck[];
  frames: QaFrame[];
  missing_audio: string[];
  coverage_issues: string[];
  thumbnail_issues: string[];
  total_cuts?: number | null;
  video_duration_sec?: number | null;
}

export interface ClipInboxItem {
  name: string;
  size: number;
}

export interface IngestedClip {
  id: string;
  source: string;
  file: string;
  duration_sec: number;
  width: number;
  height: number;
  fps: number;
  has_audio: boolean;
}

export interface ClipsState {
  success: boolean;
  inbox: ClipInboxItem[];
  clips: IngestedClip[];
  error?: string;
}

export interface ClipIngestStatus {
  success: boolean;
  status?: 'running' | 'done';
  ok?: boolean;
  error?: string;
  result?: {
    clips: IngestedClip[];
    rejected: Array<{ source: string; reason: string }>;
    matching_aborted: boolean;
    ingest_aborted: boolean;
    from_manifest?: string | null;
  };
}

export interface NotebooklmVerifyResult {
  success: boolean;
  passed?: boolean;
  supported_count?: number;
  flagged_rows?: Array<Record<string, string>>;
  reprompt_block?: string;
  gate_blockers?: Array<{ claim_id: string; verdict: string; reason: string }>;
  claims_count?: number;
  error?: string;
}

export interface DevPackResult {
  success: boolean;
  pack_id?: string;
  bundle?: string;
  chars?: number;
  files?: string[];
  mode?: string;
  error?: string;
}

export interface DevApplyStatus {
  success: boolean;
  status?: 'running' | 'done';
  exit_code?: number | null;
  output?: string;
  error?: string;
}

export type PackagingAxis = 'curiosity' | 'result' | 'loss';

export interface PackagingPairScores {
  title: number;
  thumbnail_text: number;
  complementarity: number;
  emotion: number;
  image?: number;
  total: number;
}

export interface PackagingPair {
  axis: PackagingAxis;
  title: string;
  config: Record<string, any>;
  thumbnail_file: string;
  scores: PackagingPairScores;
  total: number;
  issues: string[];
  image_qa: Record<string, any>;
}

export interface PackagingData {
  topic: string;
  metric: string;
  recommended_axis: PackagingAxis | null;
  selected_axis: PackagingAxis | string | null;
  score_note: string;
  pairs: PackagingPair[];
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

export interface CorpusOutlier {
  video_id: string;
  channel_id: string;
  channel_title: string;
  title: string;
  views: number;
  baseline_mean_views: number;
  ratio_vs_mean: number;
  published_at: string;
  duration_sec: number;
  thumbnail_url: string;
  thumbnail_file?: string;
}

export interface CorpusData {
  generated_at?: string;
  channels: Array<{
    channel_id: string;
    title: string;
    handle: string;
    baseline_mean_views: number;
    baseline_median_views: number;
    videos_fetched: number;
    videos_eligible: number;
  }>;
  outliers: CorpusOutlier[];
}

export interface PatternTitleArchetype {
  id: string;
  axis: PackagingAxis;
  label: string;
  template: string;
  weight: number;
  wins: number;
  losses: number;
  hook_first: boolean;
}

export interface PatternLayoutArchetype {
  id: string;
  label: string;
  use_badge: boolean;
  max_elements: number;
  weight: number;
  wins: number;
  losses: number;
}

export interface PatternLibrary {
  version: number;
  updated_at: string;
  source_outliers_count: number;
  bracket_tag_rate: number;
  prefer_hook_first: boolean;
  prefer_clean_badge_free: boolean;
  avg_outlier_title_chars: number;
  anti_slop_phrases: string[];
  title_archetypes: PatternTitleArchetype[];
  layout_archetypes: PatternLayoutArchetype[];
  recent_outlier_hooks: Array<{
    video_id: string;
    title: string;
    axis: string;
    ratio_vs_mean: number;
    views: number;
    channel_title: string;
  }>;
}

export interface CorpusResponse {
  success: boolean;
  corpus: CorpusData | null;
  patterns: PatternLibrary;
  channels: string[];
  has_api_key?: boolean;
}
