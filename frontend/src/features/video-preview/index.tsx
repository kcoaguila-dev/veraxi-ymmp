import React from 'react';

export const VideoPreview: React.FC = () => {
  return (
    <div className="flex flex-col gap-2 p-4 bg-canvas">
      <div className="relative w-full aspect-video bg-black rounded overflow-hidden border border-structural">
        <video className="w-full h-full object-contain" controls src="qa_test.mp4" />
        <div className="absolute bottom-0 left-0 w-full h-2 bg-layer">
          <div className="absolute top-0 left-[20%] w-1 h-full bg-zundamon"></div>
        </div>
      </div>
      <div className="flex justify-end">
        <span className="px-2 py-1 bg-zundamon text-canvas text-xs font-bold rounded">
          🔊 音量バランス: 最適 ✓
        </span>
      </div>
    </div>
  );
};
