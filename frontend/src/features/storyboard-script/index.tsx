import React, { useState, useMemo } from 'react';
import { useStudioStore } from '../../shared/store';
import { api } from '../../shared/api';
import { DirectorScriptEntry, Emotion, Motion } from '../../shared/types';

const EMOTIONS: { val: Emotion; label: string }[] = [
  { val: 'happy', label: '😊 笑顔' },
  { val: 'normal', label: '😌 通常' },
  { val: 'neutral', label: '😐 中立' },
  { val: 'excited', label: '✨ 喜び' },
  { val: 'surprised', label: '😲 驚き' },
  { val: 'angry', label: '😠 怒り' },
  { val: 'sad', label: '😢 悲しみ' },
  { val: 'confused', label: '🤔 困惑' },
  { val: 'smug', label: '😏 ドヤ顔' },
];

const MOTIONS: { val: Motion; label: string }[] = [
  { val: 'none', label: '動きなし' },
  { val: 'jump', label: '⚡ ジャンプ' },
  { val: 'nod', label: 'うなずき' },
  { val: 'shake', label: '揺れ' },
];

const CHARACTERS = ['ずんだもん', '四国めたん', '春日部つむぎ'];

interface SceneGroup {
  sceneNumber: number;
  title: string;
  slideMedia: string | null;
  slideType: 'image' | 'bg' | null;
  bgmLabel: string | null;
  items: { entry: DirectorScriptEntry; index: number }[];
}

function basename(pathStr?: string | null): string {
  if (!pathStr) return '未設定';
  const parts = pathStr.replace(/\\/g, '/').split('/');
  return parts[parts.length - 1] || pathStr;
}

function inferSceneTitle(sceneNum: number, slideMedia: string | null, firstText?: string): string {
  if (sceneNum === 1 && (!slideMedia || slideMedia.includes('classroom') || slideMedia.includes('room'))) {
    const snippet = firstText ? firstText.replace(/[「」！？。、]/g, '').slice(0, 12) : '導入パート';
    return `イントロ（${snippet}）`;
  }
  if (slideMedia) {
    const base = basename(slideMedia).replace(/\.[a-zA-Z0-9]+$/, '');
    if (base.includes('profit')) return '収益構造・ビジネスモデル解説';
    if (base.includes('flywheel')) return '規模の経済と成長サイクル';
    if (base.includes('points')) return '重要ポイント・強みのまとめ';
    return `スライド解説（${base}）`;
  }
  const snippet = firstText ? firstText.replace(/[「」！？。、]/g, '').slice(0, 14) : `パート ${sceneNum}`;
  return snippet;
}

export const StoryboardScript: React.FC = () => {
  const {
    projectData,
    activeProjectName,
    updateScriptEntry,
    addScriptEntry,
    deleteScriptEntry,
    moveScriptEntry,
    splitScriptCuts,
    setScript,
    saveScript,
    isDirty,
    mediaCacheBust,
  } = useStudioStore();

  const [newChar, setNewChar] = useState('ずんだもん');
  const [newText, setNewText] = useState('');
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [playingIndex, setPlayingIndex] = useState<number | null>(null);
  const [showPasteModal, setShowPasteModal] = useState(false);
  const [pasteJson, setPasteJson] = useState('');
  const [repromptBlock, setRepromptBlock] = useState<string | null>(null);

  const getCharStyle = (char?: string) => {
    if (!char) {
      return {
        short: '未設定',
        nameColor: 'text-slate-300',
        avatarBg: 'bg-slate-800 border-slate-500 text-slate-200',
        playIcon: '#94A3B8',
        pillBg: 'bg-slate-800 border-slate-500 text-slate-200',
      };
    }
    if (char.includes('ずんだもん')) {
      return {
        short: 'ずんだ',
        nameColor: 'text-[#34D399]',
        avatarBg: 'bg-[#064E3B] border-[#10B981] text-[#A7F3D0]',
        playIcon: '#10B981',
        pillBg: 'bg-[#064E3B] border-[#10B981] text-[#A7F3D0]',
      };
    }
    if (char.includes('四国めたん') || char.includes('めたん')) {
      return {
        short: 'めたん',
        nameColor: 'text-[#FB7185]',
        avatarBg: 'bg-[#881337] border-[#F43F5E] text-[#FECDD3]',
        playIcon: '#F43F5E',
        pillBg: 'bg-[#881337] border-[#F43F5E] text-[#FECDD3]',
      };
    }
    if (char.includes('つむぎ')) {
      return {
        short: 'つむぎ',
        nameColor: 'text-[#FBBF24]',
        avatarBg: 'bg-[#78350F] border-[#F59E0B] text-[#FDE68A]',
        playIcon: '#F59E0B',
        pillBg: 'bg-[#78350F] border-[#F59E0B] text-[#FDE68A]',
      };
    }
    return {
      short: char.slice(0, 3),
      nameColor: 'text-[#38BDF8]',
      avatarBg: 'bg-sky-950 border-sky-400 text-sky-200',
      playIcon: '#38BDF8',
      pillBg: 'bg-sky-950 border-sky-400 text-sky-200',
    };
  };

  const { scenes, directives, totalDialogueLines, estimatedDurationLabel } = useMemo(() => {
    const script = projectData?.script || [];
    const nonDialogueDirectives: { entry: DirectorScriptEntry; index: number }[] = [];
    const groupedScenes: SceneGroup[] = [];

    let currentBgmLabel: string | null = null;
    let activeBg: string | null = null;
    let currentScene: SceneGroup | null = null;
    let dialogueLines = 0;
    let totalChars = 0;

    script.forEach((entry, index) => {
      if (entry.type === 'bgm' || (!entry.character && !entry.text)) {
        nonDialogueDirectives.push({ entry, index });
        if (entry.type === 'bgm' && entry.path) {
          const vol = entry.volume !== undefined ? ` (${entry.volume}%)` : '';
          currentBgmLabel = `${basename(entry.path)}${vol}`;
        }
        if (entry.bg) {
          activeBg = entry.bg;
        }
        return;
      }

      dialogueLines += 1;
      totalChars += (entry.text || '').length;

      if (entry.bg) {
        activeBg = entry.bg;
      }
      const lineSlide = entry.image || entry.bg || activeBg || null;
      const lineSlideType: 'image' | 'bg' | null = entry.image ? 'image' : lineSlide ? 'bg' : null;

      const shouldStartNewScene =
        !currentScene ||
        (entry.image && entry.image !== currentScene.slideMedia) ||
        (!entry.image && currentScene.slideType === 'image') ||
        (entry.bg && currentScene.items.length > 0 && entry.bg !== currentScene.slideMedia);

      if (shouldStartNewScene || !currentScene) {
        const nextNum = groupedScenes.length + 1;
        const newScene: SceneGroup = {
          sceneNumber: nextNum,
          title: inferSceneTitle(nextNum, lineSlide, entry.text),
          slideMedia: lineSlide,
          slideType: lineSlideType,
          bgmLabel: nextNum === 1 ? currentBgmLabel : null,
          items: [{ entry, index }],
        };
        currentScene = newScene;
        groupedScenes.push(newScene);
      } else {
        currentScene.items.push({ entry, index });
      }
    });

    // ~6.5 chars per second in Voicevox Japanese speech + 0.4s pause per cut
    const estSeconds = Math.max(5, Math.round(totalChars / 6.5 + dialogueLines * 0.4));
    const mins = Math.floor(estSeconds / 60);
    const secs = estSeconds % 60;
    const durationStr = mins > 0 ? `${mins}分${secs.toString().padStart(2, '0')}秒` : `${secs}秒`;

    return {
      scenes: groupedScenes,
      directives: nonDialogueDirectives,
      totalDialogueLines: dialogueLines,
      estimatedDurationLabel: durationStr,
    };
  }, [projectData?.script]);

  const handleAudition = async (text: string, character: string, idx: number) => {
    if (!text.trim()) return;
    setSelectedIndex(idx);
    setPlayingIndex(idx);
    try {
      const blob = await api.auditionVoice(text, character);
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.onended = () => setPlayingIndex(null);
      audio.onerror = () => setPlayingIndex(null);
      await audio.play();
    } catch (e) {
      console.error(e);
      setPlayingIndex(null);
      alert('VOICEVOX試聴に失敗しました。VOICEVOXが起動しているか確認してください。');
    }
  };

  const handleCopyPrompt = async (e: React.MouseEvent<HTMLButtonElement>) => {
    const el = e.currentTarget;
    const orig = el.textContent;
    try {
      const { prompt_markdown } = await api.getAIPrompt();
      await navigator.clipboard.writeText(prompt_markdown);
      el.textContent = '✓ コピー完了!';
      setTimeout(() => {
        el.textContent = orig || '📋 AI用プロンプトをコピー';
      }, 2000);
    } catch (err) {
      console.error(err);
      alert('プロンプトのコピーに失敗しました');
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

  const handleChangeSceneSlide = (scene: SceneGroup) => {
    const currentVal = scene.slideMedia || '';
    const nextVal = prompt(
      `シーン ${scene.sceneNumber} の背景・スライド画像パスを入力してください (空欄で解除):`,
      currentVal
    );
    if (nextVal === null || !projectData) return;

    const trimmed = nextVal.trim();
    const newScript = [...projectData.script];
    scene.items.forEach(({ index }, i) => {
      const target = { ...newScript[index] };
      if (!trimmed) {
        delete target.image;
      } else if (trimmed.includes('/bg/')) {
        if (i === 0) target.bg = trimmed;
        delete target.image;
      } else {
        target.image = trimmed;
      }
      newScript[index] = target;
    });
    setScript(newScript);
  };

  const handleAdd = () => {
    if (!newText.trim()) return;
    addScriptEntry({
      character: newChar,
      emotion: 'normal',
      motion: 'none',
      text: newText.trim(),
    });
    setNewText('');
  };

  if (!projectData) {
    return (
      <div className="p-6 text-sm text-[#94A3B8] flex items-center justify-center h-full">
        プロジェクトを読み込み中...
      </div>
    );
  }

  const newCharStyle = getCharStyle(newChar);

  return (
    <div className="flex flex-col h-full bg-[#111827] text-[#F8FAFC]">
      {/* Panel Header & Web AI Copy-Paste Bridge */}
      <div className="h-[54px] px-5 border-b border-[#1E293B] flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <h2 className="text-[15px] font-extrabold text-[#F8FAFC] whitespace-nowrap">
            1. 台本・スライド編集
          </h2>
          <span className="text-[11.5px] font-medium text-[#64748B] whitespace-nowrap tabular-nums">
            {totalDialogueLines}行 • {estimatedDurationLabel}
          </span>
          {isDirty && (
            <button
              onClick={saveScript}
              className="bg-[#10B981] hover:bg-[#34D399] text-[#080C14] text-[11px] font-extrabold px-2.5 py-1 rounded-[6px] shadow-sm transition-colors whitespace-nowrap"
            >
              💾 保存
            </button>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={handleCopyPrompt}
            className="h-[30px] px-3 rounded-[6px] bg-gradient-to-br from-[#6366F1] to-[#4F46E5] hover:from-[#818CF8] hover:to-[#6366F1] text-white text-[11px] font-extrabold flex items-center gap-1 shadow-sm transition-all whitespace-nowrap"
          >
            📋 AI用プロンプトをコピー
          </button>
          <button
            onClick={() => setShowPasteModal(true)}
            className="h-[30px] px-3 rounded-[6px] bg-[#1E293B] hover:bg-[#334155] border border-[#475569] text-[#E2E8F0] text-[11px] font-bold flex items-center gap-1 transition-colors whitespace-nowrap"
          >
            📥 JSON貼り付け
          </button>
        </div>
      </div>

      {/* Scrollable Scene Blocks Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3.5">
        {/* Global / Non-dialogue Directives Pill Strip (compact) */}
        {directives.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {directives.map(({ entry, index }) => (
              <div
                key={index}
                className="bg-[#0E1525] border border-[#1E293B] rounded-[8px] px-3 py-1.5 flex items-center justify-between gap-3 text-xs w-full"
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <span className="text-[10.5px] font-extrabold bg-amber-500/15 text-amber-400 border border-amber-500/30 px-2 py-0.5 rounded-[5px] shrink-0">
                    {entry.type === 'bgm' ? '🎵 BGM' : `⚙ ${entry.type || '設定'}`}
                  </span>
                  <span className="text-[11.5px] text-[#CBD5E1] font-mono truncate">
                    {entry.path || entry.bg || '未指定'}
                  </span>
                  {entry.volume !== undefined && (
                    <span className="text-[11px] text-[#64748B] shrink-0">
                      音量: {entry.volume}%
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={() => {
                      const nextPath = prompt('BGM/設定ファイルパス:', entry.path || entry.bg || '');
                      if (nextPath !== null) {
                        updateScriptEntry(index, { ...entry, path: nextPath.trim() });
                      }
                    }}
                    className="bg-[#1E293B] hover:bg-[#334155] text-[#94A3B8] hover:text-white px-2 py-0.5 rounded text-[10.5px]"
                  >
                    変更
                  </button>
                  <button
                    onClick={() => deleteScriptEntry(index)}
                    className="bg-[#1E293B] hover:bg-rose-950 text-rose-400 px-1.5 py-0.5 rounded text-[10.5px]"
                    title="削除"
                  >
                    🗑
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Scene Blocks (Matching SVG Scene 1 & Scene 2 Blocks) */}
        {scenes.map((scene) => {
          const slideName = basename(scene.slideMedia);
          const hasSlideMedia = !!scene.slideMedia && activeProjectName;

          return (
            <div
              key={scene.sceneNumber}
              className="rounded-[10px] bg-[#0E1525] border border-[#1E293B] overflow-hidden shadow-sm"
            >
              {/* Scene Header with Inline Slide Thumbnail */}
              <div className="min-h-[58px] px-3 py-2 bg-[#162033] border-b border-[#1E293B]/80 flex items-center justify-between gap-3">
                <div className="flex items-center gap-3 min-w-0">
                  {/* Inline Slide Thumbnail (74 x 42) */}
                  <div
                    onClick={() => handleChangeSceneSlide(scene)}
                    title="クリックしてスライド画像を変更"
                    className={`w-[74px] h-[42px] rounded-[4px] bg-[#0B0F19] border ${
                      scene.sceneNumber === 1 ? 'border-[#38BDF8]' : 'border-[#475569]'
                    } overflow-hidden shrink-0 flex flex-col items-center justify-center relative cursor-pointer group`}
                  >
                    {hasSlideMedia && (
                      <img
                        src={`/api/projects/${encodeURIComponent(activeProjectName!)}/media/${scene.slideMedia}?t=${mediaCacheBust}`}
                        alt={`Slide ${scene.sceneNumber}`}
                        className="absolute inset-0 w-full h-full object-cover opacity-55 group-hover:opacity-75 transition-opacity"
                        onError={(e) => {
                          (e.currentTarget as HTMLImageElement).style.display = 'none';
                        }}
                      />
                    )}
                    <span
                      className={`relative z-10 text-[7.5px] font-extrabold leading-tight tracking-wider ${
                        scene.sceneNumber === 1 ? 'text-[#38BDF8]' : 'text-[#94A3B8]'
                      } drop-shadow`}
                    >
                      SLIDE {scene.sceneNumber}
                    </span>
                    <span className="relative z-10 text-[7px] font-semibold text-[#E2E8F0] truncate max-w-[66px] drop-shadow">
                      {slideName.replace(/\.[a-zA-Z0-9]+$/, '')}
                    </span>
                  </div>

                  {/* Scene Title & Slide/BGM Info */}
                  <div className="min-w-0">
                    <div className="text-[13px] font-extrabold text-[#F8FAFC] truncate">
                      シーン {scene.sceneNumber}：{scene.title}
                    </div>
                    <div className="text-[11px] text-[#94A3B8] truncate mt-0.5">
                      背景スライド: {slideName}
                      {scene.bgmLabel ? ` • BGM: ${scene.bgmLabel}` : ''}
                    </div>
                  </div>
                </div>

                {/* Change Slide Button */}
                <button
                  type="button"
                  onClick={() => handleChangeSceneSlide(scene)}
                  className="h-[26px] px-2.5 rounded-[6px] bg-[#1E293B] hover:bg-[#334155] text-[#38BDF8] text-[11px] font-semibold shrink-0 flex items-center gap-1 transition-colors"
                >
                  🖼 スライド変更
                </button>
              </div>

              {/* Dialogue Lines Inside Scene */}
              <div className="p-3 space-y-2.5">
                {scene.items.map(({ entry, index }) => {
                  const character = entry.character || 'ずんだもん';
                  const text = entry.text || '';
                  const textLen = text.length;
                  const charStyle = getCharStyle(character);
                  const isSelected = selectedIndex === index || playingIndex === index;
                  const isWarn = textLen > 35 && textLen <= 40;
                  const isOverLimit = textLen > 40;

                  let cardBgClass = 'bg-[#151F32] border border-[#1E293B]';
                  if (isOverLimit) {
                    cardBgClass = 'bg-[#28131A] border-[1.4px] border-[#F43F5E]';
                  } else if (isWarn) {
                    cardBgClass = 'bg-[#231B12] border-[1.2px] border-[#F59E0B]';
                  } else if (isSelected) {
                    cardBgClass = 'bg-[#1A2744] border-[1.8px] border-[#3B82F6]';
                  }

                  return (
                    <div
                      key={index}
                      onClick={() => setSelectedIndex(index)}
                      className={`rounded-[8px] px-3 py-2.5 flex items-center gap-3 transition-colors group ${cardBgClass}`}
                    >
                      {/* Circular Character Avatar Badge */}
                      <div
                        className={`w-[40px] h-[40px] rounded-full border-[1.5px] flex items-center justify-center shrink-0 text-[10px] font-extrabold select-none ${charStyle.avatarBg}`}
                      >
                        {charStyle.short}
                      </div>

                      {/* Dialogue Body & Controls */}
                      <div className="flex-1 min-w-0 flex flex-col gap-1">
                        {/* Metadata Row */}
                        <div className="flex items-center justify-between gap-2 flex-wrap">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            {/* Character Selector styled as semantic character label */}
                            <select
                              aria-label="キャラクター選択"
                              value={character}
                              onChange={(e) =>
                                updateScriptEntry(index, { ...entry, character: e.target.value })
                              }
                              className={`bg-transparent font-bold text-[12px] ${charStyle.nameColor} focus:outline-none cursor-pointer pr-1`}
                            >
                              {CHARACTERS.map((c) => (
                                <option key={c} value={c} className="bg-[#111827] text-[#F8FAFC]">
                                  {c}
                                </option>
                              ))}
                            </select>

                            {/* Emotion Tag Pill */}
                            <select
                              aria-label="感情タグ"
                              value={entry.emotion || 'normal'}
                              onChange={(e) =>
                                updateScriptEntry(index, {
                                  ...entry,
                                  emotion: e.target.value as Emotion,
                                })
                              }
                              className="h-[20px] bg-[#1E293B] hover:bg-[#334155] text-[#FDE047] rounded-[5px] text-[10.5px] font-medium px-1.5 focus:outline-none cursor-pointer transition-colors"
                            >
                              {EMOTIONS.map((em) => (
                                <option
                                  key={em.val}
                                  value={em.val}
                                  className="bg-[#111827] text-[#F8FAFC]"
                                >
                                  {em.label}
                                </option>
                              ))}
                            </select>

                            {/* Motion Tag Pill */}
                            <select
                              aria-label="モーション"
                              value={entry.motion || 'none'}
                              onChange={(e) =>
                                updateScriptEntry(index, {
                                  ...entry,
                                  motion: e.target.value as Motion,
                                })
                              }
                              className="h-[20px] bg-[#1E293B] hover:bg-[#334155] text-[#94A3B8] rounded-[5px] text-[10px] font-medium px-1.5 focus:outline-none cursor-pointer transition-colors"
                            >
                              {MOTIONS.map((m) => (
                                <option
                                  key={m.val}
                                  value={m.val}
                                  className="bg-[#111827] text-[#F8FAFC]"
                                >
                                  {m.label}
                                </option>
                              ))}
                            </select>
                          </div>

                          {/* Right: Row Quick Actions (on hover/select) + Character Length Counter */}
                          <div className="flex items-center gap-2 ml-auto">
                            <div className="opacity-0 group-hover:opacity-100 focus-within:opacity-100 flex items-center gap-1 transition-opacity">
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  moveScriptEntry(index, 'up');
                                }}
                                className="bg-[#1E293B] hover:bg-[#334155] text-[#94A3B8] hover:text-white px-1.5 py-0.5 rounded text-[10px]"
                                title="上へ移動"
                              >
                                ↑
                              </button>
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  moveScriptEntry(index, 'down');
                                }}
                                className="bg-[#1E293B] hover:bg-[#334155] text-[#94A3B8] hover:text-white px-1.5 py-0.5 rounded text-[10px]"
                                title="下へ移動"
                              >
                                ↓
                              </button>
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  addScriptEntry({ ...entry });
                                }}
                                className="bg-[#1E293B] hover:bg-[#334155] text-[#94A3B8] hover:text-white px-1.5 py-0.5 rounded text-[10px]"
                                title="セリフを複製"
                              >
                                複製
                              </button>
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  deleteScriptEntry(index);
                                }}
                                className="bg-[#1E293B] hover:bg-rose-950 text-rose-400 px-1.5 py-0.5 rounded text-[10px]"
                                title="セリフを削除"
                              >
                                🗑
                              </button>
                            </div>

                            {textLen <= 35 ? (
                              <span
                                className={`text-[11px] tabular-nums whitespace-nowrap ${
                                  isSelected ? 'text-[#93C5FD] font-semibold' : 'text-[#64748B]'
                                }`}
                              >
                                {textLen}文字 ✓
                              </span>
                            ) : textLen <= 40 ? (
                              <span className="h-[22px] bg-[#78350F] text-[#FDE047] px-2 rounded-[5px] text-[10.5px] font-bold flex items-center gap-1.5 whitespace-nowrap">
                                <span>✂ {textLen}文字 — 2行に分割を推奨</span>
                                <button
                                  type="button"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    splitScriptCuts();
                                  }}
                                  className="underline hover:text-white font-extrabold"
                                >
                                  分割
                                </button>
                              </span>
                            ) : (
                              <span className="h-[22px] bg-rose-950 border border-rose-500/40 text-rose-300 px-2 rounded-[5px] text-[10.5px] font-bold flex items-center gap-1.5 whitespace-nowrap">
                                <span>✂ {textLen}文字 — 2行に分割を推奨</span>
                                <button
                                  type="button"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    splitScriptCuts();
                                  }}
                                  className="bg-rose-500 text-[#080C14] px-1.5 py-0.2 rounded font-extrabold hover:bg-rose-400"
                                >
                                  自動分割
                                </button>
                              </span>
                            )}
                          </div>
                        </div>

                        {/* Dialogue Textarea */}
                        <textarea
                          rows={2}
                          value={text}
                          onChange={(e) =>
                            updateScriptEntry(index, { ...entry, text: e.target.value })
                          }
                          className={`w-full bg-transparent hover:bg-[#0B0F19]/35 focus:bg-[#0B0F19]/65 rounded px-1.5 py-0.5 text-[14px] font-semibold leading-snug resize-none focus:outline-none focus:ring-1 focus:ring-[#3B82F6]/50 transition-colors ${
                            textLen > 35 ? 'text-[#FDE68A]' : 'text-[#F8FAFC]'
                          }`}
                        />

                        {text.startsWith('「ええ、') && (
                          <div className="text-[11px] text-rose-400 font-medium">
                            ⚠ 台本規約: 「ええ、」から始まる相槌は避け、キャラ固有の肯定表現を使用してください
                          </div>
                        )}
                      </div>

                      {/* Circular Audition Play Button (Matches SVG r=15 play circle) */}
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleAudition(text, character, index);
                        }}
                        title="VOICEVOXでセリフを試聴"
                        className={`w-[30px] h-[30px] rounded-full flex items-center justify-center shrink-0 transition-all ${
                          playingIndex === index
                            ? 'bg-[#3B82F6] ring-2 ring-[#93C5FD]/50 scale-105'
                            : isSelected
                            ? 'bg-[#3B82F6] hover:bg-[#2563EB]'
                            : 'bg-[#1E293B] hover:bg-[#334155]'
                        }`}
                      >
                        <svg width="11" height="12" viewBox="0 0 11 12" fill="none" aria-hidden="true">
                          <polygon
                            points="2,1 10,6 2,11"
                            fill={
                              isSelected || playingIndex === index
                                ? '#FFFFFF'
                                : isWarn || isOverLimit
                                ? '#F59E0B'
                                : charStyle.playIcon
                            }
                          />
                        </svg>
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      {/* YMM4-Style Quick Chat Input Bar at Bottom */}
      <div className="p-3 bg-[#111827] border-t border-[#1E293B] shrink-0">
        <div className="h-[52px] rounded-[10px] bg-[#080C14] border border-[#334155] px-2.5 flex items-center gap-2.5">
          <select
            aria-label="追加するキャラクター"
            value={newChar}
            onChange={(e) => setNewChar(e.target.value)}
            className={`h-[34px] px-3 rounded-[7px] border text-[12px] font-extrabold focus:outline-none cursor-pointer shrink-0 ${newCharStyle.pillBg}`}
          >
            {CHARACTERS.map((c) => (
              <option key={c} value={c} className="bg-[#111827] text-[#F8FAFC]">
                {c}
              </option>
            ))}
          </select>

          <input
            type="text"
            className="flex-1 bg-transparent px-2 text-[13px] font-medium text-[#F8FAFC] placeholder-[#64748B] focus:outline-none"
            placeholder="手動でセリフを追加 (Enter)..."
            value={newText}
            onChange={(e) => setNewText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleAdd();
            }}
          />

          <button
            type="button"
            onClick={handleAdd}
            className="h-[34px] px-4 rounded-[7px] bg-[#10B981] hover:bg-[#34D399] text-[#080C14] text-[12.5px] font-extrabold whitespace-nowrap shrink-0 transition-colors"
          >
            ＋ 追加
          </button>
        </div>
      </div>

      {/* Paste JSON Modal */}
      {showPasteModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-xs flex items-center justify-center z-50 p-4">
          <div className="bg-[#111827] border border-[#1E293B] rounded-[14px] p-6 w-full max-w-2xl max-h-screen overflow-y-auto shadow-2xl">
            <h3 className="font-extrabold text-[16px] text-[#F8FAFC] mb-2">
              📥 Web AIの台本JSONを貼り付け
            </h3>
            <p className="text-xs text-[#94A3B8] mb-3">
              ChatGPT / Claude / Gemini で生成した台本JSON配列を貼り付けて適用します。
            </p>
            <textarea
              className="w-full h-48 bg-[#0B0F19] border border-[#334155] rounded-[8px] p-3 text-xs text-[#F8FAFC] font-mono mb-4 focus:outline-none focus:border-[#6366F1]"
              value={pasteJson}
              onChange={(e) => setPasteJson(e.target.value)}
              placeholder='[ { "character": "ずんだもん", "emotion": "happy", "text": "..." } ]'
            />
            {repromptBlock && (
              <div className="mb-4">
                <div className="bg-rose-950/40 border border-rose-800 p-3 rounded-[8px] text-xs font-mono text-rose-300 whitespace-pre-wrap max-h-40 overflow-y-auto">
                  {repromptBlock}
                </div>
                <button
                  onClick={() => navigator.clipboard.writeText(repromptBlock)}
                  className="mt-2 bg-[#1E293B] hover:bg-[#334155] border border-[#475569] px-3 py-1.5 rounded-[6px] text-xs font-bold flex items-center gap-1"
                >
                  📋 修正用Re-Promptをコピー
                </button>
              </div>
            )}
            <div className="flex justify-end gap-2.5">
              <button
                onClick={() => setShowPasteModal(false)}
                className="bg-[#1E293B] hover:bg-[#334155] px-4 py-2 rounded-[8px] text-xs font-bold text-[#E2E8F0]"
              >
                キャンセル
              </button>
              <button
                onClick={handlePasteSubmit}
                className="bg-[#10B981] hover:bg-[#34D399] text-[#080C14] font-extrabold px-5 py-2 rounded-[8px] text-xs"
              >
                台本を適用
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
