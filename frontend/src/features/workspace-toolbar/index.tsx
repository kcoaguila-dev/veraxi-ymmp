import React from 'react';

export const WorkspaceToolbar: React.FC = () => {
  const [loadingGen, setLoadingGen] = React.useState(false);
  const [loadingYMM, setLoadingYMM] = React.useState(false);
  const [loadingPrem, setLoadingPrem] = React.useState(false);

  const handleAction = (setter: React.Dispatch<React.SetStateAction<boolean>>) => {
    setter(true);
    setTimeout(() => setter(false), 1000);
  };

  return (
    <div className="flex items-center justify-between p-4 bg-panel border-b border-structural text-[#F8FAFC]">
      <div className="flex items-center gap-4">
        <div className="font-bold text-lg text-white">veraxi <span className="font-light">Studio</span></div>
        <select className="bg-layer border border-structural rounded px-3 py-1">
          <option>my_video</option>
        </select>
        <span className="px-2 py-1 bg-zundamon text-canvas text-xs font-bold rounded">
          VOICEVOX OK
        </span>
      </div>
      <div className="flex items-center gap-2">
        <button onClick={() => handleAction(setLoadingGen)} disabled={loadingGen} className="bg-emerald-600 hover:bg-emerald-500 text-white font-bold px-3 py-1 rounded text-sm disabled:opacity-50">
          ⚡ 動画を生成 (プレビュー)
        </button>
        <button onClick={() => handleAction(setLoadingYMM)} disabled={loadingYMM} className="bg-layer hover:bg-hover px-3 py-1 rounded text-sm disabled:opacity-50">
          {loadingYMM ? "⏳" : "🎬"} YMM4で開く
        </button>
        <button onClick={() => handleAction(setLoadingPrem)} disabled={loadingPrem} className="bg-layer hover:bg-hover px-3 py-1 rounded text-sm disabled:opacity-50">
          {loadingPrem ? "⏳" : "📄"} Premiere書き出し
        </button>
      </div>
    </div>
  );
};
