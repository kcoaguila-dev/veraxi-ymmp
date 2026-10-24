import React, { useState, useRef } from 'react';
import { useStudioStore } from '../../shared/store';
import { api } from '../../shared/api';
import { LoudnessResult } from '../../shared/types';

export const VideoPreview: React.FC = () => {
  const { projectData, activeProjectName, mediaCacheBust, runPipeline } = useStudioStore();
  const videoRef = useRef<HTMLVideoElement>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [loudness, setLoudness] = useState<LoudnessResult | null>(null);
  const [isNormalizing, setIsNormalizing] = useState(false);

  const formatTime = (time: number) => {
    const mins = Math.floor(time / 60).toString().padStart(2, '0');
    const secs = (time % 60).toFixed(2).padStart(5, '0');
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

  const handleSeek = (e: React.MouseEvent<HTMLDivElement>) => {
    if (videoRef.current && duration) {
      const rect = e.currentTarget.getBoundingClientRect();
      const pos = (e.clientX - rect.left) / rect.width;
      videoRef.current.currentTime = pos * duration;
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
      alert('Normalization failed');
    }
    setIsNormalizing(false);
  };

  if (!projectData) return null;

  const videoSrc = projectData.qa_video_path
    ? `/api/projects/${activeProjectName}/media/qa_test.mp4?t=${mediaCacheBust}`
    : null;

  return (
    <div className="flex flex-col gap-2 p-4 bg-canvas border-b border-structural">
      <div className="relative w-full aspect-video bg-black rounded overflow-hidden border border-structural">
        {videoSrc ? (
          <video
            ref={videoRef}
            className="w-full h-full object-contain"
            controls
            src={videoSrc}
            onTimeUpdate={handleTimeUpdate}
            onLoadedMetadata={handleLoadedMetadata}
          />
        ) : (
          <div className="flex flex-col items-center justify-center w-full h-full text-gray-500 gap-4">
            <div>No QA video generated yet.</div>
            <button onClick={() => runPipeline(true)} className="bg-emerald-600 hover:bg-emerald-500 text-white font-bold px-4 py-2 rounded">
              ⚡ 動画を生成
            </button>
          </div>
        )}

        {videoSrc && (
            <div
                className="absolute bottom-10 left-0 w-full h-1.5 bg-layer cursor-pointer hover:h-2 transition-all opacity-0 hover:opacity-100"
                onClick={handleSeek}
            >
                <div
                    className="absolute top-0 left-0 h-full bg-zundamon pointer-events-none"
                    style={{ width: `${duration > 0 ? (currentTime / duration) * 100 : 0}%` }}
                ></div>
            </div>
        )}
      </div>
      <div className="flex justify-between items-center text-[#F8FAFC]">
        <div className="font-mono tabular-nums text-sm bg-layer px-2 py-1 rounded">
          {formatTime(currentTime)} / {formatTime(duration)}
        </div>
        <div className="flex gap-2 items-center">
            {loudness && (
                <span className="text-xs text-gray-400">
                    {loudness.measured_i.toFixed(1)} LUFS ({loudness.measured_tp.toFixed(1)} dBTP)
                </span>
            )}
            <button
                onClick={handleNormalize}
                disabled={isNormalizing || !videoSrc}
                className={`px-2 py-1 ${loudness && Math.abs(loudness.measured_i - loudness.target_lufs) < 1.0 ? 'bg-zundamon text-canvas' : 'bg-layer hover:bg-hover text-[#F8FAFC]'} text-xs font-bold rounded disabled:opacity-50 transition-colors`}
            >
            {isNormalizing ? '⏳...' : loudness ? '🔊 音量バランス: 最適 ✓' : '🔊 音量正規化 (-14 LUFS)'}
            </button>
        </div>
      </div>
    </div>
  );
};
