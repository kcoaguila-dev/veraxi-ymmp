import React, { useEffect, useRef, useState } from 'react';
import { api } from '../../shared/api';
import type { DevApplyStatus, DevPackResult } from '../../shared/types';

/**
 * Dev view: the web-chat code-editing fallback (WP1-WP8) inside Studio.
 *
 * session-start -> pack -> (web chat) -> apply, using the same backend
 * library functions as the CLI, so every fail-closed guard (allowlist,
 * stale-base, shrink/elision) applies identically. Apply runs as a
 * polled job because it executes ruff/mypy/pytest.
 */
export const DevFallback: React.FC = () => {
  const [sessionText, setSessionText] = useState('');
  const [sessionBusy, setSessionBusy] = useState(false);
  const [sessionError, setSessionError] = useState<string | null>(null);

  const [task, setTask] = useState('');
  const [filesText, setFilesText] = useState('');
  const [mode, setMode] = useState<'full' | 'edit'>('full');
  const [packTest, setPackTest] = useState('');
  const [pack, setPack] = useState<DevPackResult | null>(null);
  const [packBusy, setPackBusy] = useState(false);
  const [packError, setPackError] = useState<string | null>(null);

  const [reply, setReply] = useState('');
  const [allowTests, setAllowTests] = useState(false);
  const [applyTest, setApplyTest] = useState('');
  const [applyJob, setApplyJob] = useState<DevApplyStatus | null>(null);
  const [applyBusy, setApplyBusy] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const handleSessionStart = async () => {
    setSessionBusy(true);
    setSessionError(null);
    try {
      const res = await api.devSessionStart();
      if (!res.success || !res.text) {
        setSessionError(res.error || 'セッション開始テキストの生成に失敗しました');
        return;
      }
      setSessionText(res.text);
    } catch (e: any) {
      setSessionError(e?.data?.error || e?.message || 'セッション開始に失敗しました');
    } finally {
      setSessionBusy(false);
    }
  };

  const handlePack = async () => {
    const files = filesText.split('\n').map((f) => f.trim()).filter(Boolean);
    if (!task.trim() || files.length === 0) return;
    setPackBusy(true);
    setPackError(null);
    setPack(null);
    try {
      const res = await api.devPack({
        task: task.trim(),
        files,
        mode,
        test: packTest.trim() || undefined,
      });
      if (!res.success) {
        setPackError(res.error || 'パック作成に失敗しました');
        return;
      }
      setPack(res);
    } catch (e: any) {
      setPackError(e?.data?.error || e?.message || 'パック作成に失敗しました');
    } finally {
      setPackBusy(false);
    }
  };

  const handleApply = async () => {
    if (!reply.trim()) return;
    if (!window.confirm('Web AIの返信を新しいGitブランチへ適用し、チェック (ruff/mypy/pytest) を実行します。よろしいですか？')) return;
    setApplyBusy(true);
    setApplyError(null);
    setApplyJob(null);
    try {
      const res = await api.devApply({
        reply,
        mode,
        pack_id: pack?.pack_id,
        allow_tests: allowTests,
        test: applyTest.trim() || undefined,
      });
      if (!res.success || !res.job_id) {
        setApplyError(res.error || '適用を開始できませんでした');
        setApplyBusy(false);
        return;
      }
      const jobId = res.job_id;
      const poll = async () => {
        if (!mountedRef.current) return;
        try {
          const status = await api.devApplyStatus(jobId);
          if (!mountedRef.current) return;
          setApplyJob(status);
          if (status.status === 'done') {
            setApplyBusy(false);
          } else {
            window.setTimeout(poll, 1500);
          }
        } catch (e: any) {
          if (!mountedRef.current) return;
          setApplyError(e?.data?.error || e?.message || '適用状況の取得に失敗しました');
          setApplyBusy(false);
        }
      };
      void poll();
    } catch (e: any) {
      setApplyError(e?.data?.error || e?.message || '適用を開始できませんでした');
      setApplyBusy(false);
    }
  };

  const textareaCls = 'w-full bg-[#0B0F19] border border-[#334155] rounded-[6px] p-2.5 text-[11px] text-[#E2E8F0] placeholder:text-[#475569] font-mono';
  const inputCls = 'w-full bg-[#0B0F19] border border-[#334155] rounded-[6px] px-2.5 py-1.5 text-[12px] text-[#E2E8F0] placeholder:text-[#475569]';
  const btnCls = 'text-[11px] font-extrabold px-3 py-1.5 rounded-[6px] whitespace-nowrap disabled:opacity-50 transition-colors';

  return (
    <div className="h-full overflow-y-auto space-y-4 pr-0.5">
      <div className="rounded-[14px] bg-[#111827] border border-[#1E293B] p-5">
        <h2 className="text-[13px] font-extrabold text-[#F8FAFC]">🛠 開発フォールバック (Web Chat)</h2>
        <p className="text-[11.5px] text-[#94A3B8] mt-1">
          ローカルエージェントのクォータ切れ時に、Webチャット (Claude / Gemini / ChatGPT) とコピペだけでコード変更を続けるための画面です。
          適用はCLIと同じガード (許可リスト・陳腐化・縮小チェック) を通し、不正な返信は<strong className="text-[#FDE68A]">何も書き込まず失敗</strong>します。
          対象リポジトリはこのバックエンドが動作している veraxi-ymmp リポジトリ自体です。
        </p>
      </div>

      <section className="rounded-[14px] bg-[#111827] border border-[#1E293B] p-5 space-y-2.5">
        <h3 className="text-[12px] font-extrabold text-[#E2E8F0]">① セッション開始 (session-start)</h3>
        <p className="text-[11px] text-[#64748B]">ルール・Git状態・TODOをまとめた貼り付け用テキストを生成します。新しいWebチャットの冒頭に貼ってください。</p>
        <div className="flex items-center gap-2 flex-wrap">
          <button type="button" onClick={handleSessionStart} disabled={sessionBusy} className={`${btnCls} bg-[#1E293B] hover:bg-[#334155] border border-[#475569] text-[#E2E8F0]`}>
            {sessionBusy ? '⏳ 生成中...' : 'セッション開始テキストを生成'}
          </button>
          {sessionText && (
            <button type="button" onClick={() => navigator.clipboard.writeText(sessionText)} className={`${btnCls} bg-[#1E293B] hover:bg-[#334155] border border-[#475569] text-[#E2E8F0]`}>
              📋 コピー
            </button>
          )}
          {sessionError && <span className="text-[11.5px] font-semibold text-[#FECDD3]">⚠ {sessionError}</span>}
        </div>
        {sessionText && <textarea readOnly value={sessionText} rows={10} className={textareaCls} aria-label="セッション開始テキスト" />}
      </section>

      <section className="rounded-[14px] bg-[#111827] border border-[#1E293B] p-5 space-y-2.5">
        <h3 className="text-[12px] font-extrabold text-[#E2E8F0]">② パック作成 (pack)</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
          <input value={task} onChange={(e) => setTask(e.target.value)} placeholder="タスク内容 (例: fix(app): handle empty script)" className={inputCls} aria-label="タスク" />
          <div className="flex gap-2">
            <select value={mode} onChange={(e) => setMode(e.target.value as 'full' | 'edit')} className="bg-[#0B0F19] border border-[#334155] rounded-[6px] px-2 py-1.5 text-[12px] text-[#E2E8F0]" aria-label="返信モード">
              <option value="full">full (ファイル全体)</option>
              <option value="edit">edit (SEARCH/REPLACE)</option>
            </select>
            <input value={packTest} onChange={(e) => setPackTest(e.target.value)} placeholder="対象テスト (任意) 例: tests/test_x.py" className={inputCls} aria-label="対象テスト" />
          </div>
        </div>
        <textarea value={filesText} onChange={(e) => setFilesText(e.target.value)} rows={4} placeholder={'対象ファイルを1行に1つ (リポジトリ相対パス)\n例: veraxi_ymmp/app/pack_apply.py'} className={textareaCls} aria-label="対象ファイル" />
        <div className="flex items-center gap-2 flex-wrap">
          <button type="button" onClick={handlePack} disabled={packBusy || !task.trim() || !filesText.trim()} className={`${btnCls} bg-gradient-to-br from-[#6366F1] to-[#4F46E5] text-white`}>
            {packBusy ? '⏳ 作成中...' : 'パックを作成'}
          </button>
          {pack?.bundle && (
            <>
              <span className="text-[11px] text-[#94A3B8]">{pack.chars?.toLocaleString()} 文字 · pack_id: {pack.pack_id}</span>
              <button type="button" onClick={() => navigator.clipboard.writeText(pack.bundle || '')} className={`${btnCls} bg-[#1E293B] hover:bg-[#334155] border border-[#475569] text-[#E2E8F0]`}>
                📋 バンドルをコピー
              </button>
            </>
          )}
          {packError && <span className="text-[11.5px] font-semibold text-[#FECDD3]">⚠ {packError}</span>}
        </div>
        {pack?.bundle && <textarea readOnly value={pack.bundle} rows={10} className={textareaCls} aria-label="パックバンドル" />}
        <p className="text-[11px] text-[#F59E0B]">⚠ パックは内容を伏せ字にしません。貼り付ける前にバンドルを確認してください (CLI版と同じ注意)。</p>
      </section>

      <section className="rounded-[14px] bg-[#111827] border border-[#1E293B] p-5 space-y-2.5">
        <h3 className="text-[12px] font-extrabold text-[#E2E8F0]">③ 返信を適用 (apply{mode === 'edit' ? '-edit' : ''})</h3>
        <textarea value={reply} onChange={(e) => setReply(e.target.value)} rows={8} placeholder="Web AIの返信 (ファイルブロック / SEARCH-REPLACEブロック) をここに貼り付け" className={textareaCls} aria-label="Web AIの返信" />
        <div className="flex items-center gap-3 flex-wrap">
          <label className="flex items-center gap-1.5 text-[11.5px] text-[#CBD5E1]">
            <input type="checkbox" checked={allowTests} onChange={(e) => setAllowTests(e.target.checked)} />
            テストファイルの変更を許可
          </label>
          <input value={applyTest} onChange={(e) => setApplyTest(e.target.value)} placeholder="対象テスト (任意)" className="bg-[#0B0F19] border border-[#334155] rounded-[6px] px-2.5 py-1.5 text-[12px] text-[#E2E8F0] placeholder:text-[#475569] w-64" aria-label="適用時の対象テスト" />
          <button type="button" onClick={handleApply} disabled={applyBusy || !reply.trim()} className={`${btnCls} bg-gradient-to-br from-[#10B981] to-[#059669] text-white`}>
            {applyBusy ? '⏳ 適用中 (チェック実行中)...' : '新しいブランチへ適用'}
          </button>
          {applyError && <span className="text-[11.5px] font-semibold text-[#FECDD3]">⚠ {applyError}</span>}
        </div>
        {applyJob?.status === 'done' && (
          <p className={`text-[12px] font-extrabold rounded-[6px] px-2.5 py-1.5 ${applyJob.exit_code === 0 ? 'bg-[#064E3B] text-[#A7F3D0]' : 'bg-[#4C0519] text-[#FECDD3]'}`}>
            {applyJob.exit_code === 0 ? '✓ 適用完了 — チェック通過' : '✗ 適用されませんでした (ガード拒否またはチェック失敗) — 何も変更されていないか、出力で確認してください'}
          </p>
        )}
        {applyJob?.output && (
          <pre className="bg-[#0B0F19] border border-[#1E293B] rounded-[6px] p-2.5 text-[10.5px] text-[#94A3B8] max-h-64 overflow-y-auto whitespace-pre-wrap">{applyJob.output}</pre>
        )}
      </section>
    </div>
  );
};
