import React, { useState, useRef, useEffect } from 'react';
import { useStudioStore } from '../../shared/store';
import { api, apiUrl } from '../../shared/api';
import { LoudnessResult, QaResult } from '../../shared/types';

// The backend pipeline reports real stage keys via its progress callback;
// display them as named stages (Runway-style) instead of leading with a
// percentage. Order follows the pipeline's own sequence.
const PIPELINE_STAGES: { label: string; match: string[] }[] = [
  { label: '準備', match: ['starting'] },
  { label: 'B-roll生成', match: ['rendering_broll'] },
  { label: '音声合成', match: ['synthesizing_audio'] },
  { label: 'YMM4/XML出力', match: ['exporting_ymmp_and_xml'] },
  { label: '動画レンダリング', match: ['moviepy_rendering', 'production_rendering'] },
  { label: '音量正規化', match: ['audio_normalization'] },
];

const stageIndexOf = (stage?: string): number =>
  PIPELINE_STAGES.findIndex((s) => s.match.includes(stage || ''));

export const VideoPreview: React.FC = () => {
  const { projectData, activeProjectName, mediaCacheBust, runPipeline, pipelineStatus, lastValidation, useTts, voicevoxHealth } = useStudioStore();
  const videoRef = useRef<HTMLVideoElement>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [loudness, setLoudness] = useState<LoudnessResult | null>(null);
  const [isNormalizing, setIsNormalizing] = useState(false);
  const [qaResult, setQaResult] = useState<QaResult | null>(null);
  const [isRunningQa, setIsRunningQa] = useState(false);
  const [runStartedAt, setRunStartedAt] = useState<number | null>(null);
  const [elapsedSec, setElapsedSec] = useState(0);

  useEffect(() => {
    if (pipelineStatus.status === 'running') {
      setRunStartedAt((prev) => prev ?? Date.now());
    } else {
      setRunStartedAt(null);
      setElapsedSec(0);
    }
  }, [pipelineStatus.status]);

  useEffect(() => {
    if (runStartedAt === null) return;
    const id = setInterval(
      () => setElapsedSec(Math.floor((Date.now() - runStartedAt) / 1000)),
      500
    );
    return () => clearInterval(id);
  }, [runStartedAt]);

  const activeProjectRef = useRef(activeProjectName);
  useEffect(() => {
    activeProjectRef.current = activeProjectName;
    // QA/loudness results belong to the project (and media revision) they
    // were produced for; never carry them across a project switch.
    setQaResult(null);
    setLoudness(null);
  }, [activeProjectName]);

  const handleQa = async () => {
    if (!activeProjectName) return;
    const projectAtStart = activeProjectName;
    setIsRunningQa(true);
    try {
      const res = await api.runProjectQa(projectAtStart);
      if (activeProjectRef.current !== projectAtStart) return;
      setQaResult(res);
    } catch (e) {
      if (activeProjectRef.current !== projectAtStart) return;
      console.error(e);
      alert('QA 検査に失敗しました (QA audit failed)');
    } finally {
      setIsRunningQa(false);
    }
  };

  const handleGenerate = () => {
    if (lastValidation && !lastValidation.passed) {
      const confirmed = window.confirm(
        `⚠ 監査ゲート警告: Retention ${lastValidation.retention_score}/100` +
        (lastValidation.fact_summary.unsupported > 0
          ? ` / UNSUPPORTED ${lastValidation.fact_summary.unsupported}件`
          : '') +
        '\n監査を通過していませんが、動画生成を続行しますか？'
      );
      if (!confirmed) return;
    }
    // Same guard as the toolbar button: honor the user's TTS toggle and
    // the VOICEVOX online state instead of always requesting TTS.
    runPipeline(useTts && !!voicevoxHealth?.available);
  };

  useEffect(() => {
    const handlePausePreview = () => {
      if (videoRef.current && !videoRef.current.paused) {
        videoRef.current.pause();
      }
    };

    window.addEventListener('veraxi:pause-preview', handlePausePreview);
    return () => {
      window.removeEventListener('veraxi:pause-preview', handlePausePreview);
    };
  }, []);

  const formatTime = (time: number) => {
    if (!Number.isFinite(time) || time < 0) return '00:00';
    const mins = Math.floor(time / 60).toString().padStart(2, '0');
    const secs = Math.floor(time % 60).toString().padStart(2, '0');
    return `${mins}:${secs}`;
  };

  const handleTimeUpdate = () => {
    if (videoRef.current) {
      setCurrentTime(videoRef.current.currentTime);
    }
  };

  const handleLoadedMetadata = () => {
    if (videoRef.current) {
      setDuration(videoRef.current.duration);
    }
  };

  const togglePlay = () => {
    if (!videoRef.current) return;
    if (videoRef.current.paused) {
      // Discontinue any active single-line audition to guarantee audio exclusivity
      window.dispatchEvent(new CustomEvent('veraxi:stop-audition'));
      videoRef.current.play();
    } else {
      videoRef.current.pause();
    }
  };

  const handleSeek = (e: React.MouseEvent<HTMLDivElement>) => {
    if (videoRef.current && duration > 0) {
      const rect = e.currentTarget.getBoundingClientRect();
      const pos = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      videoRef.current.currentTime = pos * duration;
      setCurrentTime(pos * duration);
    }
  };

  const handleNormalize = async () => {
    if (!activeProjectName) return;
    setIsNormalizing(true);
    try {
      const res = await api.normalizeAudio(activeProjectName);
      setLoudness(res);
    } catch (e) {
      console.error(e);
      alert('音量正規化に失敗しました (Normalization failed)');
    }
    setIsNormalizing(false);
  };

  if (!projectData) return null;

  const videoSrc = projectData.qa_video_path
    ? apiUrl(`/api/projects/${encodeURIComponent(activeProjectName!)}/media/qa_test.mp4?t=${mediaCacheBust}`)
    : null;

  const progressPct = duration > 0 ? Math.min(100, Math.max(0, (currentTime / duration) * 100)) : 0;

  const currentStageIdx = stageIndexOf(pipelineStatus.stage);
  const currentStageLabel =
    currentStageIdx >= 0 ? PIPELINE_STAGES[currentStageIdx].label : null;
  const elapsedLabel = `${Math.floor(elapsedSec / 60)}:${String(elapsedSec % 60).padStart(2, '0')}`;

  // Pre-flight summary (Fliki-style): what will actually run, before the
  // expensive button is pressed.
  const dialogueCount = projectData.script.filter(
    (e) => e && (e as any).character && (e as any).text
  ).length;
  const vvOnline = !!voicevoxHealth?.available;
  const ttsEffective = useTts && vvOnline;
  const ttsReason = ttsEffective
    ? 'VOICEVOX で合成'
    : !useTts
      ? 'トグルで No-TTS 指定'
      : 'VOICEVOX 未接続のため No-TTS';

  // QA checks are reviewed failures-first (Opus-style triage).
  const sortedChecks = qaResult
    ? [...qaResult.checks].sort((a, b) => Number(a.passed) - Number(b.passed))
    : [];
  const failedChecks = qaResult ? qaResult.checks.filter((c) => !c.passed) : [];

  return (
    <div className="rounded-[14px] bg-[#111827] border border-[#1E293B] shadow-[0_6px_20px_rgba(0,0,0,0.4)] flex flex-col shrink-0">
      {/* 2. Card Header (Matches SVG lines 219-226) */}
      <div className="min-h-[52px] py-1.5 px-5 border-b border-[#1E293B] flex flex-wrap items-center gap-x-3 gap-y-1.5 justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-[15px] font-extrabold text-[#F8FAFC]">
            2. プレビュー確認
          </h2>
          {pipelineStatus.status === 'running' ? (
            <span className="text-[12px] font-semibold text-[#F59E0B] animate-pulse">
              ⚡ 生成中{currentStageLabel ? `: ${currentStageLabel}` : ''} · {elapsedLabel}
            </span>
          ) : pipelineStatus.status === 'error' ? (
            <span className="text-[12px] font-semibold text-[#F87171]">✗ 生成失敗</span>
          ) : videoSrc ? (
            <span className="text-[12px] font-semibold text-[#34D399]">
              ✓ 生成完了 (qa_test.mp4)
            </span>
          ) : (
            <span className="text-[12px] font-medium text-[#64748B]">
              未生成
            </span>
          )}
        </div>

        <button
          type="button"
          onClick={handleNormalize}
          disabled={isNormalizing || !videoSrc}
          title={
            loudness
              ? `Measured: ${loudness.measured_i.toFixed(1)} LUFS / ${loudness.measured_tp.toFixed(1)} dBTP`
              : 'EBU R128 (-14.0 LUFS) 音量正規化を実行'
          }
          className="h-[26px] px-3.5 rounded-full bg-[#064E3B] hover:bg-[#047857] text-[#A7F3D0] text-[11px] font-bold flex items-center gap-1.5 disabled:opacity-50 transition-colors"
        >
          {isNormalizing
            ? '⏳ 音量解析中...'
            : loudness
            ? `🔊 音量バランス: 最適 (${loudness.measured_i.toFixed(1)} LUFS) ✓`
            : '🔊 音量バランス: 最適 ✓'}
        </button>

        <button
          type="button"
          onClick={handleQa}
          disabled={isRunningQa}
          title="Step 5: TTSカバレッジ・サムネイル・キーフレームの自動QA検査"
          className={`h-[26px] px-3.5 rounded-full text-[11px] font-bold flex items-center gap-1.5 disabled:opacity-50 transition-colors ${
            qaResult
              ? qaResult.passed
                ? 'bg-[#064E3B] text-[#A7F3D0]'
                : 'bg-[#4C0519] text-[#FECDD3]'
              : 'bg-[#1E293B] hover:bg-[#334155] text-[#E2E8F0]'
          }`}
        >
          {isRunningQa
            ? '⏳ QA検査中...'
            : qaResult
            ? qaResult.passed
              ? '🔎 QA 検査: 合格 ✓'
              : '🔎 QA 検査: 不合格 ✗'
            : '🔎 QA 検査 (Keyframe Audit)'}
        </button>
      </div>

      {/* Pre-flight summary: confirm what will run before generating */}
      {pipelineStatus.status !== 'running' && (
        <div className="px-5 py-2 border-b border-[#1E293B] flex flex-wrap items-center gap-1.5 text-[11px] font-semibold text-[#94A3B8]">
          <span className="text-[#64748B] font-bold mr-0.5">生成前チェック:</span>
          <span className="px-2 py-0.5 rounded-full bg-[#1E293B] text-[#E2E8F0]">台本 {dialogueCount} カット</span>
          <span className="px-2 py-0.5 rounded-full bg-[#1E293B] text-[#E2E8F0]">音声: {ttsReason}</span>
          <span
            className={`px-2 py-0.5 rounded-full ${
              lastValidation
                ? lastValidation.passed
                  ? 'bg-[#064E3B] text-[#A7F3D0]'
                  : 'bg-[#4C0519] text-[#FECDD3]'
                : 'bg-[#1E293B] text-[#E2E8F0]'
            }`}
          >
            監査: {lastValidation ? (lastValidation.passed ? '合格' : '不合格 (生成時に確認)') : '未実施'}
          </span>
          {videoSrc && <span className="px-2 py-0.5 rounded-full bg-[#1E293B] text-[#E2E8F0]">既存プレビューあり (再生成で置換)</span>}
          <button
            type="button"
            onClick={handleGenerate}
            className="ml-auto h-[28px] px-4 rounded-[8px] bg-gradient-to-br from-[#10B981] to-[#059669] hover:from-[#34D399] hover:to-[#10B981] text-white text-[12px] font-extrabold shadow-sm transition-all"
          >
            ⚡ 動画を生成 (プレビュー)
          </button>
        </div>
      )}

      {pipelineStatus.status === 'error' && videoSrc && (
        <div className="mx-5 mt-3 bg-[#4C0519] border border-[#F43F5E]/40 text-[#FECDD3] text-[11.5px] font-semibold rounded-[8px] px-3 py-2 break-words">
          ✗ 前回の生成は失敗しました（前回のプレビューはそのまま残しています）: {pipelineStatus.error || 'パイプラインがエラーを返しました'}
        </div>
      )}

      {/* 16:9 Video Canvas (Matches SVG lines 228-260) */}
      <div className="px-5 pt-3.5 pb-2.5">
        <div className="relative w-full aspect-video rounded-[10px] bg-gradient-to-b from-[#1E293B] to-[#090D16] border-[1.5px] border-[#334155] overflow-hidden shadow-inner">
          {pipelineStatus.status === 'running' ? (
            <div className="flex flex-col items-center justify-center w-full h-full text-[#94A3B8] gap-3 p-6 text-center">
              <div className="flex items-center gap-2 text-sm font-bold text-[#34D399] animate-pulse">
                <span className="inline-block w-2.5 h-2.5 rounded-full bg-[#10B981] animate-ping" />
                動画を自動生成中 · 経過 {elapsedLabel}
              </div>
              {/* Named pipeline stages: the current stage is highlighted,
                  finished stages are checked, nothing is a fabricated ETA. */}
              <div className="flex flex-wrap items-center justify-center gap-x-1.5 gap-y-1 max-w-[560px]">
                {PIPELINE_STAGES.map((stage, i) => {
                  const state =
                    currentStageIdx < 0
                      ? 'todo'
                      : i < currentStageIdx
                        ? 'done'
                        : i === currentStageIdx
                          ? 'active'
                          : 'todo';
                  return (
                    <React.Fragment key={stage.label}>
                      {i > 0 && <span className="text-[#475569] text-[10px]">→</span>}
                      <span
                        className={`px-2 py-0.5 rounded-full text-[11px] font-bold ${
                          state === 'done'
                            ? 'bg-[#064E3B] text-[#A7F3D0]'
                            : state === 'active'
                              ? 'bg-[#065F46] text-white animate-pulse'
                              : 'bg-[#1E293B] text-[#64748B]'
                        }`}
                      >
                        {state === 'done' ? '✓ ' : ''}{stage.label}
                      </span>
                    </React.Fragment>
                  );
                })}
              </div>
              <div className="text-xs text-[#E2E8F0] font-medium">
                {pipelineStatus.message || '処理を実行中...'}
              </div>
              <div className="w-64 h-1.5 bg-[#1E293B] rounded-full overflow-hidden border border-[#334155]">
                <div
                  className="h-full bg-gradient-to-r from-[#10B981] to-[#34D399] transition-all duration-300"
                  style={{ width: `${Math.max(5, Math.min(100, pipelineStatus.progress || 0))}%` }}
                />
              </div>
              <div className="text-[11px] text-[#64748B]">
                長編動画（約8分）のため、音声合成・レンダリング完了まで少々お待ちください
              </div>
            </div>
          ) : pipelineStatus.status === 'error' && !videoSrc ? (
            <div className="flex flex-col items-center justify-center w-full h-full text-center gap-3 p-6">
              <div className="text-sm font-bold text-[#F87171]">✗ 動画生成がブロックされました</div>
              <div className="text-xs text-[#FCA5A5] max-w-[520px] break-words">
                {pipelineStatus.error || 'パイプラインがエラーを返しました'}
              </div>
              <div className="text-[11px] text-[#64748B]">
                台本・監査パネルで問題を解消してから、再度「動画を生成」を実行してください
              </div>
            </div>
          ) : videoSrc ? (
            <video
              ref={videoRef}
              className="w-full h-full object-contain cursor-pointer"
              src={videoSrc}
              onClick={togglePlay}
              onPlay={() => {
                window.dispatchEvent(new CustomEvent('veraxi:stop-audition'));
                setIsPlaying(true);
              }}
              onPause={() => setIsPlaying(false)}
              onEnded={() => setIsPlaying(false)}
              onTimeUpdate={handleTimeUpdate}
              onLoadedMetadata={handleLoadedMetadata}
            />
          ) : (
            <div className="flex flex-col items-center justify-center w-full h-full text-[#94A3B8] gap-3 p-6 text-center">
              <div className="text-sm font-bold text-[#F8FAFC]">
                プレビュー動画 (qa_test.mp4) がまだ生成されていません
              </div>
              <div className="text-xs text-[#64748B]">
                上の「⚡ 動画を生成 (プレビュー)」をクリックすると音声・立ち絵・字幕を自動合成します
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Clean Studio Player Controls Bar (Matches SVG lines 262-274) */}
      <div className="px-5 pb-3.5 pt-1 flex items-center gap-4">
        <button
          type="button"
          onClick={togglePlay}
          disabled={!videoSrc}
          className="h-[36px] w-[88px] rounded-[8px] bg-[#10B981] hover:bg-[#34D399] text-[#080C14] text-[13px] font-extrabold flex items-center justify-center gap-1 shrink-0 disabled:opacity-40 transition-colors"
        >
          {isPlaying ? '⏸ 停止' : '▶ 再生'}
        </button>

        <div className="font-mono tabular-nums text-[13px] font-bold text-[#E2E8F0] shrink-0 min-w-[96px]">
          {formatTime(currentTime)} / {formatTime(duration)}
        </div>

        {/* Scrubber Track with Scene Tick Marks & Playhead Thumb */}
        <div
          onClick={handleSeek}
          className="flex-1 h-6 flex items-center cursor-pointer group relative"
          title="クリックしてシーク"
        >
          <div className="w-full h-[8px] rounded-full bg-[#1E293B] relative">
            {/* Scene Tick Marks */}
            <div className="absolute left-1/3 -top-[3px] w-[1.5px] h-[14px] bg-[#64748B]/70 pointer-events-none" />
            <div className="absolute left-2/3 -top-[3px] w-[1.5px] h-[14px] bg-[#64748B]/70 pointer-events-none" />

            {/* Emerald Progress Bar */}
            <div
              className="h-full rounded-full bg-[#10B981] pointer-events-none"
              style={{ width: `${progressPct}%` }}
            />

            {/* Playhead Thumb */}
            <div
              className="w-[14px] h-[14px] rounded-full bg-white border-[2.5px] border-[#10B981] shadow absolute top-1/2 -translate-y-1/2 -translate-x-1/2 pointer-events-none transition-transform group-hover:scale-110"
              style={{ left: `${progressPct}%` }}
            />
          </div>
        </div>

        {/* Fullscreen button */}
        {videoSrc && (
          <button
            type="button"
            onClick={() => videoRef.current?.requestFullscreen?.()}
            title="フルスクリーン表示"
            className="h-[30px] px-2 rounded-[6px] bg-[#1E293B] hover:bg-[#334155] text-[#94A3B8] hover:text-white text-xs font-bold shrink-0 transition-colors"
          >
            ⛶
          </button>
        )}
      </div>

      {/* Step 5 QA Results: checks + milestone keyframe grid */}
      {qaResult && (
        <div className="px-5 pb-4 pt-1 space-y-3">
          <div className={`text-[11.5px] font-extrabold ${failedChecks.length ? 'text-[#FB7185]' : 'text-[#34D399]'}`}>
            {failedChecks.length
              ? `✗ ${failedChecks.length} 件の不合格があります (全 ${qaResult.checks.length} 件中)`
              : `✓ 全 ${qaResult.checks.length} 件のチェックに合格`}
          </div>
          <ul className="space-y-1">
            {sortedChecks.map((check) => (
              <li key={check.name} className="text-[11.5px] font-semibold flex gap-2">
                <span className={check.passed ? 'text-[#34D399]' : 'text-[#FB7185]'}>
                  {check.passed ? '✓' : '✗'}
                </span>
                <span className="text-[#CBD5E1]">
                  {check.name}: {check.detail}
                </span>
              </li>
            ))}
          </ul>
          {failedChecks.length > 0 && qaResult.frames.length > 0 && (
            <div className="bg-[#4C0519] border border-[#F43F5E]/40 text-[#FECDD3] text-[11.5px] font-semibold rounded-[8px] px-3 py-2">
              要確認: {failedChecks.map((c) => c.name).join(' / ')} — 下のキーフレームで該当箇所を確認してください
            </div>
          )}
          {qaResult.frames.length > 0 && (
            <div className="grid grid-cols-2 xl:grid-cols-4 gap-2.5">
              {qaResult.frames.map((frame) => (
                <figure key={frame.key} className="bg-[#0B0F19] border border-[#1E293B] rounded-[8px] overflow-hidden">
                  <img
                    src={apiUrl(`${frame.url}?t=${mediaCacheBust}`)}
                    alt={frame.label}
                    className="w-full aspect-video object-cover"
                  />
                  <figcaption className="px-2 py-1.5 text-[10.5px] font-bold text-[#94A3B8]">
                    {frame.label}
                    {frame.timestamp_sec !== null && ` · ${frame.timestamp_sec}s`}
                    {frame.speaker && ` · ${frame.speaker}`}
                  </figcaption>
                </figure>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
