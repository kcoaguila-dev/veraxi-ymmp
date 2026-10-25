import React, { useState } from 'react';
import { useStudioStore } from '../../shared/store';
import { api } from '../../shared/api';

export const WorkspaceToolbar: React.FC = () => {
  const { projects, activeProjectName, setActiveProject, createProject, voicevoxHealth, pipelineStatus, runPipeline, isDirty } = useStudioStore();
  const [loadingYMM, setLoadingYMM] = useState(false);
  const [ymmSuccess, setYmmSuccess] = useState(false);
  const [loadingPrem, setLoadingPrem] = useState(false);
  const [useTts, setUseTts] = useState(true);

  const handleYMM4 = async () => {
    if (!activeProjectName) return;
    setLoadingYMM(true);
    setYmmSuccess(false);
    try {
      await api.launchYMM4(activeProjectName);
      setYmmSuccess(true);
      setTimeout(() => setYmmSuccess(false), 5000);
    } catch (e: any) {
      console.error(e);
      const detail = e?.data?.error || e?.message || 'Ensure YMM4 is configured properly.';
      alert(`Failed to launch YMM4: ${detail}`);
    }
    setLoadingYMM(false);
  };

  const handlePremiere = async () => {
    if (!activeProjectName) return;
    setLoadingPrem(true);
    try {
      const url = `/api/projects/${encodeURIComponent(activeProjectName)}/media/premiere/${encodeURIComponent(activeProjectName)}.xml`;
      const a = document.createElement('a');
      a.href = url;
      a.download = `${activeProjectName}.xml`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } catch (e) {
      console.error(e);
      alert('Failed to download Premiere XML.');
    }
    setLoadingPrem(false);
  };

  const handleCreateProject = () => {
    const name = prompt("新規プロジェクト名を入力してください (Enter new project name):");
    if (name) {
      createProject(name);
    }
  };

  const isRunning = pipelineStatus.status === 'running';
  const vvOnline = !!voicevoxHealth?.available;

  return (
    <header className="h-[60px] px-6 bg-[#111827] border-b border-[#1E293B] flex items-center justify-between text-[#F8FAFC] shrink-0">
      {/* Left: Brand + Project Selector + Voicevox Pill */}
      <div className="flex items-center gap-3.5">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-[7px] bg-gradient-to-br from-[#10B981] to-[#059669] flex items-center justify-center shadow-sm shrink-0">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M6 7L12 18L18 7" stroke="#FFFFFF" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <span className="text-[16px] font-extrabold tracking-tight text-[#F8FAFC]">
            veraxi Studio
          </span>
        </div>

        <div className="h-5 w-[1px] bg-[#334155] mx-0.5" />

        <div className="flex items-center gap-2">
          <select
            aria-label="プロジェクト選択"
            className="bg-[#1E293B]/90 hover:bg-[#1E293B] border border-[#334155] rounded-[7px] px-3 py-1 text-[13px] font-semibold text-[#E2E8F0] focus:outline-none focus:border-[#10B981] transition-colors"
            value={activeProjectName || ''}
            onChange={(e) => {
              const next = e.target.value;
              if (isDirty) {
                const confirmed = window.confirm(
                  '未保存の台本編集があります。プロジェクトを切り替えると変更が破棄されますがよろしいですか？'
                );
                if (!confirmed) return;
              }
              setActiveProject(next);
            }}
          >
            {activeProjectName && !projects.some(p => p.name === activeProjectName) && (
              <option value={activeProjectName}>{activeProjectName}</option>
            )}
            {projects.map(p => (
              <option key={p.name} value={p.name}>{p.name}</option>
            ))}
          </select>

          <button
            onClick={handleCreateProject}
            className="bg-[#1E293B] hover:bg-[#334151] border border-[#334155] text-[#E2E8F0] px-2.5 py-1 rounded-[7px] text-[11.5px] font-bold transition-colors"
            title="新規プロジェクトを作成"
          >
            ＋ 新規
          </button>
        </div>

        {vvOnline ? (
          <button
            type="button"
            onClick={() => setUseTts(!useTts)}
            title="クリックしてTTSモードを切り替え"
            className={`h-[24px] px-3 rounded-full flex items-center gap-1.5 text-[10.5px] font-bold tracking-wide transition-colors ${
              useTts
                ? 'bg-[#064E3B] text-[#A7F3D0] border border-[#10B981]/30'
                : 'bg-[#1E293B] text-[#94A3B8] border border-[#475569]'
            }`}
          >
            <span className={`w-[7px] h-[7px] rounded-full ${useTts ? 'bg-[#34D399]' : 'bg-[#94A3B8]'}`} />
            {useTts ? 'VOICEVOX OK' : 'VOICEVOX MUTE (No-TTS)'}
          </button>
        ) : (
          <button
            type="button"
            onClick={() => setUseTts(!useTts)}
            title="Click to toggle No-TTS fallback mode"
            className={`h-[24px] px-3 rounded-full flex items-center gap-1.5 text-[10.5px] font-bold tracking-wide transition-colors ${
              useTts
                ? 'bg-[#4C0519] text-[#FECDD3] border border-[#F43F5E]/40'
                : 'bg-[#78350F]/80 text-[#FDE68A] border border-[#F59E0B]/40'
            }`}
          >
            <span className={`w-[7px] h-[7px] rounded-full ${useTts ? 'bg-[#F43F5E]' : 'bg-[#F59E0B]'}`} />
            {useTts ? 'VOICEVOX OFFLINE (No-TTS切替)' : 'NO-TTS モード有効'}
          </button>
        )}
      </div>

      {/* Right: Step 1 (Local Generate) + Optional Editor Handoffs */}
      <div className="flex items-center gap-2.5">
        <button
          onClick={() => runPipeline(useTts && vvOnline)}
          disabled={isRunning}
          className="h-[36px] min-w-[196px] px-4 rounded-[8px] bg-gradient-to-br from-[#10B981] to-[#059669] hover:from-[#34D399] hover:to-[#10B981] text-white text-[13px] font-extrabold shadow-sm flex items-center justify-center gap-1.5 disabled:opacity-50 transition-all"
        >
          {isRunning ? (
            <span className="flex items-center justify-between w-full gap-3">
              <span className="truncate">⚡ {pipelineStatus.stage}</span>
              <span className="font-mono tabular-nums">{Math.round(pipelineStatus.progress || 0)}%</span>
            </span>
          ) : (
            <span>⚡ 動画を生成 (プレビュー)</span>
          )}
        </button>

        <div className="h-6 w-[1px] bg-[#334155] mx-0.5" />

        <button
          onClick={handleYMM4}
          disabled={loadingYMM}
          className={`h-[36px] px-3.5 rounded-[8px] border text-[12.5px] font-bold flex items-center gap-1.5 disabled:opacity-50 transition-colors ${
            ymmSuccess
              ? 'bg-[#064E3B] border-[#10B981] text-[#A7F3D0]'
              : 'bg-[#1E293B] hover:bg-[#334155] border-[#475569] text-[#E2E8F0]'
          }`}
          title="YMM4でプロジェクトを開く"
        >
          <span>{loadingYMM ? '⏳' : ymmSuccess ? '✅' : '🎬'}</span>
          <span>{loadingYMM ? '起動中...' : ymmSuccess ? 'YMM4起動完了' : 'YMM4で開く'}</span>
        </button>

        <button
          onClick={handlePremiere}
          disabled={loadingPrem}
          className="h-[36px] px-3.5 rounded-[8px] bg-[#1E293B] hover:bg-[#334155] border border-[#475569] text-[#E2E8F0] text-[12.5px] font-bold flex items-center gap-1.5 disabled:opacity-50 transition-colors"
        >
          <span>{loadingPrem ? '⏳' : '📄'}</span>
          <span>Premiere書き出し</span>
        </button>
      </div>
    </header>
  );
};
