import React, { useState } from 'react';
import { useStudioStore } from '../../shared/store';
import { api } from '../../shared/api';

export const WorkspaceToolbar: React.FC = () => {
  const { projects, activeProjectName, setActiveProject, createProject, voicevoxHealth, pipelineStatus, runPipeline } = useStudioStore();
  const [loadingYMM, setLoadingYMM] = useState(false);
  const [loadingPrem, setLoadingPrem] = useState(false);
  const [useTts, setUseTts] = useState(true);

  const handleYMM4 = async () => {
    if (!activeProjectName) return;
    setLoadingYMM(true);
    try {
      await api.launchYMM4(activeProjectName);
    } catch (e) {
      console.error(e);
      alert('Failed to launch YMM4. Ensure YMM4 is configured properly.');
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
    const name = prompt("Enter new project name:");
    if (name) {
      createProject(name);
    }
  };

  const isRunning = pipelineStatus.status === 'running';

  return (
    <div className="flex items-center justify-between p-4 bg-panel border-b border-structural text-[#F8FAFC]">
      <div className="flex items-center gap-4">
        <div className="font-bold text-lg text-white">veraxi <span className="font-light">Studio</span></div>
        <select
          className="bg-layer border border-structural rounded px-3 py-1"
          value={activeProjectName || ''}
          onChange={(e) => setActiveProject(e.target.value)}
        >
          {projects.map(p => <option key={p.name} value={p.name}>{p.name}</option>)}
        </select>
        <button onClick={handleCreateProject} className="bg-layer hover:bg-hover px-2 py-1 rounded text-xs font-bold">
          + 新規
        </button>
        {voicevoxHealth?.available ? (
            <span className="px-2 py-1 bg-zundamon text-canvas text-xs font-bold rounded cursor-pointer" onClick={() => setUseTts(true)}>
            VOICEVOX OK
            </span>
        ) : (
            <span
                className={`px-2 py-1 ${useTts ? 'bg-shikoku' : 'bg-tsumugi'} text-canvas text-xs font-bold rounded cursor-pointer`}
                onClick={() => setUseTts(!useTts)}
                title="Click to toggle No-TTS mode"
            >
            VOICEVOX OFFLINE {useTts ? '(Click to disable)' : '(No-TTS Mode)'}
            </span>
        )}
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={() => runPipeline(useTts && !!voicevoxHealth?.available)}
          disabled={isRunning}
          className="bg-emerald-600 hover:bg-emerald-500 text-white font-bold px-3 py-1 rounded text-sm disabled:opacity-50 min-w-[200px]"
        >
          {isRunning ? (
            <span className="flex items-center justify-between w-full">
              <span>⚡ {pipelineStatus.stage}</span>
              <span>{Math.round(pipelineStatus.progress || 0)}%</span>
            </span>
          ) : (
            "⚡ 動画を生成 (プレビュー)"
          )}
        </button>
        <button onClick={handleYMM4} disabled={loadingYMM} className="bg-layer hover:bg-hover px-3 py-1 rounded text-sm disabled:opacity-50">
          {loadingYMM ? "⏳" : "🎬"} YMM4で開く
        </button>
        <button onClick={handlePremiere} disabled={loadingPrem} className="bg-layer hover:bg-hover px-3 py-1 rounded text-sm disabled:opacity-50">
          {loadingPrem ? "⏳" : "📄"} Premiere書き出し
        </button>
      </div>
    </div>
  );
};
