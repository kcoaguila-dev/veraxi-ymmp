import React from 'react';

export const YoutubePublish: React.FC = () => {
  return (
    <div className="bg-panel border border-structural rounded p-4 flex flex-col gap-4 text-[#F8FAFC]">
      <div className="aspect-video bg-layer rounded flex items-center justify-center text-xs overflow-hidden border border-hover">
        <img src="thumbnail.png" alt="Thumbnail Preview" className="w-full h-full object-cover" onError={(e: any) => e.target.style.display = 'none'} />
      </div>
      <input
        type="text"
        className="w-full bg-layer border border-hover rounded px-2 py-1 text-sm font-bold"
        defaultValue="Untitled Project"
      />
      <div className="flex flex-col gap-1 text-xs">
        <label className="flex items-center gap-2">
          <input type="checkbox" defaultChecked />
          Title is engaging
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" defaultChecked />
          Thumbnail looks good at small sizes
        </label>
      </div>
      <select className="w-full bg-layer border border-hover rounded px-2 py-1 text-sm">
        <option>🔒 非公開 (Private)</option>
      </select>
      <button className="w-full bg-shikoku hover:bg-[#E11D48] text-white font-bold py-2 rounded shadow text-sm">
        🚀 YouTubeへ投稿
      </button>
    </div>
  );
};
