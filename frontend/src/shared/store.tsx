import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { api } from './api';
import { ProjectSummary, ProjectData, PipelineStatus, VoicevoxHealth, DirectorScriptEntry } from './types';

interface StudioState {
  projects: ProjectSummary[];
  activeProjectName: string | null;
  projectData: ProjectData | null;
  voicevoxHealth: VoicevoxHealth | null;
  pipelineStatus: PipelineStatus;
  isDirty: boolean;

  loadProjects: () => Promise<void>;
  createProject: (name: string) => Promise<void>;
  setActiveProject: (name: string) => Promise<void>;

  updateScriptEntry: (index: number, entry: DirectorScriptEntry) => void;
  addScriptEntry: (entry: DirectorScriptEntry) => void;
  deleteScriptEntry: (index: number) => void;
  moveScriptEntry: (index: number, direction: 'up' | 'down') => void;
  splitScriptCuts: () => Promise<void>;
  setScript: (script: DirectorScriptEntry[]) => void;

  saveScript: () => Promise<any>;
  runPipeline: (useTts?: boolean) => Promise<void>;

  refreshMedia: () => void;
  mediaCacheBust: number;
}

const StudioContext = createContext<StudioState | null>(null);

export const StudioProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [activeProjectName, setActiveProjectName] = useState<string | null>(null);
  const [projectData, setProjectData] = useState<ProjectData | null>(null);
  const [voicevoxHealth, setVoicevoxHealth] = useState<VoicevoxHealth | null>(null);
  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatus>({ status: 'idle' });
  const [isDirty, setIsDirty] = useState(false);
  const [mediaCacheBust, setMediaCacheBust] = useState(Date.now());

  useEffect(() => {
    loadProjects();
    checkVoicevox();
    const interval = setInterval(checkVoicevox, 15000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    let interval: number;
    if (pipelineStatus.status === 'running' && activeProjectName) {
      interval = window.setInterval(async () => {
        try {
          const status = await api.getPipelineStatus(activeProjectName);
          setPipelineStatus(status);
          if (status.status === 'complete') {
            refreshMedia();
          }
        } catch (e) {
          console.error('Failed to poll pipeline status', e);
        }
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [pipelineStatus.status, activeProjectName]);

  const checkVoicevox = async () => {
    try {
      const health = await api.getVoicevoxHealth();
      setVoicevoxHealth(health);
    } catch (e) {
      setVoicevoxHealth({ available: false, url: '', speakers: [] });
    }
  };

  const loadProjects = async () => {
    try {
      const res = await api.getProjects();
      setProjects(res.projects);
      if (res.projects.length > 0 && !activeProjectName) {
        setActiveProject(res.projects[0].name);
      }
    } catch (e) {
      console.error('Failed to load projects', e);
    }
  };

  const createProject = async (name: string) => {
    await api.createProject(name);
    await loadProjects();
    await setActiveProject(name);
  };

  const setActiveProject = async (name: string) => {
    setActiveProjectName(name);
    try {
      const data = await api.getProject(name);
      setProjectData(data);
      setIsDirty(false);
      setPipelineStatus({ status: 'idle' });
      refreshMedia();
    } catch (e) {
      console.error('Failed to load project data', e);
    }
  };

  const updateScriptEntry = (index: number, entry: DirectorScriptEntry) => {
    if (!projectData) return;
    const newScript = [...projectData.script];
    newScript[index] = entry;
    setProjectData({ ...projectData, script: newScript });
    setIsDirty(true);
  };

  const addScriptEntry = (entry: DirectorScriptEntry) => {
    if (!projectData) return;
    setProjectData({ ...projectData, script: [...projectData.script, entry] });
    setIsDirty(true);
  };

  const deleteScriptEntry = (index: number) => {
    if (!projectData) return;
    const newScript = [...projectData.script];
    newScript.splice(index, 1);
    setProjectData({ ...projectData, script: newScript });
    setIsDirty(true);
  };

  const moveScriptEntry = (index: number, direction: 'up' | 'down') => {
    if (!projectData) return;
    if (direction === 'up' && index === 0) return;
    if (direction === 'down' && index === projectData.script.length - 1) return;

    const newScript = [...projectData.script];
    const target = direction === 'up' ? index - 1 : index + 1;
    [newScript[index], newScript[target]] = [newScript[target], newScript[index]];
    setProjectData({ ...projectData, script: newScript });
    setIsDirty(true);
  };

  const splitScriptCuts = async () => {
    if (!projectData || !activeProjectName) return;
    try {
      const res = await api.splitScript(activeProjectName, projectData.script, 40);
      setProjectData({ ...projectData, script: res.script });
      setIsDirty(true);
    } catch (e) {
      console.error('Failed to split script', e);
    }
  };

  const setScript = (script: DirectorScriptEntry[]) => {
    if (!projectData) return;
    setProjectData({ ...projectData, script });
    setIsDirty(true);
  };

  const saveScript = async () => {
    if (!projectData || !activeProjectName) return;
    try {
      const res = await api.saveProjectScript(activeProjectName, projectData.script, projectData.broll_manifest);
      setIsDirty(false);
      return res;
    } catch (e: any) {
      if (e.data) return e.data;
      throw e;
    }
  };

  const runPipeline = async (useTts: boolean = true) => {
    if (!activeProjectName) return;
    try {
      await api.runPipeline(activeProjectName, useTts);
      setPipelineStatus({ status: 'running', stage: 'starting', progress: 0 });
    } catch (e) {
      console.error('Failed to run pipeline', e);
    }
  };

  const refreshMedia = () => setMediaCacheBust(Date.now());

  const value: StudioState = {
    projects,
    activeProjectName,
    projectData,
    voicevoxHealth,
    pipelineStatus,
    isDirty,
    loadProjects,
    createProject,
    setActiveProject,
    updateScriptEntry,
    addScriptEntry,
    deleteScriptEntry,
    moveScriptEntry,
    splitScriptCuts,
    setScript,
    saveScript,
    runPipeline,
    refreshMedia,
    mediaCacheBust
  };

  return <StudioContext.Provider value={value}>{children}</StudioContext.Provider>;
};

export const useStudioStore = () => {
  const context = useContext(StudioContext);
  if (!context) {
    throw new Error('useStudioStore must be used within a StudioProvider');
  }
  return context;
};
