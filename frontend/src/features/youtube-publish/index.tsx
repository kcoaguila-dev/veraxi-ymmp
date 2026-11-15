import React, { useState, useEffect, useRef } from 'react';
import { useStudioStore } from '../../shared/store';
import { api, apiUrl } from '../../shared/api';
import type { YoutubeAuthStatus, PackagingData, PackagingPair, PackagingAxis } from '../../shared/types';

const PACKAGING_AXIS_LABELS: Record<PackagingAxis, string> = {
  curiosity: '好奇心',
  result: '実績・数字',
  loss: '損失回避',
};

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

  // YouTube Auth State
  const [authStatus, setAuthStatus] = useState<YoutubeAuthStatus | null>(null);
  const [isAuthLoading, setIsAuthLoading] = useState(false);
  const [clientSecretsInput, setClientSecretsInput] = useState('');
  const [authMessage, setAuthMessage] = useState<{ type: 'info' | 'error'; text: string } | null>(null);

  const [isPublishing, setIsPublishing] = useState(false);
  const [publishResult, setPublishResult] = useState<any>(null);
  const [isRegeneratingThumb, setIsRegeneratingThumb] = useState(false);
  const [thumbLoadFailed, setThumbLoadFailed] = useState(false);

  // Packaging (Test & Compare) candidates state
  const [packaging, setPackaging] = useState<PackagingData | null>(null);
  const [isGeneratingPackaging, setIsGeneratingPackaging] = useState(false);
  const [selectingAxis, setSelectingAxis] = useState<PackagingAxis | null>(null);
  const [packagingError, setPackagingError] = useState<string | null>(null);
  const [packagingImgFailed, setPackagingImgFailed] = useState<Record<string, boolean>>({});
  const [packagingImgRev, setPackagingImgRev] = useState(0);
  const activeProjectRef = useRef<string | null>(activeProjectName);
  activeProjectRef.current = activeProjectName;
  const packagingOpIdRef = useRef(0);

  const fetchAuthStatus = async () => {
    try {
      const res = await api.getYoutubeAuthStatus(true);
      setAuthStatus(res);
    } catch (e) {
      console.debug('Failed to fetch YouTube auth status:', e);
    }
  };

  useEffect(() => {
    fetchAuthStatus();
  }, []);

  useEffect(() => {
    if (activeProjectName) {
      setTitle(DEFAULT_TITLES[activeProjectName] || activeProjectName);
    }
  }, [activeProjectName]);

  useEffect(() => {
    if (activeProjectName) {
      setThumbLoadFailed(false);
    }
  }, [activeProjectName, mediaCacheBust]);

  const handleSaveSecrets = async () => {
    if (!clientSecretsInput.trim()) return;
    setIsAuthLoading(true);
    setAuthMessage(null);
    try {
      const res = await api.saveYoutubeClientSecrets(clientSecretsInput.trim());
      setAuthStatus(res.status);
      setClientSecretsInput('');
      setAuthMessage({ type: 'info', text: 'client_secrets.json を保存しました！' });
    } catch (e: any) {
      setAuthMessage({ type: 'error', text: e.data?.error || e.message || '保存に失敗しました' });
    } finally {
      setIsAuthLoading(false);
    }
  };

  const handleConnectOAuth = async () => {
    setIsAuthLoading(true);
    setAuthMessage({ type: 'info', text: 'ブラウザで Google 認証画面を開いています...' });
    try {
      const res = await api.connectYoutubeAuth();
      setAuthStatus(res.status);
      setAuthMessage({ type: 'info', text: `認証に成功しました！${res.status?.channel?.title ? ` (${res.status.channel.title})` : ''}` });
    } catch (e: any) {
      setAuthMessage({ type: 'error', text: e.data?.error || e.message || '認証に失敗しました' });
    } finally {
      setIsAuthLoading(false);
    }
  };

  const handleRevokeAuth = async () => {
    if (!confirm('YouTube連携を解除しますか？')) return;
    setIsAuthLoading(true);
    setAuthMessage(null);
    try {
      const res = await api.revokeYoutubeAuth();
      setAuthStatus(res.status);
      setAuthMessage({ type: 'info', text: '連携を解除しました。' });
    } catch (e: any) {
      setAuthMessage({ type: 'error', text: e.data?.error || e.message || '解除に失敗しました' });
    } finally {
      setIsAuthLoading(false);
    }
  };

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

  const isStalePackagingOp = (reqProject: string, opId: number) =>
    activeProjectRef.current !== reqProject || packagingOpIdRef.current !== opId;

  const fetchPackaging = async (name: string, opId?: number) => {
    const id = opId ?? ++packagingOpIdRef.current;
    try {
      const res = await api.getPackaging(name);
      if (isStalePackagingOp(name, id)) return;
      const pkg = res.success ? res.packaging : null;
      setPackaging(pkg);
      if (pkg?.selected_axis) {
        const selectedPair = pkg.pairs.find((p) => p.axis === pkg.selected_axis);
        if (selectedPair?.title) {
          setTitle(selectedPair.title);
        }
      }
    } catch (e) {
      if (isStalePackagingOp(name, id)) return;
      console.debug('Failed to fetch packaging candidates:', e);
      setPackaging(null);
    }
  };

  useEffect(() => {
    const opId = ++packagingOpIdRef.current;
    setPackaging(null);
    setPackagingError(null);
    setPackagingImgFailed({});
    setIsGeneratingPackaging(false);
    setSelectingAxis(null);
    if (activeProjectName) {
      fetchPackaging(activeProjectName, opId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeProjectName]);

  const handleGeneratePackaging = async () => {
    const reqProject = activeProjectName;
    if (!reqProject) return;
    const opId = ++packagingOpIdRef.current;
    setIsGeneratingPackaging(true);
    setPackagingError(null);
    try {
      const res = await api.generatePackaging(reqProject);
      if (isStalePackagingOp(reqProject, opId)) return;
      setPackaging(res.packaging);
      setPackagingImgFailed({});
      setPackagingImgRev((r) => r + 1);
    } catch (e: any) {
      if (isStalePackagingOp(reqProject, opId)) return;
      console.error(e);
      setPackagingError(e.data?.error || e.message || '候補の生成に失敗しました');
    } finally {
      if (!isStalePackagingOp(reqProject, opId)) {
        setIsGeneratingPackaging(false);
      }
    }
  };

  const handleSelectPackagingPair = async (pair: PackagingPair) => {
    const reqProject = activeProjectName;
    if (!reqProject) return;
    const opId = ++packagingOpIdRef.current;
    setSelectingAxis(pair.axis);
    setPackagingError(null);
    try {
      const res = await api.selectPackagingPair(reqProject, pair.axis);
      if (isStalePackagingOp(reqProject, opId)) return;
      // The chosen pair becomes thumbnail.png and its title is the publish
      // title (backend also refreshes youtube_metadata.txt).
      setTitle(res.selected?.title || pair.title);
      setThumbLoadFailed(false);
      await fetchPackaging(reqProject, opId);
      if (isStalePackagingOp(reqProject, opId)) return;
      await refreshMedia();
    } catch (e: any) {
      if (isStalePackagingOp(reqProject, opId)) return;
      console.error(e);
      setPackagingError(e.data?.error || e.message || '候補の選択に失敗しました');
    } finally {
      if (!isStalePackagingOp(reqProject, opId)) {
        setSelectingAxis(null);
      }
    }
  };

  const handlePublish = async () => {
    if (!activeProjectName) return;

    // Guardrail: if attempting live upload without auth
    if (!mockUpload && !authStatus?.authenticated) {
      setShowAdvanced(true);
      setAuthMessage({
        type: 'error',
        text: '本番投稿を行うには、先に YouTube API (OAuth2) の連携設定を完了してください。'
      });
      return;
    }

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
      {/* 3. Card Header */}
      <div className="h-[50px] px-5 border-b border-[#1E293B] flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-[15px] font-extrabold text-[#F8FAFC]">
            3. YouTubeサムネイル・投稿
          </h2>

          {/* Auth Status Badge */}
          {authStatus?.authenticated ? (
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-[4px] bg-emerald-950/60 border border-emerald-600/40 text-[#34D399] text-[11px] font-bold">
              <span className="w-1.5 h-1.5 rounded-full bg-[#10B981] animate-pulse"></span>
              {authStatus.channel?.title ? `連携済: ${authStatus.channel.title}` : 'YouTube連携済'}
            </span>
          ) : (
            <button
              type="button"
              onClick={() => setShowAdvanced(true)}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-[4px] bg-[#1E293B] hover:bg-[#334155] border border-[#334155] text-[#94A3B8] hover:text-[#F8FAFC] text-[10.5px] font-semibold transition-colors"
            >
              <span>⚪</span>
              <span>API未連携 (設定)</span>
            </button>
          )}

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
            {showAdvanced ? '▲ 詳細を閉じる' : '⚙ 詳細・API設定'}
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

      {/* Card Body */}
      <div className="p-4 lg:p-5 flex flex-col sm:flex-row gap-5 items-start">
        {/* Left: 16:9 Thumbnail Preview */}
        <div className="w-full sm:w-[224px] xl:w-[240px] aspect-video rounded-[8px] border border-[#475569] overflow-hidden relative shrink-0 bg-gradient-to-br from-[#065F46] via-[#0F172A] to-[#881337] shadow-md">
          {hasThumb ? (
            <img
              src={apiUrl(`/api/projects/${encodeURIComponent(activeProjectName!)}/media/thumbnail.png?t=${mediaCacheBust}`)}
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

          <div className="absolute bottom-1.5 right-1.5 bg-[#080C14]/90 text-white text-[9.5px] font-mono font-bold px-1.5 py-0.5 rounded-[3px]">
            1:30
          </div>
        </div>

        {/* Right: Video Controls */}
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
              <span className={mockUpload ? 'text-[#34D399] font-bold' : 'text-[#EF4444] font-bold'}>
                {mockUpload ? 'テスト投稿 (Mock)' : '🔴 本番YouTube投稿 (Live)'}
              </span>
            </label>
          </div>

          {/* Expandable Advanced Metadata & OAuth2 Setup */}
          {showAdvanced && (
            <div className="flex flex-col gap-3 pt-2 pb-2 border-t border-[#1E293B]">
              {/* OAuth Configuration Box */}
              <div className="p-3 rounded-[8px] bg-[#0B0F19] border border-[#1E293B] flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <span className="text-[11.5px] font-bold text-[#38BDF8]">
                    🔐 YouTube API / OAuth 2.0 連携設定
                  </span>
                  {authStatus?.authenticated && (
                    <button
                      type="button"
                      onClick={handleRevokeAuth}
                      disabled={isAuthLoading}
                      className="text-[10.5px] text-rose-400 hover:text-rose-300 font-semibold underline disabled:opacity-50"
                    >
                      連携解除
                    </button>
                  )}
                </div>

                {authMessage && (
                  <div className={`p-2 rounded-[5px] text-[11px] font-medium ${
                    authMessage.type === 'error'
                      ? 'bg-rose-950/60 border border-rose-800/80 text-rose-300'
                      : 'bg-emerald-950/60 border border-emerald-800/80 text-emerald-300'
                  }`}>
                    {authMessage.text}
                  </div>
                )}

                {!authStatus?.authenticated ? (
                  <div className="flex flex-col gap-2">
                    <p className="text-[11px] text-[#94A3B8] leading-relaxed">
                      Google Cloud Console からダウンロードした <code className="text-[#F8FAFC] font-mono">client_secret.json</code> の内容を貼り付けて保存し、OAuth 認証を実行してください。
                    </p>
                    <textarea
                      className="w-full bg-[#111827] border border-[#1E293B] rounded-[6px] px-2.5 py-1.5 text-[11px] font-mono text-[#F8FAFC] h-16 resize-none focus:outline-none focus:border-[#38BDF8]"
                      value={clientSecretsInput}
                      onChange={(e) => setClientSecretsInput(e.target.value)}
                      placeholder='{"installed": {"client_id": "...", "client_secret": "..."}}'
                    />
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={handleSaveSecrets}
                        disabled={isAuthLoading || !clientSecretsInput.trim()}
                        className="px-3 py-1 rounded-[6px] bg-[#1E293B] hover:bg-[#334155] text-xs font-semibold text-white disabled:opacity-50 transition-colors"
                      >
                        Secrets を保存
                      </button>

                      <button
                        type="button"
                        onClick={handleConnectOAuth}
                        disabled={isAuthLoading || !authStatus?.has_client_secrets}
                        className="px-3 py-1 rounded-[6px] bg-[#0284C7] hover:bg-[#0369A1] text-xs font-semibold text-white disabled:opacity-40 transition-colors"
                      >
                        {isAuthLoading ? '認証中...' : '🔑 Googleアカウントで認証 (OAuth連携)'}
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="text-[11px] text-[#94A3B8] flex items-center justify-between">
                    <span>
                      接続先: <strong className="text-white">{authStatus.channel?.title || 'YouTube Channel'}</strong>
                    </span>
                    <span className="text-[10px] text-emerald-400 font-mono">
                      Token Active (Auto-Refresh 有効)
                    </span>
                  </div>
                )}
              </div>

              {/* Video Metadata Inputs */}
              <div className="grid grid-cols-1 gap-2">
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
            </div>
          )}

          {/* Pre-flight summary: confirm what will be uploaded */}
          <div className="flex flex-wrap items-center gap-1.5 text-[11px] font-semibold text-[#94A3B8]">
            <span className="text-[#64748B] font-bold mr-0.5">投稿前チェック:</span>
            <span className={`px-2 py-0.5 rounded-full ${projectData?.qa_video_path ? 'bg-[#1E293B] text-[#E2E8F0]' : 'bg-[#4C0519] text-[#FECDD3]'}`}>
              動画: {projectData?.qa_video_path ? 'あり' : '未生成'}
            </span>
            <span className={`px-2 py-0.5 rounded-full ${projectData?.thumbnail_path ? 'bg-[#1E293B] text-[#E2E8F0]' : 'bg-[#4C0519] text-[#FECDD3]'}`}>
              サムネイル: {projectData?.thumbnail_path ? 'あり' : '未生成'}
            </span>
            <span className="px-2 py-0.5 rounded-full bg-[#1E293B] text-[#E2E8F0]">
              タイトル: {title.length} 文字
            </span>
            <span className="px-2 py-0.5 rounded-full bg-[#1E293B] text-[#E2E8F0]">
              公開設定: {privacyStatus === 'private' ? '非公開' : privacyStatus === 'unlisted' ? '限定公開' : '公開'}
              {publishAt ? ' (予約)' : ''}
            </span>
            <span className={`px-2 py-0.5 rounded-full ${mockUpload ? 'bg-[#1E293B] text-[#E2E8F0]' : authStatus?.authenticated ? 'bg-[#064E3B] text-[#A7F3D0]' : 'bg-[#4C0519] text-[#FECDD3]'}`}>
              投稿モード: {mockUpload ? 'Mock (テスト)' : authStatus?.authenticated ? '本番' : '本番 (未連携)'}
            </span>
          </div>

          {/* Action Row */}
          <div className="flex flex-wrap items-center gap-3 mt-0.5">
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
              className={`flex-1 min-w-[220px] h-[40px] px-4 rounded-[8px] text-white text-[13px] font-extrabold shadow-md flex items-center justify-center gap-1.5 disabled:opacity-50 transition-all whitespace-nowrap ${
                mockUpload
                  ? 'bg-gradient-to-br from-[#EF4444] to-[#DC2626] hover:from-[#F87171] hover:to-[#EF4444]'
                  : 'bg-gradient-to-br from-[#E11D48] to-[#9F1239] hover:from-[#F43F5E] hover:to-[#BE123C]'
              }`}
            >
              {isPublishing
                ? '🚀 アップロード中...'
                : mockUpload
                ? '🚀 テスト投稿 (Mock) を実行'
                : '🔴 YouTubeへ本番投稿'}
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

      {/* Packaging Candidates (YouTube Test & Compare) */}
      <div className="px-4 lg:px-5 pb-4 lg:pb-5 pt-4 border-t border-[#1E293B] flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-[13px] font-extrabold text-[#F8FAFC]">
              パッケージ候補 (Test &amp; Compare)
            </h3>
            <span className="text-[10.5px] font-semibold text-[#94A3B8]">
              タイトル + サムネイルを3軸 (好奇心 / 実績・数字 / 損失回避) で比較
            </span>
          </div>
          <button
            type="button"
            onClick={handleGeneratePackaging}
            disabled={isGeneratingPackaging || selectingAxis !== null || !activeProjectName}
            className="h-[28px] px-3 rounded-[6px] bg-[#1E293B] hover:bg-[#334155] text-[#38BDF8] text-[11.5px] font-semibold flex items-center gap-1 disabled:opacity-50 transition-colors whitespace-nowrap"
          >
            {isGeneratingPackaging ? '⏳ 生成中... (3案レンダリング中)' : '🎨 候補を生成'}
          </button>
        </div>

        <p className="text-[10.5px] text-[#64748B] font-medium -mt-1">
          {packaging?.score_note || 'ヒューリスティックスコア(CTR予測ではありません)'}
        </p>

        {packagingError && (
          <div className="px-3 py-1.5 rounded-[6px] text-xs font-medium bg-rose-950/50 border border-rose-800/60 text-rose-300">
            エラー: {packagingError}
          </div>
        )}

        {!packaging ? (
          <p className="text-[11.5px] text-[#94A3B8]">
            候補はまだ生成されていません。「候補を生成」で、YouTube Test &amp; Compare 用の3案を作成します (生成には少し時間がかかります)。
          </p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {packaging.pairs.map((pair) => {
              const isRecommended = packaging.recommended_axis === pair.axis;
              const isSelected = packaging.selected_axis === pair.axis;
              const thumbText = [pair.config?.title_line1, pair.config?.title_line2].filter(Boolean).join(' ');
              return (
                <div
                  key={pair.axis}
                  className={`rounded-[8px] bg-[#0B0F19] border flex flex-col overflow-hidden ${
                    isSelected ? 'border-emerald-500/70' : isRecommended ? 'border-amber-500/60' : 'border-[#1E293B]'
                  }`}
                >
                  <div className="aspect-video bg-[#111827] relative shrink-0">
                    {packagingImgFailed[pair.axis] ? (
                      <div className="w-full h-full flex items-center justify-center text-[11px] text-[#94A3B8] font-semibold px-2 text-center">
                        候補画像を読み込めませんでした
                      </div>
                    ) : (
                      <img
                        src={apiUrl(`/api/projects/${encodeURIComponent(activeProjectName!)}/media/${pair.thumbnail_file}?t=${mediaCacheBust}&pkgRev=${packagingImgRev}`)}
                        alt={`${PACKAGING_AXIS_LABELS[pair.axis] || pair.axis} サムネイル候補`}
                        className="w-full h-full object-cover"
                        onError={() => setPackagingImgFailed((prev) => ({ ...prev, [pair.axis]: true }))}
                      />
                    )}
                    <div className="absolute top-1.5 left-1.5 flex gap-1">
                      {isRecommended && (
                        <span className="px-1.5 py-0.5 rounded-[4px] bg-amber-500 text-[#0B0F19] text-[10px] font-extrabold">
                          おすすめ
                        </span>
                      )}
                      {isSelected && (
                        <span className="px-1.5 py-0.5 rounded-[4px] bg-emerald-500 text-[#0B0F19] text-[10px] font-extrabold">
                          選択中
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="p-2.5 flex flex-col gap-1.5 flex-1">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="text-[11.5px] font-extrabold text-[#38BDF8]">
                        {PACKAGING_AXIS_LABELS[pair.axis] || pair.axis}
                      </span>
                      <span className="text-[13px] font-black text-[#F8FAFC]">
                        {pair.total}
                        <span className="text-[10px] font-bold text-[#94A3B8]"> / 100</span>
                      </span>
                    </div>

                    <p className="text-[11.5px] font-bold text-[#F8FAFC] leading-snug">
                      {pair.title}
                    </p>
                    {thumbText && (
                      <p className="text-[10.5px] text-[#94A3B8] leading-snug">
                        サムネ文言: {thumbText}
                      </p>
                    )}

                    <div className="flex flex-wrap gap-1 text-[10px] font-semibold text-[#94A3B8]">
                      <span className="px-1.5 py-0.5 rounded-full bg-[#1E293B]">タイトル {pair.scores.title}</span>
                      <span className="px-1.5 py-0.5 rounded-full bg-[#1E293B]">サムネ文言 {pair.scores.thumbnail_text}</span>
                      <span className="px-1.5 py-0.5 rounded-full bg-[#1E293B]">補完性 {pair.scores.complementarity}</span>
                      <span className="px-1.5 py-0.5 rounded-full bg-[#1E293B]">感情 {pair.scores.emotion}</span>
                      {typeof pair.scores.image === 'number' && (
                        <span className="px-1.5 py-0.5 rounded-full bg-[#1E293B]">画像 {pair.scores.image}</span>
                      )}
                    </div>

                    {pair.issues.length > 0 && (
                      <ul className="text-[10px] text-amber-300/90 leading-snug list-disc pl-3.5">
                        {pair.issues.map((issue, i) => (
                          <li key={i}>{issue}</li>
                        ))}
                      </ul>
                    )}

                    <button
                      type="button"
                      onClick={() => handleSelectPackagingPair(pair)}
                      disabled={isSelected || isGeneratingPackaging || selectingAxis !== null}
                      className={`mt-auto h-[30px] rounded-[6px] text-[11.5px] font-bold transition-colors disabled:opacity-50 ${
                        isSelected
                          ? 'bg-[#064E3B] text-[#A7F3D0] cursor-default'
                          : 'bg-[#0284C7] hover:bg-[#0369A1] text-white'
                      }`}
                    >
                      {isSelected
                        ? '✓ 選択中 (サムネイル適用済)'
                        : selectingAxis === pair.axis
                        ? '⏳ 適用中...'
                        : 'この候補を使う'}
                    </button>
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
