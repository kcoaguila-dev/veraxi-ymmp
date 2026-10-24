import React, { useState } from 'react';
import { useStudioStore } from '../../shared/store';
import { api } from '../../shared/api';
import { Emotion, Motion } from '../../shared/types';

const EMOTIONS = [
  { val: 'happy', label: '😊 happy (笑顔)' },
  { val: 'normal', label: '😐 normal (通常)' },
  { val: 'neutral', label: '😐 neutral (中立)' },
  { val: 'angry', label: '😠 angry (怒り)' },
  { val: 'sad', label: '😢 sad (悲しみ)' },
  { val: 'surprised', label: '😲 surprised (驚き)' },
  { val: 'confused', label: '🤔 confused (困惑)' },
  { val: 'smug', label: '😏 smug (ドヤ顔)' }
];
const MOTIONS = ['none', 'jump', 'shake', 'nod'];
const CHARACTERS = ['ずんだもん', '四国めたん', '春日部つむぎ'];

export const StoryboardScript: React.FC = () => {
  const { projectData, activeProjectName, updateScriptEntry, addScriptEntry, deleteScriptEntry, moveScriptEntry, splitScriptCuts, setScript, saveScript, isDirty, mediaCacheBust } = useStudioStore();
  const [newChar, setNewChar] = useState('ずんだもん');
  const [newText, setNewText] = useState('');
  const [showPasteModal, setShowPasteModal] = useState(false);
  const [pasteJson, setPasteJson] = useState('');
  const [repromptBlock, setRepromptBlock] = useState<string | null>(null);

  const getCharColor = (char: string) => {
    if (char.includes('ずんだもん')) return 'text-zundamon bg-zundamon';
    if (char.includes('四国めたん')) return 'text-shikoku bg-shikoku';
    if (char.includes('つむぎ')) return 'text-tsumugi bg-tsumugi';
    return 'text-white bg-white';
  };

  const handleAudition = async (text: string, character: string, btn: HTMLButtonElement) => {
    btn.textContent = '⏳ Loading...';
    try {
      const blob = await api.auditionVoice(text, character);
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      btn.textContent = '🔊 演奏中...';
      audio.onended = () => btn.textContent = '▶ 試聴';
      await audio.play();
    } catch (e) {
      console.error(e);
      alert('Audition failed');
      btn.textContent = '▶ 試聴';
    }
  };

  const handleCopyPrompt = async (e: React.MouseEvent<HTMLButtonElement>) => {
    const el = e.currentTarget;
    try {
      const { prompt_markdown } = await api.getAIPrompt();
      await navigator.clipboard.writeText(prompt_markdown);
      el.textContent = '✓ Copied!';
      setTimeout(() => el.textContent = '📋 AI用プロンプトをコピー', 2000);
    } catch (err) {
      console.error(err);
      alert('Failed to copy prompt');
    }
  };

  const handlePasteSubmit = async () => {
    if (!activeProjectName) return;
    try {
      const parsed = JSON.parse(pasteJson);
      const res = await api.saveProjectScript(activeProjectName, parsed);
      if (res.success) {
        setScript(parsed);
        setShowPasteModal(false);
        setPasteJson('');
        setRepromptBlock(null);
      } else {
        setRepromptBlock(res.reprompt_block || 'Validation failed without a reprompt block.');
      }
    } catch (e: any) {
        if (e.data && e.data.reprompt_block) {
            setRepromptBlock(e.data.reprompt_block);
        } else {
            setRepromptBlock(`Failed to parse JSON: ${e.message}`);
        }
    }
  };

  const handleAdd = () => {
    if (!newText.trim()) return;
    addScriptEntry({ character: newChar, text: newText.trim() });
    setNewText('');
  };

  if (!projectData) return <div className="p-4">Loading project...</div>;

  return (
    <div className="flex flex-col h-full bg-canvas text-[#F8FAFC]">
      <div className="flex items-center justify-between p-4 border-b border-structural bg-panel">
        <div className="flex items-center gap-4">
            <h2 className="font-bold text-lg">1. 台本・スライド編集</h2>
            {isDirty && (
                <button onClick={saveScript} className="bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold px-3 py-1 rounded">
                💾 保存
                </button>
            )}
        </div>
        <div className="flex gap-2">
          <button className="bg-layer hover:bg-hover px-3 py-1 rounded text-sm flex items-center gap-1" onClick={handleCopyPrompt}>
            📋 AI用プロンプトをコピー
          </button>
          <button className="bg-layer hover:bg-hover px-3 py-1 rounded text-sm flex items-center gap-1" onClick={() => setShowPasteModal(true)}>
            📥 JSON貼り付け
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-6 pb-20">
        {projectData.script.map((entry, idx) => (
          <div key={idx} className="space-y-2">
            <div className="bg-panel border border-structural rounded p-4 flex gap-4">
              <div className="w-32 h-24 bg-layer rounded flex flex-col items-center justify-center shrink-0 text-xs overflow-hidden">
                {entry.image ? (
                  <img src={`/api/projects/${activeProjectName}/media/${entry.image}?t=${mediaCacheBust}`} alt="broll" className="w-full h-full object-cover" />
                ) : (
                  <span>No B-Roll</span>
                )}
                <div className="flex gap-1 mt-1">
                  <button onClick={() => updateScriptEntry(idx, { ...entry, image: prompt("Enter image filename (e.g. image1.png):") })} className="bg-layer px-1 py-0.5 rounded text-[10px]">Set</button>
                  {entry.image && <button onClick={() => updateScriptEntry(idx, { ...entry, image: null })} className="bg-layer px-1 py-0.5 rounded text-[10px] text-rose-400">Clear</button>}
                </div>
              </div>
              <div className="flex-1 flex flex-col gap-2">
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-2">
                    <span className={`font-bold text-sm flex items-center gap-1 ${getCharColor(entry.character).split(' ')[0]}`}>
                      <div className={`w-2 h-2 rounded-full ${getCharColor(entry.character).split(' ')[1]}`}></div>
                      {entry.character}
                    </span>
                    <select
                      className="bg-layer border border-structural rounded text-xs px-1 py-0.5 text-gray-300"
                      value={entry.emotion || 'normal'}
                      onChange={(e) => updateScriptEntry(idx, { ...entry, emotion: e.target.value as Emotion })}
                    >
                      {EMOTIONS.map(e => <option key={e.val} value={e.val}>{e.label}</option>)}
                    </select>
                    <select
                      className="bg-layer border border-structural rounded text-xs px-1 py-0.5 text-gray-300"
                      value={entry.motion || 'none'}
                      onChange={(e) => updateScriptEntry(idx, { ...entry, motion: e.target.value as Motion })}
                    >
                      {MOTIONS.map(m => <option key={m} value={m}>{m}</option>)}
                    </select>
                  </div>
                  <div className="flex items-center gap-2">
                    {entry.text.length <= 35 ? (
                      <span className="text-gray-400 text-xs">{entry.text.length}文字 ✓</span>
                    ) : entry.text.length <= 40 ? (
                      <span className="bg-amber-600/20 text-amber-500 px-2 py-0.5 rounded text-xs font-bold flex items-center gap-1">
                        ✂ {entry.text.length}文字 — 2行に分割を推奨
                        <button onClick={splitScriptCuts} className="bg-amber-500 text-canvas px-1 rounded ml-1">分割</button>
                      </span>
                    ) : (
                      <span className="bg-rose-600/20 text-rose-500 px-2 py-0.5 rounded text-xs font-bold flex items-center gap-1">
                        ⚠ {entry.text.length}文字 (上限40文字超過)
                        <button onClick={splitScriptCuts} className="bg-rose-500 text-canvas px-1 rounded ml-1">自動分割</button>
                      </span>
                    )}
                  </div>
                </div>
                <textarea
                  className="w-full bg-layer border border-hover rounded p-2 text-sm text-[#F8FAFC]"
                  rows={2}
                  value={entry.text}
                  onChange={(e) => updateScriptEntry(idx, { ...entry, text: e.target.value })}
                />
                {entry.text.startsWith('「ええ、') && (
                    <div className="text-xs text-rose-400">⚠ Hygiene Rule: Do not begin lines with bare 「ええ、」</div>
                )}
                <div className="flex justify-between">
                  <div className="flex gap-1">
                    <button onClick={() => moveScriptEntry(idx, 'up')} className="bg-layer px-2 py-1 rounded text-xs">↑</button>
                    <button onClick={() => moveScriptEntry(idx, 'down')} className="bg-layer px-2 py-1 rounded text-xs">↓</button>
                    <button onClick={() => addScriptEntry({...entry})} className="bg-layer px-2 py-1 rounded text-xs">Duplicate</button>
                    <button onClick={() => deleteScriptEntry(idx)} className="bg-layer hover:bg-rose-900 px-2 py-1 rounded text-xs text-rose-500">🗑</button>
                  </div>
                  <button
                    className="text-xs bg-hover hover:bg-structural px-2 py-1 rounded flex items-center gap-1"
                    onClick={(e) => handleAudition(entry.text, entry.character, e.currentTarget)}
                  >
                    ▶ 試聴
                  </button>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="p-2 bg-panel border-t border-structural flex gap-2 items-center">
        <select
          className="bg-layer border border-hover rounded px-2 py-1 text-sm h-full"
          value={newChar}
          onChange={(e) => setNewChar(e.target.value)}
        >
          {CHARACTERS.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <input
          type="text"
          className="flex-1 bg-layer border border-hover rounded px-3 py-1 text-sm text-[#F8FAFC] h-full"
          placeholder="Press Enter to add..."
          value={newText}
          onChange={(e) => setNewText(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') handleAdd(); }}
        />
        <button onClick={handleAdd} className="bg-layer hover:bg-hover px-4 py-1 rounded text-sm font-bold whitespace-nowrap h-full">
          ＋ 追加
        </button>
      </div>

      {showPasteModal && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
          <div className="bg-panel border border-structural rounded p-6 w-full max-w-2xl max-h-screen overflow-y-auto">
            <h3 className="font-bold text-lg mb-4">JSON 貼り付け</h3>
            <textarea
              className="w-full h-48 bg-layer border border-hover rounded p-2 text-sm text-[#F8FAFC] font-mono mb-4"
              value={pasteJson}
              onChange={(e) => setPasteJson(e.target.value)}
              placeholder="[ { ... } ]"
            />
            {repromptBlock && (
              <div className="mb-4">
                <div className="bg-rose-900/20 border border-rose-900 p-2 rounded text-xs font-mono text-rose-300 whitespace-pre-wrap max-h-40 overflow-y-auto">
                  {repromptBlock}
                </div>
                <button
                  onClick={() => navigator.clipboard.writeText(repromptBlock)}
                  className="mt-2 bg-layer hover:bg-hover px-3 py-1 rounded text-xs flex items-center gap-1"
                >
                  📋 Re-Promptをコピー
                </button>
              </div>
            )}
            <div className="flex justify-end gap-2">
              <button onClick={() => setShowPasteModal(false)} className="bg-layer hover:bg-hover px-4 py-2 rounded text-sm">キャンセル</button>
              <button onClick={handlePasteSubmit} className="bg-emerald-600 hover:bg-emerald-500 text-white font-bold px-4 py-2 rounded text-sm">適用</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
