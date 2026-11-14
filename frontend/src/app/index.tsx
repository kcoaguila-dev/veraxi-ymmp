import React, { Component, ErrorInfo, ReactNode, useState } from 'react'
import { WorkspaceToolbar } from '../features/workspace-toolbar'
import { StoryboardScript } from '../features/storyboard-script'
import { VideoPreview } from '../features/video-preview'
import { YoutubePublish } from '../features/youtube-publish'
import { ResearchDossier } from '../features/research-dossier'

const WORKFLOW_STEPS = [
  '1. リサーチ & 素材',
  '2. 台本 & 監査',
  '3. 動画生成 & QA',
  '4. サムネ & 公開',
] as const

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("UI Uncaught Error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center h-full p-8 bg-[#0B0F19] text-[#F8FAFC]">
          <div className="bg-[#111827] border border-rose-900/50 rounded-xl p-6 max-w-xl w-full shadow-2xl">
            <h2 className="text-xl font-bold text-rose-400 mb-2">⚠ UI Rendering Error</h2>
            <p className="text-sm text-gray-300 mb-4">
              An error occurred while rendering the interface:
            </p>
            <pre className="bg-[#1F2937] p-3 rounded text-xs font-mono text-rose-300 overflow-x-auto mb-4 whitespace-pre-wrap">
              {this.state.error?.message || 'Unknown error'}
            </pre>
            <button
              onClick={() => window.location.reload()}
              className="bg-emerald-600 hover:bg-emerald-500 text-white font-bold px-4 py-2 rounded text-sm transition-colors"
            >
              🔄 Reload Studio
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export const App: React.FC = () => {
  const [activeStep, setActiveStep] = useState(1)
  return (
    <ErrorBoundary>
      <div className="flex flex-col h-full bg-[#0B0F19] text-[#F8FAFC] font-sans select-none">
        <WorkspaceToolbar />
        {/* Golden Path Stepper: Steps 1-2 (research/ingest) -> 3 (audit) -> 4-5 (generate/QA) -> publish */}
        <nav className="h-[42px] px-6 bg-[#0B0F19] border-b border-[#1E293B] flex items-center gap-2 shrink-0" aria-label="ワークフロー">
          {WORKFLOW_STEPS.map((label, idx) => (
            <React.Fragment key={label}>
              <button
                type="button"
                onClick={() => setActiveStep(idx)}
                className={`h-[28px] px-3.5 rounded-full text-[12px] font-extrabold transition-colors ${
                  activeStep === idx
                    ? 'bg-gradient-to-br from-[#10B981] to-[#059669] text-white'
                    : 'bg-[#1E293B] text-[#94A3B8] hover:text-white border border-[#334155]'
                }`}
              >
                {label}
              </button>
              {idx < WORKFLOW_STEPS.length - 1 && <span className="text-[#475569] text-xs">→</span>}
            </React.Fragment>
          ))}
        </nav>
        <main className="flex-1 grid grid-cols-1 lg:grid-cols-[minmax(480px,46%)_1fr] gap-5 p-4 lg:p-5 overflow-hidden">
          {/* LEFT WORKSPACE: Step 1-2 RESEARCH PANEL or STORYBOARD & WEB-AI COPY-PASTE BRIDGE */}
          <section className="h-full overflow-hidden rounded-[14px] bg-[#111827] border border-[#1E293B] shadow-[0_6px_20px_rgba(0,0,0,0.4)] flex flex-col">
            {activeStep === 0 ? (
              <ResearchDossier onIngestDone={() => setActiveStep(1)} />
            ) : (
              <StoryboardScript />
            )}
          </section>

          {/* RIGHT WORKSPACE: 2. PREVIEW PLAYER + 3. YOUTUBE UPLOAD CARD */}
          <section className="h-full overflow-y-auto flex flex-col gap-4 pr-0.5">
            <VideoPreview />
            <YoutubePublish />
          </section>
        </main>
      </div>
    </ErrorBoundary>
  )
}
