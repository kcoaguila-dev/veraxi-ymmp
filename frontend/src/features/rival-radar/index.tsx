import React, { useEffect, useState } from 'react';
import { api, apiUrl } from '../../shared/api';
import type { CorpusData, PatternLibrary } from '../../shared/types';

export const RivalRadar: React.FC = () => {
  const [channelsInput, setChannelsInput] = useState('');
  const [minRatio, setMinRatio] = useState(3.0);
  const [corpus, setCorpus] = useState<CorpusData | null>(null);
  const [patterns, setPatterns] = useState<PatternLibrary | null>(null);
  const [hasApiKey, setHasApiKey] = useState<boolean>(true);
  const [isLoading, setIsLoading] = useState(true);
  const [isScanning, setIsScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadCorpus = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await api.getCorpus();
      setCorpus(res.corpus);
      setPatterns(res.patterns);
      setHasApiKey(res.has_api_key !== false);
      if (res.channels && res.channels.length > 0) {
        setChannelsInput(res.channels.join(', '));
      }
    } catch (e: any) {
      setError(e.data?.error || e.message || 'コーパスの読み込みに失敗しました');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadCorpus();
  }, []);

  const handleScan = async () => {
    const refs = channelsInput
      .split(/[,\n]/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (refs.length === 0) {
      setError('ベンチマーク対象チャンネル (@handle または UC...) を入力してください');
      return;
    }
    setIsScanning(true);
    setError(null);
    try {
      const res = await api.scanCorpus(refs, minRatio);
      setCorpus(res.corpus);
      setPatterns(res.patterns);
    } catch (e: any) {
      setError(e.data?.error || e.message || '外れ値スキャンに失敗しました');
    } finally {
      setIsScanning(false);
    }
  };

  const handleFeedback = async (axis: string, won: boolean) => {
    try {
      const res = await api.recordPatternFeedback({ axis, won });
      setPatterns(res.patterns);
    } catch (e: any) {
      setError(e.data?.error || e.message || 'フィードバック記録に失敗しました');
    }
  };

  return (
    <div className="h-full overflow-y-auto rounded-[14px] bg-[#111827] border border-[#1E293B] shadow-[0_6px_20px_rgba(0,0,0,0.4)] p-5 flex flex-col gap-5 text-[#F8FAFC]">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#1E293B] pb-4">
        <div>
          <h2 className="text-[16px] font-extrabold text-[#F8FAFC] flex items-center gap-2">
            <span>📡 ライバル分析 &amp; トレンド抽出 (Rival Radar)</span>
            {!hasApiKey && (
              <span className="px-2 py-0.5 rounded-[4px] bg-amber-950/70 border border-amber-700/50 text-amber-300 text-[10.5px] font-bold">
                YOUTUBE_API_KEY 未設定
              </span>
            )}
          </h2>
          <p className="text-[11.5px] text-[#94A3B8] mt-0.5">
            競合チャンネルの平均再生数から 3x〜10x の外れ値動画 (Outlier) を自動検出し、タイトル・サムネの勝ちパターン (patterns.json) を更新します。
          </p>
        </div>

        <button
          type="button"
          onClick={loadCorpus}
          disabled={isLoading || isScanning}
          className="h-[30px] px-3 rounded-[6px] bg-[#1E293B] hover:bg-[#334155] text-[#CBD5E1] text-[11.5px] font-semibold disabled:opacity-50"
        >
          ↻ 再読み込み
        </button>
      </div>

      {/* Benchmark Channel Input */}
      <div className="rounded-[10px] bg-[#0B0F19] border border-[#1E293B] p-4 flex flex-col gap-3">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex-1 min-w-[260px]">
            <label className="block text-[11.5px] font-bold text-[#94A3B8] mb-1">
              ベンチマーク対象チャンネル (カンマ区切り: @handle または UC...)
            </label>
            <input
              type="text"
              value={channelsInput}
              onChange={(e) => setChannelsInput(e.target.value)}
              placeholder="@channelA, @channelB, UCxxxxxxxxxxxx"
              className="w-full h-[36px] bg-[#111827] border border-[#334155] focus:border-[#38BDF8] rounded-[6px] px-3 text-[12px] text-[#F8FAFC] focus:outline-none"
            />
          </div>

          <div className="w-[120px]">
            <label className="block text-[11.5px] font-bold text-[#94A3B8] mb-1">
              外れ値倍率
            </label>
            <select
              value={minRatio}
              onChange={(e) => setMinRatio(Number(e.target.value))}
              className="w-full h-[36px] bg-[#111827] border border-[#334155] rounded-[6px] px-2.5 text-[12px] font-bold text-[#F8FAFC]"
            >
              <option value={2.0}>2.0x 以上</option>
              <option value={3.0}>3.0x 以上 (推奨)</option>
              <option value={5.0}>5.0x 以上 (大バズ)</option>
            </select>
          </div>

          <button
            type="button"
            onClick={handleScan}
            disabled={isScanning}
            className="h-[36px] px-4 rounded-[6px] bg-gradient-to-br from-[#0284C7] to-[#0369A1] hover:from-[#0EA5E9] hover:to-[#0284C7] text-white text-[12px] font-extrabold disabled:opacity-50 transition-all whitespace-nowrap"
          >
            {isScanning ? '⏳ スキャン中...' : '📡 外れ値スキャン & パターン更新'}
          </button>
        </div>

        {error && (
          <div className="px-3 py-2 rounded-[6px] bg-rose-950/50 border border-rose-800/60 text-rose-300 text-[11.5px] font-medium">
            {error}
          </div>
        )}
      </div>

      {/* Active Trend Patterns (patterns.json) */}
      {patterns && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="rounded-[10px] bg-[#0B0F19] border border-[#1E293B] p-4 flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <h3 className="text-[13px] font-extrabold text-[#38BDF8]">
                🧠 学習済みタイトル勝ちパターン (patterns.json)
              </h3>
              <span className="text-[10.5px] text-[#64748B] font-mono">
                外れ値 {patterns.source_outliers_count}件反映
              </span>
            </div>

            <div className="flex flex-wrap gap-2 text-[11px]">
              <span className="px-2 py-1 rounded bg-[#1E293B] text-[#E2E8F0] font-semibold">
                先頭フック優先: {patterns.prefer_hook_first ? 'ON (【】タグ省略)' : 'OFF'}
              </span>
              <span className="px-2 py-1 rounded bg-[#1E293B] text-[#E2E8F0] font-semibold">
                バッジ無しミニマル: {patterns.prefer_clean_badge_free ? 'ON' : 'OFF'}
              </span>
              <span className="px-2 py-1 rounded bg-[#1E293B] text-[#E2E8F0] font-semibold">
                平均タイトル長: {patterns.avg_outlier_title_chars}字
              </span>
            </div>

            <div className="flex flex-col gap-2">
              {patterns.title_archetypes.map((arch) => (
                <div
                  key={arch.id}
                  className="p-2.5 rounded-[8px] bg-[#111827] border border-[#1E293B] flex items-center justify-between gap-2"
                >
                  <div className="min-w-0">
                    <div className="text-[12px] font-extrabold text-[#F8FAFC]">
                      {arch.label}{' '}
                      <span className="text-[10.5px] font-mono text-[#38BDF8]">
                        (w={arch.weight.toFixed(2)})
                      </span>
                    </div>
                    <div className="text-[11px] text-[#94A3B8] truncate">{arch.template}</div>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <span className="text-[10.5px] font-mono text-[#94A3B8]">
                      {arch.wins}W/{arch.losses}L
                    </span>
                    <button
                      type="button"
                      onClick={() => handleFeedback(arch.axis, true)}
                      className="px-2 py-1 rounded bg-emerald-950/70 hover:bg-emerald-900 border border-emerald-700/50 text-emerald-300 text-[10.5px] font-bold"
                      title="この軸が勝った"
                    >
                      +Win
                    </button>
                    <button
                      type="button"
                      onClick={() => handleFeedback(arch.axis, false)}
                      className="px-2 py-1 rounded bg-rose-950/70 hover:bg-rose-900 border border-rose-700/50 text-rose-300 text-[10.5px] font-bold"
                      title="この軸が負けた"
                    >
                      -Loss
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-[10px] bg-[#0B0F19] border border-[#1E293B] p-4 flex flex-col gap-3">
            <h3 className="text-[13px] font-extrabold text-[#34D399]">
              🎨 サムネイル構図アーキタイプ &amp; AIスロップ除外
            </h3>
            <div className="flex flex-col gap-2">
              {patterns.layout_archetypes.map((la) => (
                <div
                  key={la.id}
                  className="p-2.5 rounded-[8px] bg-[#111827] border border-[#1E293B] flex items-center justify-between gap-2"
                >
                  <div>
                    <div className="text-[12px] font-extrabold text-[#F8FAFC]">{la.label}</div>
                    <div className="text-[10.5px] text-[#94A3B8]">
                      最大要素数: {la.max_elements} / バッジ: {la.use_badge ? 'あり' : 'なし (モバイル特化)'}
                    </div>
                  </div>
                  <span className="text-[11px] font-mono font-bold text-[#34D399]">
                    w={la.weight.toFixed(2)}
                  </span>
                </div>
              ))}
            </div>
            <div className="text-[11px] text-[#94A3B8]">
              <span className="font-bold text-rose-400">除外ワード:</span>{' '}
              {patterns.anti_slop_phrases.join(' / ')}
            </div>
          </div>
        </div>
      )}

      {/* Outlier Gallery */}
      <div className="flex flex-col gap-3">
        <h3 className="text-[13px] font-extrabold text-[#F8FAFC]">
          🔥 検出されたライバル外れ値動画 ({corpus?.outliers?.length ?? 0}件)
        </h3>
        {!corpus || corpus.outliers.length === 0 ? (
          <div className="p-6 rounded-[10px] bg-[#0B0F19] border border-[#1E293B] text-center text-[12px] text-[#94A3B8]">
            まだ外れ値コーパスがありません。上でベンチマークチャンネルを入力して「外れ値スキャン」を実行してください。
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {corpus.outliers.slice(0, 16).map((item) => {
              const localThumb = item.video_id
                ? apiUrl(`/api/corpus/thumbnails/${encodeURIComponent(item.video_id)}.jpg`)
                : item.thumbnail_url;
              return (
                <div
                  key={item.video_id}
                  className="rounded-[8px] bg-[#0B0F19] border border-[#1E293B] overflow-hidden flex flex-col"
                >
                  <div className="aspect-video bg-[#111827] relative">
                    <img
                      src={localThumb}
                      alt={item.title}
                      className="w-full h-full object-cover"
                      onError={(e) => {
                        if (item.thumbnail_url && e.currentTarget.src !== item.thumbnail_url) {
                          e.currentTarget.src = item.thumbnail_url;
                        }
                      }}
                    />
                    <span className="absolute top-1.5 left-1.5 px-1.5 py-0.5 rounded bg-amber-500 text-[#0B0F19] text-[10.5px] font-black">
                      {item.ratio_vs_mean.toFixed(1)}x
                    </span>
                    <span className="absolute bottom-1.5 right-1.5 px-1.5 py-0.5 rounded bg-[#080C14]/90 text-white text-[10px] font-mono">
                      {item.views.toLocaleString()} views
                    </span>
                  </div>
                  <div className="p-2.5 flex flex-col gap-1">
                    <div className="text-[11.5px] font-bold text-[#F8FAFC] leading-snug line-clamp-2">
                      {item.title}
                    </div>
                    <div className="text-[10.5px] text-[#94A3B8] flex items-center justify-between">
                      <span className="truncate">{item.channel_title}</span>
                      <span className="font-mono shrink-0">{item.published_at.slice(0, 10)}</span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
