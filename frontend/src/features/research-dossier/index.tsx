import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useStudioStore } from '../../shared/store';
import { api } from '../../shared/api';
import type { SourcesResult, ClipsState, ClipIngestStatus, PackagingData, PackagingAxis } from '../../shared/types';

const ARCHETYPES: Array<{ key: string; label: string }> = [
  { key: 'post_mortem', label: 'Post-Mortem / 失敗の解剖' },
  { key: 'myth_vs_reality', label: 'Myth vs. Reality / 通説 vs. 文書' },
  { key: 'david_vs_goliath', label: 'David vs. Goliath / 法的・技術的対決' },
  { key: 'gold_rush', label: 'Gold Rush / 熱狂とボトルネック' },
];

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || '');
      resolve(result.includes(',') ? result.split(',')[1] : result);
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

interface ResearchDossierProps {
  onIngestDone?: () => void;
}

export const ResearchDossier: React.FC<ResearchDossierProps> = ({ onIngestDone }) => {
  const { activeProjectName, loadProjects, setActiveProject, refreshMedia, workspacePath } = useStudioStore();
  const [topic, setTopic] = useState('');
  const [archetype, setArchetype] = useState('post_mortem');
  const [projectName, setProjectName] = useState('');
  const [dossier, setDossier] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [prePackaging, setPrePackaging] = useState<PackagingData | null>(null);
  const [isPrePackaging, setIsPrePackaging] = useState(false);
  const [prePkgMsg, setPrePkgMsg] = useState<string | null>(null);

  const handlePreScriptPackaging = async () => {
    if (!activeProjectName) return;
    setIsPrePackaging(true);
    setPrePkgMsg(null);
    try {
      const res = await api.generatePackaging(activeProjectName);
      setPrePackaging(res.packaging);
      setPrePkgMsg('3軸フックを生成しました。台本執筆前に軸をロックできます。');
    } catch (e: any) {
      setPrePkgMsg(e.data?.error || e.message || 'フック生成に失敗しました');
    } finally {
      setIsPrePackaging(false);
    }
  };

  const handleLockPrePackaging = async (axis: PackagingAxis) => {
    if (!activeProjectName) return;
    try {
      const res = await api.selectPackagingPair(activeProjectName, axis);
      setPrePackaging((prev) => (prev ? { ...prev, selected_axis: axis } : prev));
      setPrePkgMsg(`✓ 「${res.selected?.title}」を仮ロックしました（冒頭15秒で回収してください）`);
      await refreshMedia();
    } catch (e: any) {
      setPrePkgMsg(e.data?.error || e.message || 'ロックに失敗しました');
    }
  };
  const [copyMsg, setCopyMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [sources, setSources] = useState<SourcesResult | null>(null);
  const [sourceUrl, setSourceUrl] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [evidenceMd, setEvidenceMd] = useState('');
  const [dialogueMd, setDialogueMd] = useState('');
  const [isIngesting, setIsIngesting] = useState(false);
  const [ingestMsg, setIngestMsg] = useState<string | null>(null);

  const sourcesRequestRef = useRef(0);
  const reloadSources = useCallback(async () => {
    if (!activeProjectName) {
      setSources(null);
      return;
    }
    const requestId = ++sourcesRequestRef.current;
    try {
      const res = await api.getSources(activeProjectName);
      // A slower response for a previously selected project must not
      // overwrite the current project's source list.
      if (sourcesRequestRef.current === requestId) setSources(res);
    } catch {
      if (sourcesRequestRef.current === requestId) setSources(null);
    }
  }, [activeProjectName]);

  useEffect(() => {
    reloadSources();
  }, [reloadSources]);

  const [clips, setClips] = useState<ClipsState | null>(null);
  const [clipManifest, setClipManifest] = useState('');
  const [clipBusy, setClipBusy] = useState(false);
  const [clipMsg, setClipMsg] = useState<string | null>(null);
  const [clipError, setClipError] = useState<string | null>(null);
  const [clipResult, setClipResult] = useState<ClipIngestStatus | null>(null);
  const clipFileInputRef = useRef<HTMLInputElement>(null);
  const clipsRequestRef = useRef(0);

  const reloadClips = useCallback(async () => {
    if (!activeProjectName) {
      setClips(null);
      return;
    }
    const requestId = ++clipsRequestRef.current;
    try {
      const res = await api.getClips(activeProjectName);
      if (clipsRequestRef.current === requestId) setClips(res);
    } catch {
      if (clipsRequestRef.current === requestId) setClips(null);
    }
  }, [activeProjectName]);

  useEffect(() => {
    reloadClips();
  }, [reloadClips]);

  const uploadClipFiles = async (files: FileList | File[]) => {
    if (!activeProjectName) return;
    setClipError(null);
    setClipMsg(null);
    try {
      for (const file of Array.from(files)) {
        const b64 = await fileToBase64(file);
        await api.uploadClip(activeProjectName, file.name, b64);
      }
      await reloadClips();
      setClipMsg('✓ クリップを clip_inbox へアップロードしました');
    } catch (e: any) {
      setClipError(e?.data?.error || e?.message || 'クリップのアップロードに失敗しました');
    }
  };

  const handleClipIngest = async () => {
    if (!activeProjectName || clipBusy) return;
    const projectAtStart = activeProjectName;
    setClipBusy(true);
    setClipError(null);
    setClipMsg(null);
    setClipResult(null);
    try {
      const start = await api.startClipIngest(
        projectAtStart,
        clipManifest.trim() ? clipManifest : undefined
      );
      if (!start.success || !start.job_id) {
        setClipError(start.error || 'クリップ取込を開始できませんでした');
        setClipBusy(false);
        return;
      }
      const jobId = start.job_id;
      const poll = async () => {
        try {
          const status = await api.clipIngestStatus(projectAtStart, jobId);
          if (status.status === 'done') {
            setClipResult(status);
            setClipBusy(false);
            await reloadClips();
          } else {
            window.setTimeout(poll, 1500);
          }
        } catch (e: any) {
          setClipError(e?.data?.error || e?.message || 'クリップ取込状況の取得に失敗しました');
          setClipBusy(false);
        }
      };
      void poll();
    } catch (e: any) {
      setClipError(e?.data?.error || e?.message || 'クリップ取込を開始できませんでした');
      setClipBusy(false);
    }
  };

  // Evidence/dialogue drafts are scoped to (workspace, project): stash them
  // under the previous scope on switch and restore the new scope's drafts,
  // so text pasted for project A never leaks into project B — including a
  // same-named project in a different workspace.
  const draftsRef = useRef<Record<string, { evidence: string; dialogue: string }>>({});
  const scopeKey = `${workspacePath ?? ''}::${activeProjectName ?? ''}`;
  const prevScopeRef = useRef<string | null>(null);
  useEffect(() => {
    const prev = prevScopeRef.current;
    if (prev !== scopeKey) {
      if (prev !== null) {
        draftsRef.current[prev] = { evidence: evidenceMd, dialogue: dialogueMd };
      }
      const stash = draftsRef.current[scopeKey];
      setEvidenceMd(stash?.evidence ?? '');
      setDialogueMd(stash?.dialogue ?? '');
      prevScopeRef.current = scopeKey;
    }
  }, [scopeKey, evidenceMd, dialogueMd]);

  const handleGenerateDossier = async () => {
    if (!topic.trim()) return;
    setIsGenerating(true);
    setErrorMsg(null);
    try {
      const res = await api.ideate(topic.trim(), archetype, projectName.trim() || undefined);
      setDossier(res.dossier_markdown);
      await loadProjects(res.project_name);
      await setActiveProject(res.project_name);
    } catch (e: any) {
      setErrorMsg(e?.data?.error || e?.message || 'Dossier 生成に失敗しました');
    }
    setIsGenerating(false);
  };

  const handleCopyDossier = async () => {
    if (!dossier) return;
    await navigator.clipboard.writeText(dossier);
    setCopyMsg('✓ NotebookLM 用 Dossier をコピーしました');
    setTimeout(() => setCopyMsg(null), 4000);
  };

  const uploadFiles = async (files: FileList | File[]) => {
    if (!activeProjectName) return;
    setErrorMsg(null);
    try {
      for (const file of Array.from(files)) {
        const b64 = await fileToBase64(file);
        await api.addSourceFile(activeProjectName, file.name, b64);
      }
      await reloadSources();
    } catch (e: any) {
      setErrorMsg(e?.data?.error || e?.message || 'ソースのアップロードに失敗しました');
    }
  };

  const handleRegisterUrl = async () => {
    if (!activeProjectName || !sourceUrl.trim()) return;
    setErrorMsg(null);
    try {
      await api.addSourceUrl(activeProjectName, sourceUrl.trim());
      setSourceUrl('');
      await reloadSources();
    } catch (e: any) {
      setErrorMsg(e?.data?.error || e?.message || 'URL 登録に失敗しました');
    }
  };

  const handleIngest = async () => {
    if (!activeProjectName) return;
    setIsIngesting(true);
    setErrorMsg(null);
    setIngestMsg(null);
    try {
      const res = await api.ingestProject(activeProjectName, {
        evidence_markdown: evidenceMd.trim() ? evidenceMd : undefined,
        dialogue_markdown: dialogueMd.trim() ? dialogueMd : undefined,
      });
      setIngestMsg(`✓ 取込完了: ${res.cut_count} カット / ${res.claim_count} クレーム`);
      await refreshMedia();
      onIngestDone?.();
    } catch (e: any) {
      setErrorMsg(e?.data?.error || e?.message || '取込に失敗しました');
    }
    setIsIngesting(false);
  };

  const manifestEntries = sources
    ? Object.entries(sources.sources_manifest).filter(([, v]) => v && typeof v === 'object')
    : [];

  return (
    <div className="flex flex-col h-full bg-[#111827] text-[#F8FAFC] overflow-y-auto">
      <div className="h-[54px] px-5 border-b border-[#1E293B] flex items-center shrink-0">
        <h2 className="text-[15px] font-extrabold">1. リサーチ &amp; 素材</h2>
      </div>

      <div className="p-5 space-y-6">
        {errorMsg && (
          <div className="bg-[#4C0519] border border-[#F43F5E]/40 text-[#FECDD3] text-xs font-semibold rounded-[8px] px-3 py-2">
            {errorMsg}
          </div>
        )}

        {/* Step 1: Topic ideation */}
        <section className="space-y-2.5">
          <h3 className="text-[13px] font-extrabold text-[#34D399]">Step 1 — トピック &amp; Dossier 生成</h3>
          <input
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="トピック (例: 2026年 サーバ障害の全貌)"
            className="w-full bg-[#1E293B] border border-[#334155] rounded-[8px] px-3 py-2 text-[13px] focus:outline-none focus:border-[#10B981]"
          />
          <div className="flex gap-2">
            <select
              value={archetype}
              onChange={(e) => setArchetype(e.target.value)}
              className="flex-1 bg-[#1E293B] border border-[#334155] rounded-[8px] px-2 py-2 text-[12.5px] focus:outline-none focus:border-[#10B981]"
            >
              {ARCHETYPES.map((a) => (
                <option key={a.key} value={a.key}>{a.label}</option>
              ))}
            </select>
            <input
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
              placeholder="プロジェクト名 (任意)"
              className="flex-1 bg-[#1E293B] border border-[#334155] rounded-[8px] px-3 py-2 text-[12.5px] focus:outline-none focus:border-[#10B981]"
            />
          </div>
          <button
            onClick={handleGenerateDossier}
            disabled={isGenerating || !topic.trim()}
            className="h-[34px] px-4 rounded-[8px] bg-gradient-to-br from-[#10B981] to-[#059669] text-white text-[12.5px] font-extrabold disabled:opacity-50"
          >
            {isGenerating ? '⏳ 生成中...' : '📋 Dossier 生成'}
          </button>

          {dossier && (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <button
                  onClick={handleCopyDossier}
                  className="h-[26px] px-3 rounded-full bg-[#064E3B] text-[#A7F3D0] text-[11px] font-bold"
                >
                  📋 NotebookLM へコピー
                </button>
                {copyMsg && <span className="text-[11px] text-[#34D399] font-semibold">{copyMsg}</span>}
              </div>
              <pre className="max-h-64 overflow-y-auto bg-[#0B0F19] border border-[#1E293B] rounded-[8px] p-3 text-[11px] leading-relaxed whitespace-pre-wrap">
                {dossier}
              </pre>
            </div>
          )}
        </section>

        {/* Step 1.5: Sources */}
        <section className="space-y-2.5">
          <h3 className="text-[13px] font-extrabold text-[#34D399]">一次ソース (sources/)</h3>
          {!activeProjectName ? (
            <p className="text-[12px] text-[#94A3B8]">プロジェクトを選択または生成してください。</p>
          ) : (
            <>
              <div
                role="button"
                tabIndex={0}
                aria-label="ソースファイルをアップロード"
                onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={(e) => { e.preventDefault(); setIsDragging(false); uploadFiles(e.dataTransfer.files); }}
                onClick={() => fileInputRef.current?.click()}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    fileInputRef.current?.click();
                  }
                }}
                className={`border-[1.5px] border-dashed rounded-[10px] p-4 text-center text-[12px] cursor-pointer transition-colors focus:outline-none focus:border-[#10B981] ${
                  isDragging ? 'border-[#10B981] bg-[#064E3B]/40 text-[#A7F3D0]' : 'border-[#334155] text-[#94A3B8] hover:border-[#475569]'
                }`}
              >
                .pdf / .md / .html / .txt をドラッグ＆ドロップ (またはクリックして選択)
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept=".pdf,.md,.html,.htm,.txt"
                  className="hidden"
                  onChange={(e) => { if (e.target.files) uploadFiles(e.target.files); e.target.value = ''; }}
                />
              </div>
              <div className="flex gap-2">
                <input
                  value={sourceUrl}
                  onChange={(e) => setSourceUrl(e.target.value)}
                  placeholder="ソース URL を登録 (https://...)"
                  className="flex-1 bg-[#1E293B] border border-[#334155] rounded-[8px] px-3 py-1.5 text-[12px] focus:outline-none focus:border-[#10B981]"
                />
                <button
                  onClick={handleRegisterUrl}
                  disabled={!sourceUrl.trim()}
                  className="h-[30px] px-3 rounded-[7px] bg-[#1E293B] border border-[#475569] text-[11.5px] font-bold disabled:opacity-50"
                >
                  URL 登録
                </button>
              </div>
              {sources && sources.sources.length > 0 && (
                <ul className="space-y-1">
                  {sources.sources.map((s) => (
                    <li key={s.name} className="text-[11.5px] font-mono text-[#CBD5E1] bg-[#0B0F19] border border-[#1E293B] rounded-[6px] px-2.5 py-1.5 flex justify-between gap-2">
                      <span className="truncate">{s.name}</span>
                      <span className="text-[#64748B] shrink-0">{s.sha256.slice(0, 10)}…</span>
                    </li>
                  ))}
                </ul>
              )}
              {manifestEntries.length > 0 && (
                <p className="text-[11px] text-[#64748B]">
                  manifest 登録済み: {manifestEntries.map(([k, v]) => {
                    const url = (v as { url?: unknown })?.url;
                    return typeof url === 'string' && url ? `${k} (${url})` : k;
                  }).join(', ')}
                </p>
              )}
            </>
          )}
        </section>

        {/* Step 1b: External AI clip ingest (ingest-clips) */}
        <section className="space-y-2.5">
          <h3 className="text-[13px] font-extrabold text-[#34D399]">外部AIクリップ取込 (clips/)</h3>
          <p className="text-[11px] text-[#64748B]">
            Web AI等で生成した動画クリップを clip_inbox へ入れ、プロジェクト規格 (1920x1080/60fps) へ正規化して取り込みます。
            マニフェスト (JSON) を貼ると宣言されたクリップだけを厳密に照合し、未宣言ファイルがあれば<strong className="text-[#FDE68A]">何も書かずに中断</strong>します。空欄なら inbox 全件を自動IDで取り込みます。
          </p>
          <div className="flex items-center gap-2 flex-wrap">
            <input
              ref={clipFileInputRef}
              type="file"
              accept="video/*,.mkv"
              multiple
              className="hidden"
              aria-label="クリップファイルをアップロード"
              onChange={(e) => {
                if (e.target.files) void uploadClipFiles(e.target.files);
                e.target.value = '';
              }}
            />
            <button
              type="button"
              onClick={() => clipFileInputRef.current?.click()}
              disabled={!activeProjectName}
              className="h-[30px] px-3 rounded-[7px] bg-[#1E293B] border border-[#475569] text-[11.5px] font-bold disabled:opacity-50"
            >
              🎬 クリップを追加
            </button>
            {clips && clips.inbox.length > 0 && (
              <span className="text-[11px] text-[#94A3B8]">
                inbox: {clips.inbox.map((c) => `${c.name} (${Math.max(1, Math.round(c.size / 1024))}KB)`).join(', ')}
              </span>
            )}
          </div>
          <textarea
            value={clipManifest}
            onChange={(e) => setClipManifest(e.target.value)}
            rows={4}
            placeholder={'クリップマニフェスト (任意・JSON): [{"clip_id": "intro", "filename": "clip_a.mp4"}]'}
            aria-label="クリップマニフェスト"
            className="w-full bg-[#0B0F19] border border-[#334155] rounded-[8px] px-3 py-2 text-[12px] font-mono focus:outline-none focus:border-[#10B981]"
          />
          <div className="flex items-center gap-3 flex-wrap">
            <button
              type="button"
              onClick={handleClipIngest}
              disabled={clipBusy || !activeProjectName || !clips || clips.inbox.length === 0}
              className="h-[34px] px-4 rounded-[8px] bg-gradient-to-br from-[#10B981] to-[#059669] text-white text-[12.5px] font-extrabold disabled:opacity-50"
            >
              {clipBusy ? '⏳ 取込中 (正規化しています)...' : '🎞 クリップ取込 (Ingest Clips)'}
            </button>
            {clipMsg && <span className="text-[11.5px] text-[#34D399] font-semibold">{clipMsg}</span>}
            {clipError && <span className="text-[11.5px] text-[#FECDD3] font-semibold">⚠ {clipError}</span>}
          </div>
          {clipResult?.status === 'done' && (
            <div className="space-y-1.5">
              {clipResult.error && (
                <p className="text-[11.5px] font-semibold text-[#FECDD3]">⚠ {clipResult.error}</p>
              )}
              {clipResult.result && (
                <>
                  <p className={`text-[11.5px] font-extrabold ${clipResult.ok ? 'text-[#34D399]' : 'text-[#FDE68A]'}`}>
                    {clipResult.ok
                      ? `✓ ${clipResult.result.clips.length}件のクリップを取り込みました`
                      : clipResult.result.matching_aborted
                        ? '✗ マニフェスト照合で中断 — 何も取り込まれていません'
                        : clipResult.result.ingest_aborted
                          ? '✗ 正規化に失敗し中断 — 何も取り込まれていません'
                          : '⚠ 取込結果を確認してください'}
                  </p>
                  {clipResult.result.rejected.map((r, i) => (
                    <p key={i} className="text-[11.5px] text-[#FECDD3]">
                      ✗ {r.source}: {r.reason}
                    </p>
                  ))}
                </>
              )}
            </div>
          )}
          {clips && clips.clips.length > 0 && (
            <ul className="space-y-1">
              {clips.clips.map((c) => (
                <li key={c.id} className="text-[11.5px] font-mono text-[#CBD5E1] bg-[#0B0F19] border border-[#1E293B] rounded-[6px] px-2.5 py-1.5 flex justify-between gap-2">
                  <span className="truncate">{c.id} ← {c.source}</span>
                  <span className="text-[#64748B] shrink-0">{c.duration_sec.toFixed(1)}s · {c.width}x{c.height}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* Step 1.5: Pre-Script Packaging Hook */}
        <section className="space-y-2 rounded-[10px] bg-[#0B0F19] border border-[#1E293B] p-3">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div>
              <h3 className="text-[12.5px] font-extrabold text-[#38BDF8]">
                Step 1.5 — パッケージ仮決め (台本前にフックをロック)
              </h3>
              <p className="text-[10.5px] text-[#94A3B8]">
                ライバル分析パターンからタイトル+サムネ3案を先に作り、冒頭15秒の回収ゴールを固定します。
              </p>
            </div>
            <button
              type="button"
              onClick={handlePreScriptPackaging}
              disabled={isPrePackaging || !activeProjectName}
              className="h-[30px] px-3 rounded-[6px] bg-[#1E293B] hover:bg-[#334155] text-[#38BDF8] text-[11.5px] font-bold disabled:opacity-50 whitespace-nowrap"
            >
              {isPrePackaging ? '⏳ 生成中...' : '🎨 フック3案を生成'}
            </button>
          </div>
          {prePkgMsg && <div className="text-[11px] text-[#34D399] font-semibold">{prePkgMsg}</div>}
          {prePackaging && (
            <div className="grid grid-cols-1 gap-1.5 pt-1">
              {prePackaging.pairs.map((p) => {
                const locked = prePackaging.selected_axis === p.axis;
                return (
                  <div
                    key={p.axis}
                    className={`px-2.5 py-2 rounded-[6px] border flex items-center justify-between gap-2 text-[11px] ${
                      locked ? 'bg-emerald-950/30 border-emerald-600/60' : 'bg-[#111827] border-[#1E293B]'
                    }`}
                  >
                    <div className="min-w-0">
                      <span className="font-extrabold text-[#38BDF8] mr-1.5">[{p.axis}]</span>
                      <span className="font-bold text-[#F8FAFC]">{p.title}</span>
                      <span className="ml-2 text-[#94A3B8] font-mono">({p.total}/100)</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleLockPrePackaging(p.axis)}
                      disabled={locked}
                      className={`px-2.5 py-1 rounded text-[10.5px] font-bold shrink-0 ${
                        locked ? 'bg-emerald-700 text-white' : 'bg-[#0284C7] hover:bg-[#0369A1] text-white'
                      }`}
                    >
                      {locked ? '✓ ロック済' : '仮ロック'}
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* Step 2: Evidence & dialogue ingest */}
        <section className="space-y-2.5 pb-2">
          <h3 className="text-[13px] font-extrabold text-[#34D399]">Step 2 — 証拠 &amp; 台本の取込</h3>
          <label className="block text-[11.5px] font-bold text-[#94A3B8]">
            NotebookLM Forensic Evidence Matrix (evidence.md)
          </label>
          <textarea
            value={evidenceMd}
            onChange={(e) => setEvidenceMd(e.target.value)}
            rows={6}
            placeholder="| # | Claim | Period | Verbatim Quote | Source | Metric | ..."
            className="w-full bg-[#0B0F19] border border-[#334155] rounded-[8px] px-3 py-2 text-[12px] font-mono focus:outline-none focus:border-[#10B981]"
          />
          <label className="block text-[11.5px] font-bold text-[#94A3B8]">
            Raw Dialogue Markdown (dialogue_raw.md)
          </label>
          <textarea
            value={dialogueMd}
            onChange={(e) => setDialogueMd(e.target.value)}
            rows={6}
            placeholder={'[Zundamon]: ...\n**Metan**: ...'}
            className="w-full bg-[#0B0F19] border border-[#334155] rounded-[8px] px-3 py-2 text-[12px] font-mono focus:outline-none focus:border-[#10B981]"
          />
          <div className="flex items-center gap-3">
            <button
              onClick={handleIngest}
              disabled={isIngesting || !activeProjectName || (!evidenceMd.trim() && !dialogueMd.trim())}
              className="h-[34px] px-4 rounded-[8px] bg-gradient-to-br from-[#10B981] to-[#059669] text-white text-[12.5px] font-extrabold disabled:opacity-50"
            >
              {isIngesting ? '⏳ 取込中...' : '📥 台本 & クレーム取込 (Ingest)'}
            </button>
            {ingestMsg && <span className="text-[11.5px] text-[#34D399] font-semibold">{ingestMsg}</span>}
          </div>
        </section>
      </div>
    </div>
  );
};
