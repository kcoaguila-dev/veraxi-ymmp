import React, { useState, useMemo, useEffect } from 'react';
import { useStudioStore } from '../../shared/store';
import { api } from '../../shared/api';
import { auditionManager, AuditionState } from '../../shared/audio-manager';
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

export interface ParsedPastePayload {
  script: any[];
  broll_manifest?: any[];
}

export function extractAndCleanJson(rawText: string): ParsedPastePayload {
  let text = rawText.trim();
  if (!text) {
    throw new Error('入力が空です。Web AIが生成した台本JSONを貼り付けてください。');
  }

  // 1. If wrapped in markdown code fence (```json ... ``` or ``` ... ```), extract the block
  const codeBlockMatch = text.match(/```(?:json)?\s*([\s\S]*?)\s*```/);
  if (codeBlockMatch && codeBlockMatch[1]) {
    text = codeBlockMatch[1].trim();
  } else {
    // 2. Fallback: Find outer array [ ... ] or object { ... }
    const firstBracket = text.indexOf('[');
    const firstBrace = text.indexOf('{');
    let startIdx = -1;
    let endIdx = -1;

    if (firstBracket !== -1 && (firstBrace === -1 || firstBracket < firstBrace)) {
      startIdx = firstBracket;
      endIdx = text.lastIndexOf(']');
    } else if (firstBrace !== -1) {
      startIdx = firstBrace;
      endIdx = text.lastIndexOf('}');
    }

    if (startIdx !== -1 && endIdx !== -1 && endIdx > startIdx) {
      text = text.substring(startIdx, endIdx + 1).trim();
    }
  }

  // Helper to remove trailing commas before } or ] and normalize quotes
  const sanitizeCommas = (str: string) =>
    str.replace(/,\s*([\]}])/g, '$1').replace(/[\u201C\u201D]/g, '"');

  let parsed: any;
  try {
    parsed = JSON.parse(text);
  } catch (err: any) {
    try {
      const sanitized = sanitizeCommas(text);
      parsed = JSON.parse(sanitized);
    } catch {
      throw new Error(`JSON解析エラー: ${err.message}`);
    }
  }

  // Normalize: direct array of script cuts
  if (Array.isArray(parsed)) {
    return { script: parsed };
  }

  // Normalize: object containing script and optionally broll_manifest
  if (parsed && typeof parsed === 'object') {
    const script = Array.isArray(parsed.script)
      ? parsed.script
      : Array.isArray(parsed.entries)
      ? parsed.entries
      : Array.isArray(parsed.dialogue)
      ? parsed.dialogue
      : null;

    if (!script) {
      throw new Error('貼り付けられたデータ内に台本配列（"script": [...]）が見つかりません。');
    }

    const broll_manifest = Array.isArray(parsed.broll_manifest) ? parsed.broll_manifest : undefined;
    return { script, broll_manifest };
  }
  throw new Error('貼り付けられたデータが台本配列（[...]）または台本オブジェクト（{ "script": [...] }）ではありません。');
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
    setActiveProject,
    isDirty,
    mediaCacheBust,
  } = useStudioStore();

  const [newChar, setNewChar] = useState('ずんだもん');
  const [newText, setNewText] = useState('');
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [auditionState, setAuditionState] = useState<AuditionState>(auditionManager.getState());

  useEffect(() => {
    return auditionManager.subscribe((state) => {
      setAuditionState(state);
    });
  }, []);

  useEffect(() => {
    // Cleanly stop any audition when active project changes or component unmounts
    auditionManager.stop();
    return () => {
      auditionManager.stop();
    };
  }, [activeProjectName]);

  const [showPasteModal, setShowPasteModal] = useState(false);
  const [showPromptModal, setShowPromptModal] = useState(false);
  const [promptTopic, setPromptTopic] = useState('');
  const [promptLengthMode, setPromptLengthMode] = useState<'golden' | 'medium' | 'short'>('golden');
  const [copySuccessMsg, setCopySuccessMsg] = useState<string | null>(null);
  const [pasteJson, setPasteJson] = useState('');
  const [repromptBlock, setRepromptBlock] = useState<string | null>(null);
  const [isAutoSplitting, setIsAutoSplitting] = useState(false);

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

  const handleAudition = (text: string, character: string, idx: number) => {
    setSelectedIndex(idx);
    auditionManager.toggle(idx, text, character);
  };

  const handleCopyPromptWithOptions = async (withTopic: boolean = true) => {
    try {
      const { prompt_markdown } = await api.getAIPrompt();
      let finalPrompt = prompt_markdown;
      const topic = promptTopic.trim();

      let lengthInstruction = '';
      if (promptLengthMode === 'golden') {
        lengthInstruction = `\n\n---\n## 👑 目標ボリューム・普遍的5章構成指定（王道ゴールデンゾーン：約8〜12分 / 110〜130カット / 総文字数 3,500〜4,500字以上）
※ 要約や途中で打ち切る短縮は厳禁です。YouTubeアルゴリズムで最高評価（総再生時間・維持率向上）を得るため、
必ず以下の【全5章・合計110〜130カット・総文字数3,500字以上】の充実した台本を作成してください。
※ 10文字程度の細切れ文でカット数だけを稼ぐのは禁止です。1カットあたり平均25〜35文字のしっかりした文述を心がけてください。

### 【普遍的5章構成・カット数ノルマ】
1. **第1章：導入・常識と疑問のフック（約 18〜22カット / slide_01.png）**
   - 冒頭10秒で視聴者の関心を惹く「常識を覆す事実」や「意外な謎・対立の構図」を提示。
2. **第2章：現状と背景の深掘り・表面的な実態（約 22〜26カット / slide_02.png）**
   - 世間一般で知られているイメージや公表データ、前提となる基本事実・仕組みを整理。
3. **第3章：核心の課題・裏に潜む最大の決定打（約 25〜30カット / slide_03.png）**
   - テーマにおける最も重要かつ深刻な問題点、見過ごされがちな根本原因、または歴史的・構造的転換点を徹底解剖。
4. **第4章：多角的分析・関係者や周囲への波及効果（約 22〜26カット / slide_04.png）**
   - 当事者や社会・市場・周辺環境に与えている影響、具体的な事例や因果関係を客観的に掘り下げ。
5. **第5章：解決策・未来の展望と明確な結論（約 20〜25カット / slide_05.png）**
   - 今後の展望、現代における解決策や教訓、視聴者が納得できる明快なまとめ。

### 【出力フォーマット（台本 ＋ スライド定義の一括出力）】
必ず以下の通り、\`script\` 配列と、台本で参照するスライド（slide_01.png〜slide_05.png）を網羅した \`broll_manifest\` 配列を両方含んだ単一のJSONオブジェクトで出力してください：

\`\`\`json
{
  "script": [
    {
      "character": "ずんだもん",
      "text": "セリフ内容（25〜35文字程度）",
      "emotion": "excited",
      "motion": "jump",
      "bgm": "assets/bgm/10c_style_bgm.ogg",
      "sfx": "assets/sfx/pon.wav",
      "image": "broll/slide_01.png",
      "character_position": "left",
      "subtitle_position": "bottom_center",
      "subtitle_style": "outlined"
    }
  ],
  "broll_manifest": [
    {
      "type": "vs",
      "filename": "slide_01.png",
      "title": "スライドタイトル",
      "step_tag": "第1章",
      "hero_title": "メインの見出し",
      "hero_status": "補足・ステータス",
      "left_box": ["比較A", "説明A", "amber"],
      "right_box": ["比較B", "説明B", "green"],
      "bottom_tag": "結論",
      "bottom_text": "要点の一言まとめ",
      "theme_color": "blue"
    }
  ]
}
\`\`\`
※ スライドの type は "overview"（概要・箇条書き）, "metric"（数値強調）, "vs"（左右対決・対比）から選んでください。
※ 出力トークン制限で途中で止まりそうな場合は、まず第1章〜第3章を出力し、続けて残りを出すようにしてください。\n`;
      } else if (promptLengthMode === 'medium') {
        lengthInstruction = `\n\n---\n## ⚡ 目標ボリューム・普遍的構成指定（テンポ重視解説：約4〜6分 / 50〜70カット / 総文字数 1,800〜2,200字）
※ 表面的な箇条書き要約にせず、テーマの核心をしっかり掘り下げた満足度の高い対話にするため、
以下の【全4章・合計50〜70カット】の台本JSONオブジェクト（"script" と "broll_manifest"）を作成してください。

### 【普遍的構成・カット数ノルマ】
1. **第1章：導入・疑問とフック（約 10〜12カット / slide_01.png）**：興味を惹く疑問や意外な事実の提示。
2. **第2章：基本構造と現状（約 15〜18カット / slide_02.png）**：背景と基本の仕組みを解説。
3. **第3章：核心の課題・深掘り（約 15〜18カット / slide_03.png）**：最大のポイントや問題の深掘り。
4. **第4章：教訓・未来・まとめ（約 10〜15カット / slide_04.png）**：結論とこれからの展望。

※ 出力フォーマットは {"script": [...], "broll_manifest": [...]} の形式で、各スライドの定義も必ず含めてください。\n`;
      } else {
        lengthInstruction = `\n\n---\n## 📱 目標ボリューム・構成指定（YouTube Shorts：約60秒以内 / 14〜18カット）
※ 冒頭1秒の強烈なフックから、核心の意外な事実、オチまでを端的にテンポよく展開してください（14〜18カット）。
※ スライドを使わない場合は "image": null としてください。\n`;
      }

      finalPrompt += lengthInstruction;

      if (withTopic && topic) {
        finalPrompt += `\n---\n## 今回の動画テーマ・元ネタ情報\n以下のテーマ・参考情報をもとに、上記ルール・制約（1カット20〜35字の自然な文区切り、10文字未満の細切れ分割禁止、事実厳守、指定感情・アセット）を厳守して台本JSONを作成してください：\n\n${topic}\n`;
      }

      await navigator.clipboard.writeText(finalPrompt);
      setCopySuccessMsg(withTopic && topic ? '✓ テーマ・構成付きプロンプトをコピーしました！' : '✓ 構成付きプロンプトをコピーしました！');
      setTimeout(() => {
        setCopySuccessMsg(null);
        setShowPromptModal(false);
      }, 1400);
    } catch (err) {
      console.error(err);
      alert('プロンプトのコピーに失敗しました');
    }
  };

  const handlePasteSubmit = async () => {
    if (!activeProjectName) return;
    setRepromptBlock(null);

    let payload: ParsedPastePayload;
    try {
      payload = extractAndCleanJson(pasteJson);
    } catch (e: any) {
      setRepromptBlock(`Failed to parse JSON: ${e.message}\n\n【貼り付けられた先頭テキスト】\n${pasteJson.trim().slice(0, 300)}...`);
      return;
    }

    let parsed = payload.script;

    // Auto-split long lines (>40 chars) using BudouX on the backend if needed
    const hasLongLines = parsed.some(
      (e) => e && typeof e.text === 'string' && e.text.length > 40
    );

    if (hasLongLines) {
      setIsAutoSplitting(true);
      try {
        const splitRes = await api.splitScript(activeProjectName, parsed, 40);
        if (splitRes && Array.isArray(splitRes.script)) {
          parsed = splitRes.script;
        }
      } catch (err) {
        console.warn('Auto-split request error, continuing with parsed', err);
      } finally {
        setIsAutoSplitting(false);
      }
    }

    try {
      const res = await api.saveProjectScript(activeProjectName, parsed, payload.broll_manifest);
      if (res.success) {
        await setActiveProject(activeProjectName);
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
        setRepromptBlock(`Failed to save script: ${e.message || 'Unknown error'}`);
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
            onClick={() => setShowPromptModal(true)}
            className="h-[30px] px-3 rounded-[6px] bg-gradient-to-br from-[#6366F1] to-[#4F46E5] hover:from-[#818CF8] hover:to-[#6366F1] text-white text-[11px] font-extrabold flex items-center gap-1.5 shadow-sm transition-all whitespace-nowrap"
          >
            📋 AIプロンプト生成
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
                  const isSelected = selectedIndex === index || auditionState.playingIndex === index;
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

                      {/* Circular Audition Play/Stop Button */}
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleAudition(text, character, index);
                        }}
                        title={
                          auditionState.playingIndex === index
                            ? 'クリックして試聴を停止'
                            : 'VOICEVOXでセリフを試聴'
                        }
                        aria-label={
                          auditionState.playingIndex === index
                            ? '試聴を停止'
                            : 'VOICEVOXで試聴'
                        }
                        className={`w-[30px] h-[30px] rounded-full flex items-center justify-center shrink-0 transition-all ${
                          auditionState.playingIndex === index
                            ? 'bg-[#3B82F6] ring-2 ring-[#93C5FD]/50 scale-105 shadow-[0_0_12px_rgba(59,130,246,0.6)]'
                            : isSelected
                            ? 'bg-[#3B82F6] hover:bg-[#2563EB]'
                            : 'bg-[#1E293B] hover:bg-[#334155]'
                        }`}
                      >
                        {auditionState.playingIndex === index && auditionState.isLoading ? (
                          <svg className="animate-spin h-3.5 w-3.5 text-white" viewBox="0 0 24 24" fill="none">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"></path>
                          </svg>
                        ) : auditionState.playingIndex === index ? (
                          <svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden="true">
                            <rect width="10" height="10" rx="1.5" fill="#FFFFFF" />
                          </svg>
                        ) : (
                          <svg width="11" height="12" viewBox="0 0 11 12" fill="none" aria-hidden="true">
                            <polygon
                              points="2,1 10,6 2,11"
                              fill={
                                isSelected
                                  ? '#FFFFFF'
                                  : isWarn || isOverLimit
                                  ? '#F59E0B'
                                  : charStyle.playIcon
                              }
                            />
                          </svg>
                        )}
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

      {/* AI Prompt Generator with Topic Input Modal */}
      {showPromptModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-xs flex items-center justify-center z-50 p-4">
          <div className="bg-[#111827] border border-[#1E293B] rounded-[14px] p-6 w-full max-w-xl shadow-2xl">
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-extrabold text-[16px] text-[#F8FAFC] flex items-center gap-2">
                📋 Web AI用プロンプト生成
              </h3>
              <span className="text-[10.5px] bg-[#1E293B] text-[#94A3B8] px-2 py-0.5 rounded font-mono">
                ChatGPT / Claude / Gemini
              </span>
            </div>
            <p className="text-xs text-[#94A3B8] mb-4 leading-relaxed">
              外部Web版AI向けに、内蔵アセットや文字数制約を遵守した正確な台本JSONを出力させる指示プロンプトを作成します。
            </p>

            {/* Target Duration / Mode Selector */}
            <div className="mb-4">
              <label className="block text-xs font-bold text-[#CBD5E1] mb-2 flex items-center justify-between">
                <span>動画の目標尺・構成タイプ</span>
                <span className="text-[11px] text-[#A5B4FC] font-semibold">YouTubeアルゴリズム最適化</span>
              </label>
              <div className="grid grid-cols-3 gap-2">
                <button
                  type="button"
                  onClick={() => setPromptLengthMode('golden')}
                  className={`p-2.5 rounded-[9px] border text-left transition-all relative ${
                    promptLengthMode === 'golden'
                      ? 'bg-[#1E1B4B]/80 border-[#6366F1] shadow-md shadow-[#6366F1]/10'
                      : 'bg-[#0B0F19] border-[#1E293B] hover:border-[#334155] opacity-75 hover:opacity-100'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[12px] font-extrabold text-[#F8FAFC]">👑 王道ゴールデン</span>
                    <span className="text-[10px] font-mono px-1.5 py-0.5 bg-[#4338CA]/60 text-[#C7D2FE] rounded">8〜12分</span>
                  </div>
                  <div className="text-[10.5px] text-[#94A3B8] leading-tight">
                    80〜120カット・5章構成。総再生時間＆収益化に特化
                  </div>
                </button>

                <button
                  type="button"
                  onClick={() => setPromptLengthMode('medium')}
                  className={`p-2.5 rounded-[9px] border text-left transition-all ${
                    promptLengthMode === 'medium'
                      ? 'bg-[#1E1B4B]/80 border-[#6366F1] shadow-md shadow-[#6366F1]/10'
                      : 'bg-[#0B0F19] border-[#1E293B] hover:border-[#334155] opacity-75 hover:opacity-100'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[12px] font-extrabold text-[#F8FAFC]">⚡ テンポ解説</span>
                    <span className="text-[10px] font-mono px-1.5 py-0.5 bg-[#334155] text-[#CBD5E1] rounded">4〜6分</span>
                  </div>
                  <div className="text-[10.5px] text-[#94A3B8] leading-tight">
                    40〜60カット。離脱を防ぎ要点をスピーディに解説
                  </div>
                </button>

                <button
                  type="button"
                  onClick={() => setPromptLengthMode('short')}
                  className={`p-2.5 rounded-[9px] border text-left transition-all ${
                    promptLengthMode === 'short'
                      ? 'bg-[#1E1B4B]/80 border-[#6366F1] shadow-md shadow-[#6366F1]/10'
                      : 'bg-[#0B0F19] border-[#1E293B] hover:border-[#334155] opacity-75 hover:opacity-100'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[12px] font-extrabold text-[#F8FAFC]">📱 Shorts</span>
                    <span className="text-[10px] font-mono px-1.5 py-0.5 bg-[#334155] text-[#CBD5E1] rounded">〜60秒</span>
                  </div>
                  <div className="text-[10.5px] text-[#94A3B8] leading-tight">
                    14〜18カット。YouTube Shorts / TikTok専用
                  </div>
                </button>
              </div>
            </div>

            <div className="mb-4">
              <label className="block text-xs font-bold text-[#CBD5E1] mb-1.5">
                動画のテーマ・元ネタ・記事URL（任意）
              </label>
              <textarea
                className="w-full h-32 bg-[#0B0F19] border border-[#334155] rounded-[8px] p-3 text-xs text-[#F8FAFC] font-sans focus:outline-none focus:border-[#6366F1] resize-none"
                value={promptTopic}
                onChange={(e) => setPromptTopic(e.target.value)}
                placeholder="例: なぜコストコは年会費だけで利益を出せるのか？仕組みとビジネスモデルをずんだもんとめたんで分かりやすく解説してほしい。またはニュース記事や箇条書きメモをそのまま貼り付け"
              />
              <p className="text-[11px] text-[#64748B] mt-1">
                ※ 入力するとプロンプト末尾にテーマ指示が自動結合されます。空欄の場合は汎用プロンプトのみコピーされます。
              </p>
            </div>

            {copySuccessMsg && (
              <div className="mb-4 bg-emerald-950/50 border border-emerald-500/50 text-emerald-300 text-xs font-bold p-2.5 rounded-[8px] flex items-center gap-2">
                {copySuccessMsg}
              </div>
            )}

            <div className="flex items-center justify-between pt-3 border-t border-[#1E293B]">
              <button
                type="button"
                onClick={() => handleCopyPromptWithOptions(false)}
                className="text-xs text-[#94A3B8] hover:text-[#E2E8F0] font-medium underline transition-colors"
              >
                プロンプトのみコピー (テーマなし)
              </button>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setShowPromptModal(false)}
                  className="bg-[#1E293B] hover:bg-[#334155] px-4 py-2 rounded-[8px] text-xs font-bold text-[#E2E8F0]"
                >
                  閉じる
                </button>
                <button
                  type="button"
                  onClick={() => handleCopyPromptWithOptions(true)}
                  className="bg-gradient-to-br from-[#6366F1] to-[#4F46E5] hover:from-[#818CF8] hover:to-[#6366F1] text-white font-extrabold px-5 py-2 rounded-[8px] text-xs shadow-md transition-all flex items-center gap-1.5"
                >
                  📋 テーマ付きでコピー
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Paste JSON Modal */}
      {showPasteModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-xs flex items-center justify-center z-50 p-4">
          <div className="bg-[#111827] border border-[#1E293B] rounded-[14px] p-6 w-full max-w-2xl max-h-screen overflow-y-auto shadow-2xl">
            <h3 className="font-extrabold text-[16px] text-[#F8FAFC] mb-2">
              📥 Web AIの台本JSONを貼り付け
            </h3>
            <p className="text-xs text-[#94A3B8] mb-3">
              ChatGPT / Claude / Gemini で生成した台本JSONを貼り付けて適用します。
              <span className="text-[#38BDF8] ml-1">
                （※ Markdownの ```json 囲みや前後の会話テキストは自動除去されます）
              </span>
            </p>
            <textarea
              className="w-full h-48 bg-[#0B0F19] border border-[#334155] rounded-[8px] p-3 text-xs text-[#F8FAFC] font-mono mb-3 focus:outline-none focus:border-[#6366F1]"
              value={pasteJson}
              onChange={(e) => setPasteJson(e.target.value)}
              placeholder='[ { "character": "ずんだもん", "emotion": "happy", "text": "..." } ]'
            />
            {isAutoSplitting && (
              <div className="mb-3 bg-amber-950/40 border border-amber-600/50 text-amber-300 text-xs p-2.5 rounded-[8px] flex items-center gap-2">
                ⏳ 40文字を超える長文カットを自動分割中 (BudouX)...
              </div>
            )}
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
