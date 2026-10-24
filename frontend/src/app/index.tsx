import React from 'react'
import { WorkspaceToolbar } from '../features/workspace-toolbar'
import { StoryboardScript } from '../features/storyboard-script'
import { VideoPreview } from '../features/video-preview'
import { YoutubePublish } from '../features/youtube-publish'

export const App: React.FC = () => {
  return (
    <div className="flex flex-col h-full bg-canvas text-[#F8FAFC] font-sans">
      <WorkspaceToolbar />
      <div className="flex flex-1 overflow-hidden">
        <div className="flex-[2] overflow-hidden border-r border-structural">
          <StoryboardScript />
        </div>
        <div className="flex-1 flex flex-col overflow-y-auto">
          <VideoPreview />
          <div className="p-4">
            <YoutubePublish />
          </div>
        </div>
      </div>
    </div>
  )
}
