import React from 'react';

export const StoryboardScript: React.FC = () => {
  return (

    <div className="flex flex-col h-full bg-canvas text-[#F8FAFC]">
      <div className="flex items-center justify-between p-4 border-b border-structural bg-panel">
        <h2 className="font-bold text-lg">1. 台本・スライド編集</h2>
        <div className="flex gap-2">
          <button className="bg-layer hover:bg-hover px-3 py-1 rounded text-sm flex items-center gap-1" onClick={(e) => { const el = e.currentTarget; el.textContent = '✓ Copied!'; setTimeout(() => el.textContent = '📋 AI用プロンプトをコピー', 2000); }}>📋 AI用プロンプトをコピー</button>
          <button className="bg-layer hover:bg-hover px-3 py-1 rounded text-sm flex items-center gap-1">📥 JSON貼り付け</button>
        </div>
      </div>


      <div className="flex-1 overflow-y-auto p-4 space-y-6">

        <div className="space-y-4">
          <h3 className="font-bold text-structural mb-2">シーン 1</h3>
          <div className="bg-panel border border-structural rounded p-4 flex gap-4">
            <div className="w-32 h-24 bg-layer rounded flex flex-col items-center justify-center shrink-0 text-xs gap-2">
              <span>🖼 スライド変更</span>
            </div>
            <div className="flex-1 flex flex-col gap-2">
              <div className="flex justify-between items-center">
                <div className="flex items-center gap-2">
                  <span className="text-zundamon font-bold text-sm flex items-center gap-1"><div className="w-2 h-2 rounded-full bg-zundamon"></div>ずんだもん</span>
                  <select className="bg-layer border border-structural rounded text-xs px-1 py-0.5 text-gray-300">
                    <option>😊 笑顔 ▾</option>
                  </select>
                </div>
                <span className="bg-shikoku text-canvas px-2 py-0.5 rounded text-xs font-bold">
                  ✂ 38文字 — 2行に分割を推奨
                </span>
              </div>
              <textarea
                className="w-full bg-layer border border-hover rounded p-2 text-sm text-[#F8FAFC]"
                rows={2}
                defaultValue="こんにちはなのだ！今日はClean Architectureについて解説するのだ！"
              />
              <div className="flex justify-end">
                <button className="text-xs bg-hover hover:bg-structural px-2 py-1 rounded flex items-center gap-1">
                  ▶ 試聴
                </button>
              </div>
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <h3 className="font-bold text-structural mb-2">シーン 2</h3>
          <div className="bg-panel border border-structural rounded p-4 flex gap-4">
            <div className="w-32 h-24 shrink-0"></div>
            <div className="flex-1 flex flex-col gap-2">
              <div className="flex justify-between items-center">
                <div className="flex items-center gap-2">
                  <span className="text-shikoku font-bold text-sm flex items-center gap-1"><div className="w-2 h-2 rounded-full bg-shikoku"></div>四国めたん</span>
                  <select className="bg-layer border border-structural rounded text-xs px-1 py-0.5 text-gray-300">
                    <option>😐 通常 ▾</option>
                  </select>
                </div>
                <span className="text-gray-400 text-xs">
                  28文字 ✓
                </span>
              </div>
              <textarea
                className="w-full bg-layer border border-hover rounded p-2 text-sm text-[#F8FAFC]"
                rows={2}
                defaultValue="よろしくお願いいたしますわ。基礎からしっかり学びましょう。"
              />
              <div className="flex justify-end">
                <button className="text-xs bg-hover hover:bg-structural px-2 py-1 rounded flex items-center gap-1">
                  ▶ 試聴
                </button>
              </div>
            </div>
          </div>
        </div>

      </div>

      <div className="p-2 bg-panel border-t border-structural flex gap-2 items-center">
        <select className="bg-layer border border-hover rounded px-2 py-1 text-sm h-full">
          <option>ずんだもん ▾</option>
        </select>
        <input
          type="text"
          className="flex-1 bg-layer border border-hover rounded px-3 py-1 text-sm text-[#F8FAFC] h-full"
          placeholder="Press Enter to add..."
          onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.value = ''; }}
        />
        <button className="bg-layer hover:bg-hover px-4 py-1 rounded text-sm font-bold whitespace-nowrap h-full">
          ＋ 追加
        </button>
      </div>
    </div>
  );
};
