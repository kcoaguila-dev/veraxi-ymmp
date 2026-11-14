import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useStudioStore } from '../../shared/store';
import { api } from '../../shared/api';
import type { SourcesResult } from '../../shared/types';

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
  const { activeProjectName, loadProjects, setActiveProject, refreshMedia } = useStudioStore();
  const [topic, setTopic] = useState('');
  const [archetype, setArchetype] = useState('post_mortem');
  const [projectName, setProjectName] = useState('');
  const [dossier, setDossier] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
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

  // Evidence/dialogue drafts are per-project: stash them under the previous
  // project's name on switch and restore the newly selected project's drafts,
  // so text pasted for project A never leaks into project B.
  const draftsRef = useRef<Record<string, { evidence: string; dialogue: string }>>({});
  const prevProjectRef = useRef<string | null>(null);
  useEffect(() => {
    const prev = prevProjectRef.current;
    if (prev !== activeProjectName) {
      if (prev) {
        draftsRef.current[prev] = { evidence: evidenceMd, dialogue: dialogueMd };
      }
      if (activeProjectName) {
        const stash = draftsRef.current[activeProjectName];
        setEvidenceMd(stash?.evidence ?? '');
        setDialogueMd(stash?.dialogue ?? '');
      } else {
        setEvidenceMd('');
        setDialogueMd('');
      }
      prevProjectRef.current = activeProjectName;
    }
  }, [activeProjectName, evidenceMd, dialogueMd]);

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
