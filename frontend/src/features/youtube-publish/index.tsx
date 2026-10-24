import React, { useState, useEffect } from 'react';
import { useStudioStore } from '../../shared/store';
import { api } from '../../shared/api';

export const YoutubePublish: React.FC = () => {
  const { projectData, activeProjectName, mediaCacheBust, refreshMedia } = useStudioStore();
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [tags, setTags] = useState('');
  const [privacyStatus, setPrivacyStatus] = useState<'private' | 'unlisted' | 'public'>('private');
  const [publishAt, setPublishAt] = useState('');
  const [mockUpload, setMockUpload] = useState(true);

  const [isPublishing, setIsPublishing] = useState(false);
  const [publishResult, setPublishResult] = useState<any>(null);
  const [isRegeneratingThumb, setIsRegeneratingThumb] = useState(false);

  useEffect(() => {
    if (activeProjectName) {
      setTitle(activeProjectName);
    }
  }, [activeProjectName]);

  const handleRegenerateThumb = async () => {
    if (!activeProjectName) return;
    setIsRegeneratingThumb(true);
    try {
      await api.generateThumbnail(activeProjectName);
      refreshMedia();
    } catch (e) {
      console.error(e);
      alert('Failed to regenerate thumbnail');
    }
    setIsRegeneratingThumb(false);
  };

  const handlePublish = async () => {
    if (!activeProjectName) return;
    setIsPublishing(true);
    setPublishResult(null);
    try {
      const payload = {
        title,
        description,
        tags: tags.split(',').map(t => t.trim()).filter(Boolean),
        privacy_status: privacyStatus,
        publish_at: publishAt || undefined,
        mock_upload: mockUpload
      };
      const res = await api.uploadToYoutube(activeProjectName, payload);
      setPublishResult(res);
    } catch (e: any) {
      console.error(e);
      setPublishResult({ error: e.data?.error || e.message || 'Upload failed' });
    }
    setIsPublishing(false);
  };

  if (!projectData) return null;

  return (
    <div className="bg-panel border border-structural rounded flex flex-col text-[#F8FAFC]">
      <div className="p-4 border-b border-structural flex justify-between items-center">
        <h2 className="font-bold text-lg">3. YouTubeサムネイル・投稿</h2>
        {publishResult && publishResult.video_id && (
            <a href={`https://youtu.be/${publishResult.video_id}`} target="_blank" rel="noreferrer" className="text-emerald-400 text-sm font-bold hover:underline">
                View on YouTube ↗
            </a>
        )}
      </div>
      <div className="p-4 flex gap-4 flex-col lg:flex-row">
        <div className="flex-1 flex flex-col gap-2">
            <div className="aspect-video bg-layer rounded flex flex-col items-center justify-center text-xs overflow-hidden border border-hover relative">
                {projectData.thumbnail_path ? (
                    <img
                        src={`/api/projects/${activeProjectName}/media/thumbnail.png?t=${mediaCacheBust}`}
                        alt="Thumbnail Preview"
                        className="w-full h-full object-cover"
                        onError={(e: any) => e.target.style.display = 'none'}
                    />
                ) : (
                    <span>No Thumbnail</span>
                )}
            <div className="absolute bottom-1 right-1 bg-black/80 text-white text-[10px] px-1 rounded font-mono">1:30</div>
            </div>
            <button
                onClick={handleRegenerateThumb}
                disabled={isRegeneratingThumb}
                className="bg-layer hover:bg-hover px-3 py-1 rounded text-sm w-full disabled:opacity-50"
            >
                {isRegeneratingThumb ? '🔄 Generating...' : '🔄 サムネイル再生成'}
            </button>
        </div>
        <div className="flex-[2] flex flex-col gap-3">
          <input
            type="text"
            className="w-full bg-layer border border-hover rounded px-2 py-1 text-sm font-bold"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Video Title"
          />
          <textarea
            className="w-full bg-layer border border-hover rounded px-2 py-1 text-sm h-20"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Video Description"
          />
          <input
            type="text"
            className="w-full bg-layer border border-hover rounded px-2 py-1 text-sm"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            placeholder="Tags (comma separated)"
          />

          <div className="flex gap-2">
              <select
                className="flex-1 bg-layer border border-hover rounded px-2 py-2 text-sm"
                value={privacyStatus}
                onChange={(e) => setPrivacyStatus(e.target.value as any)}
                disabled={!!publishAt}
              >
                <option value="private">🔒 非公開 (Private)</option>
                <option value="unlisted">🔗 限定公開 (Unlisted)</option>
                <option value="public">🌍 公開 (Public)</option>
              </select>

              <input
                type="datetime-local"
                className="flex-1 bg-layer border border-hover rounded px-2 py-2 text-sm"
                value={publishAt}
                onChange={(e) => {
                    setPublishAt(e.target.value);
                    if (e.target.value) {
                        setPrivacyStatus('private');
                    }
                }}
              />
          </div>
          {publishAt && <div className="text-xs text-amber-400">Scheduled publish requires privacy to be set to Private.</div>}

          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={mockUpload} onChange={e => setMockUpload(e.target.checked)} />
            Mock Upload (テスト投稿 - Do not actually upload)
          </label>

          <button
            onClick={handlePublish}
            disabled={isPublishing}
            className="w-full bg-shikoku hover:bg-[#E11D48] text-white font-bold py-2 rounded shadow text-sm disabled:opacity-50 mt-auto"
          >
            {isPublishing ? '🚀 Uploading...' : '🚀 YouTubeへ投稿'}
          </button>

          {publishResult && (
              <div className={`p-2 rounded text-xs mt-2 ${publishResult.error ? 'bg-rose-900/20 text-rose-400' : 'bg-emerald-900/20 text-emerald-400'}`}>
                  {publishResult.error ? `Error: ${publishResult.error}` : `Success! Video ID: ${publishResult.video_id} (Status: ${publishResult.status})`}
              </div>
          )}
        </div>
      </div>
    </div>
  );
};
