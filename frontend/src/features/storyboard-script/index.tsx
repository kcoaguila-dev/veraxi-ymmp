import React from 'react';

export const StoryboardScript: React.FC = () => {
  return (
    <div className="flex flex-col h-full bg-canvas text-[#F8FAFC]">
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <div className="bg-panel border border-structural rounded p-4 flex gap-4">
          <div className="w-32 h-24 bg-layer rounded flex items-center justify-center shrink-0 text-xs">
            Slide Thumbnail
          </div>
          <div className="flex-1 flex flex-col gap-2">
            <div className="flex justify-between items-center">
              <span className="text-zundamon font-bold text-sm">ずんだもん</span>
              <span className="bg-shikoku text-canvas px-2 py-0.5 rounded text-xs font-bold">
                &gt; 35 chars split
              </span>
            </div>
            <textarea
              className="w-full bg-layer border border-hover rounded p-2 text-sm text-[#F8FAFC]"
              rows={2}
              defaultValue="こんにちはなのだ！今日はClean Architectureについて解説するのだ！"
            />
            <div className="flex justify-end">
              <button className="text-xs bg-hover hover:bg-structural px-2 py-1 rounded">
                ▶ Audition Voice
              </button>
            </div>
          </div>
        </div>
      </div>
      <div className="p-2 bg-panel border-t border-structural flex gap-2">
        <select className="bg-layer border border-hover rounded px-2 text-sm">
          <option>ずんだもん ▾</option>
        </select>
        <input
          type="text"
          className="flex-1 bg-layer border border-hover rounded px-2 text-sm text-[#F8FAFC]"
          placeholder="Press Enter to add..."
        />
      </div>
    </div>
  );
};
