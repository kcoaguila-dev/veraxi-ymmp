
import React from 'react';

export const YoutubePublish: React.FC = () => {
  return (
    <div className="bg-panel border border-structural rounded flex flex-col text-[#F8FAFC]">
      <div className="p-4 border-b border-structural">
        <h2 className="font-bold text-lg">3. YouTubeサムネイル・投稿</h2>
      </div>
      <div className="p-4 flex gap-4">
        <div className="flex-1 aspect-video bg-layer rounded flex flex-col items-center justify-center text-xs overflow-hidden border border-hover relative">
          <img src="thumbnail.png" alt="Thumbnail Preview" className="w-full h-full object-cover" onError={(e: any) => e.target.style.display = 'none'} />
          <div className="absolute bottom-1 right-1 bg-black/80 text-white text-[10px] px-1 rounded font-mono">1:30</div>
        </div>
        <div className="flex-1 flex flex-col gap-3">
          <input
            type="text"
            className="w-full bg-layer border border-hover rounded px-2 py-1 text-sm font-bold"
            defaultValue="Untitled Project"
          />
          <div className="bg-[#0B0F19] border border-structural rounded p-2 text-xs flex items-start gap-2">
            <span className="text-zundamon">✓</span>
            <span className="text-gray-300">3分割レイアウト・右下タイムスタンプ回避済</span>
          </div>
          <div className="flex-1"></div>
          <select className="w-full bg-layer border border-hover rounded px-2 py-2 text-sm">
            <option>🔒 非公開 (下書き) ▾</option>
          </select>
          <button className="w-full bg-shikoku hover:bg-[#E11D48] text-white font-bold py-2 rounded shadow text-sm">
            🚀 YouTubeへ投稿
          </button>
        </div>
      </div>
    </div>
  );
};
