import React, { useState, useEffect } from 'react';
import { useStudioStore } from '../../shared/store';
import { api } from '../../shared/api';

const DEFAULT_TITLES: Record<string, string> = {
  '01_costco_business_model': '【完全解説】なぜコストコは激安でも儲かるのか？最強のビジネスモデル',
  '02_market_analysis_2026': '【2026年最新】AI市場の衝撃と今後のトレンド徹底解説！',
  '03_stock_market_fundamentals_2026': '【投資の基礎】プロが見る優良企業の条件と最強のモートとは？',
};

export const YoutubePublish: React.FC = () => {
  const { projectData, activeProjectName, mediaCacheBust, refreshMedia } = useStudioStore();
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [tags, setTags] = useState('');
  const [privacyStatus, setPrivacyStatus] = useState<'private' | 'unlisted' | 'public'>('private');
  const [publishAt, setPublishAt] = useState('');
  const [mockUpload, setMockUpload] = useState(true);
  const [showAdvanced, setShowAdvanced] = useState(false);

  const [isPublishing, setIsPublishing] = useState(false);
  const [publishResult, setPublishResult] = useState<any>(null);
  const [isRegeneratingThumb, setIsRegeneratingThumb] = useState(false);
  const [thumbLoadFailed, setThumbLoadFailed] = useState(false);

  useEffect(() => {
    if (activeProjectName) {
      setTitle(DEFAULT_TITLES[activeProjectName] || activeProjectName);
      setThumbLoadFailed(false);
    }
  }, [activeProjectName, mediaCacheBust]);

  const handleRegenerateThumb = async () => {
    if (!activeProjectName) return;
    setIsRegeneratingThumb(true);
    try {
      await api.generateThumbnail(activeProjectName);
      setThumbLoadFailed(false);
      await refreshMedia();
    } catch (e) {
      console.error(e);
      alert('サムネイル再生成に失敗しました');
    }
    setIsRegeneratingThumb(false);
  };

  const handlePublish = async () => {
    if (!activeProjectName) return;
    setIsPublishing(true);
    setPublishResult(null);
    try {
      const payload = {
        title,
        description,
        tags: tags.split(',').map(t => t.trim()).filter(Boolean),
        privacy_status: privacyStatus,
        publish_at: publishAt ? new Date(publishAt).toISOString() : undefined,
        mock_upload: mockUpload,
      };
      const res = await api.uploadToYoutube(activeProjectName, payload);
      setPublishResult(res);
    } catch (e: any) {
      console.error(e);
      setPublishResult({ error: e.data?.error || e.message || 'Upload failed' });
    }
    setIsPublishing(false);
  };

  if (!projectData) return null;

  const hasThumb = !!projectData.thumbnail_path && !thumbLoadFailed;

  return (
    <div className="rounded-[14px] bg-[#111827] border border-[#1E293B] shadow-[0_6px_20px_rgba(0,0,0,0.4)] flex flex-col text-[#F8FAFC] shrink-0">
      {/* 3. Card Header (Matches SVG lines 281-284) */}
      <div className="h-[50px] px-5 border-b border-[#1E293B] flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-[15px] font-extrabold text-[#F8FAFC]">
            3. YouTubeサムネイル・投稿
          </h2>
          {publishResult && publishResult.video_id && (
            <a
              href={`https://youtu.be/${publishResult.video_id}`}
              target="_blank"
              rel="noreferrer"
              className="text-[#34D399] text-xs font-bold hover:underline"
            >
              YouTubeで表示 ↗
            </a>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="h-[28px] px-2.5 rounded-[6px] bg-[#1E293B] hover:bg-[#334155] text-[#94A3B8] hover:text-[#F8FAFC] text-[11px] font-semibold transition-colors whitespace-nowrap"
          >
            {showAdvanced ? '▲ 詳細を閉じる' : '⚙ 詳細・予約設定'}
          </button>

          <button
            type="button"
            onClick={handleRegenerateThumb}
            disabled={isRegeneratingThumb}
            className="h-[28px] px-3 rounded-[6px] bg-[#1E293B] hover:bg-[#334155] text-[#38BDF8] text-[11.5px] font-semibold flex items-center gap-1 disabled:opacity-50 transition-colors whitespace-nowrap"
          >
            {isRegeneratingThumb ? '⏳ 生成中...' : '✏ サムネ編集・再生成'}
          </button>
        </div>
      </div>

      {/* Card Body: 16:9 Thumbnail Preview (Left) + Title & Publish Controls (Right) */}
      <div className="p-4 lg:p-5 flex flex-col sm:flex-row gap-5 items-start">
        {/* Left: Fixed-Aspect 3-Split Thumbnail Preview (Matches SVG 240 x 135) */}
        <div className="w-full sm:w-[224px] xl:w-[240px] aspect-video rounded-[8px] border border-[#475569] overflow-hidden relative shrink-0 bg-gradient-to-br from-[#065F46] via-[#0F172A] to-[#881337] shadow-md">
          {hasThumb ? (
            <img
              src={`/api/projects/${encodeURIComponent(activeProjectName!)}/media/thumbnail.png?t=${mediaCacheBust}`}
              alt="YouTube Thumbnail Preview"
              className="w-full h-full object-cover"
              onError={() => setThumbLoadFailed(true)}
            />
          ) : (
            <div className="w-full h-full p-3 flex flex-col justify-between relative select-none">
              <span className="self-start bg-[#EF4444] text-white text-[10px] font-extrabold px-2 py-0.5 rounded-[4px]">
                3分割サムネ
              </span>
              <div>
                <div className="text-[18px] font-black text-[#FDE047] drop-shadow leading-tight">
                  完全自動化！
                </div>
                <div className="text-[12px] font-extrabold text-white drop-shadow">
                  {activeProjectName}
                </div>
              </div>
              <div className="w-11 h-11 rounded-full bg-[#A7F3D0] border-2 border-white flex items-center justify-center text-[8px] font-black text-[#064E3B] absolute right-3 top-1/2 -translate-y-1/2">
                ずんだもん
              </div>
            </div>
          )}

          {/* Timestamp Safe-Zone Indicator Badge */}
          <div className="absolute bottom-1.5 right-1.5 bg-[#080C14]/90 text-white text-[9.5px] font-mono font-bold px-1.5 py-0.5 rounded-[3px]">
            1:30
          </div>
        </div>

        {/* Right: Video Title, Safe-Zone Status, Privacy & Upload CTA (Matches SVG lines 301-315) */}
        <div className="flex-1 min-w-0 w-full flex flex-col gap-2.5">
          <div>
            <label className="block text-[11.5px] font-bold text-[#94A3B8] mb-1">
              動画タイトル
            </label>
            <input
              type="text"
              className="w-full h-[34px] bg-[#0B0F19] border border-[#1E293B] focus:border-[#38BDF8] rounded-[6px] px-3 text-[12px] font-bold text-[#F8FAFC] focus:outline-none transition-colors"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="【完全無料】ずんだもん解説動画をAIで自動生成！"
            />
          </div>

          <div className="flex items-center justify-between gap-2 flex-wrap">
            <span className="text-[11px] font-semibold text-[#34D399]">
              ✓ 3分割レイアウト・右下タイムスタンプ回避済
            </span>

            <label className="flex items-center gap-1.5 text-[11px] text-[#94A3B8] cursor-pointer">
              <input
                type="checkbox"
                checked={mockUpload}
                onChange={(e) => setMockUpload(e.target.checked)}
                className="accent-[#10B981] rounded"
              />
              <span>テスト投稿 (Mock)</span>
            </label>
          </div>

          {/* Expandable Advanced Metadata (Description, Tags, Scheduled Time) */}
          {showAdvanced && (
            <div className="grid grid-cols-1 gap-2 pt-1 pb-1 border-t border-[#1E293B]">
              <textarea
                className="w-full bg-[#0B0F19] border border-[#1E293B] rounded-[6px] px-2.5 py-1.5 text-xs text-[#F8FAFC] h-16 resize-none focus:outline-none focus:border-[#38BDF8]"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="動画の概要欄 (Description)..."
              />
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <input
                  type="text"
                  className="w-full bg-[#0B0F19] border border-[#1E293B] rounded-[6px] px-2.5 py-1.5 text-xs text-[#F8FAFC] focus:outline-none focus:border-[#38BDF8]"
                  value={tags}
                  onChange={(e) => setTags(e.target.value)}
                  placeholder="タグ (カンマ区切り: ずんだもん, 解説)"
                />
                <input
                  type="datetime-local"
                  className="w-full bg-[#0B0F19] border border-[#1E293B] rounded-[6px] px-2.5 py-1.5 text-xs text-[#F8FAFC] focus:outline-none focus:border-[#38BDF8]"
                  value={publishAt}
                  onChange={(e) => {
                    setPublishAt(e.target.value);
                    if (e.target.value) {
                      setPrivacyStatus('private');
                    }
                  }}
                />
              </div>
              {publishAt && (
                <div className="text-[11px] text-amber-400">
                  ※ 予約投稿時は公開設定が自動的に「非公開」に設定されます。
                </div>
              )}
            </div>
          )}

          {/* Action Row: Privacy Dropdown + YouTube Red Gradient CTA */}
          <div className="flex items-center gap-3 mt-0.5">
            <select
              aria-label="公開設定"
              className="h-[40px] px-3 rounded-[8px] bg-[#1E293B] hover:bg-[#334155] border border-[#334155] text-[#E2E8F0] text-[12px] font-bold focus:outline-none cursor-pointer transition-colors shrink-0"
              value={privacyStatus}
              onChange={(e) => setPrivacyStatus(e.target.value as any)}
              disabled={!!publishAt}
            >
              <option value="private">🔒 非公開 (下書き)</option>
              <option value="unlisted">🔗 限定公開</option>
              <option value="public">🌍 公開</option>
            </select>

            <button
              type="button"
              onClick={handlePublish}
              disabled={isPublishing}
              className="flex-1 h-[40px] px-4 rounded-[8px] bg-gradient-to-br from-[#EF4444] to-[#DC2626] hover:from-[#F87171] hover:to-[#EF4444] text-white text-[13px] font-extrabold shadow-md flex items-center justify-center gap-1.5 disabled:opacity-50 transition-all whitespace-nowrap"
            >
              {isPublishing ? '🚀 アップロード中...' : '🚀 YouTubeへ投稿'}
            </button>
          </div>

          {publishResult && (
            <div
              className={`px-3 py-1.5 rounded-[6px] text-xs font-medium ${
                publishResult.error
                  ? 'bg-rose-950/50 border border-rose-800/60 text-rose-300'
                  : 'bg-emerald-950/50 border border-emerald-800/60 text-emerald-300'
              }`}
            >
              {publishResult.error
                ? `エラー: ${publishResult.error}`
                : `投稿完了! Video ID: ${publishResult.video_id} (${publishResult.status})`}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
