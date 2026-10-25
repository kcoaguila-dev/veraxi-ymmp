import React, { useState, useRef, useEffect } from 'react';
import { useStudioStore } from '../../shared/store';
import { api } from '../../shared/api';
import { LoudnessResult } from '../../shared/types';

export const VideoPreview: React.FC = () => {
  const { projectData, activeProjectName, mediaCacheBust, runPipeline } = useStudioStore();
  const videoRef = useRef<HTMLVideoElement>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [loudness, setLoudness] = useState<LoudnessResult | null>(null);
  const [isNormalizing, setIsNormalizing] = useState(false);

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
    ? `/api/projects/${encodeURIComponent(activeProjectName!)}/media/qa_test.mp4?t=${mediaCacheBust}`
    : null;

  const progressPct = duration > 0 ? Math.min(100, Math.max(0, (currentTime / duration) * 100)) : 0;

  return (
    <div className="rounded-[14px] bg-[#111827] border border-[#1E293B] shadow-[0_6px_20px_rgba(0,0,0,0.4)] flex flex-col shrink-0">
      {/* 2. Card Header (Matches SVG lines 219-226) */}
      <div className="h-[52px] px-5 border-b border-[#1E293B] flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-[15px] font-extrabold text-[#F8FAFC]">
            2. プレビュー確認
          </h2>
          {videoSrc ? (
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
      </div>

      {/* 16:9 Video Canvas (Matches SVG lines 228-260) */}
      <div className="px-5 pt-3.5 pb-2.5">
        <div className="relative w-full aspect-video rounded-[10px] bg-gradient-to-b from-[#1E293B] to-[#090D16] border-[1.5px] border-[#334155] overflow-hidden shadow-inner">
          {videoSrc ? (
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
              <button
                onClick={() => runPipeline(true)}
                className="mt-1 bg-gradient-to-br from-[#10B981] to-[#059669] hover:from-[#34D399] hover:to-[#10B981] text-white font-extrabold px-4 py-2 rounded-[8px] text-xs shadow"
              >
                ⚡ 動画を生成 (プレビュー)
              </button>
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
    </div>
  );
};
