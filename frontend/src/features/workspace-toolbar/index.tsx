import React from 'react';

export const WorkspaceToolbar: React.FC = () => {
  return (
    <div className="flex items-center justify-between p-4 bg-panel border-b border-structural text-[#F8FAFC]">
      <div className="flex items-center gap-4">
        <select className="bg-layer border border-structural rounded px-3 py-1">
          <option>my_video</option>
        </select>
        <span className="px-2 py-1 bg-zundamon text-canvas text-xs font-bold rounded">
          VOICEVOX OK
        </span>
      </div>
      <div className="flex items-center gap-2">
        <button className="bg-layer hover:bg-hover px-3 py-1 rounded text-sm">
          ⚡ 動画を生成 (プレビュー)
        </button>
        <button className="bg-layer hover:bg-hover px-3 py-1 rounded text-sm">
          🎬 YMM4で開く
        </button>
        <button className="bg-layer hover:bg-hover px-3 py-1 rounded text-sm">
          📄 Premiere書き出し
        </button>
      </div>
    </div>
  );
};
