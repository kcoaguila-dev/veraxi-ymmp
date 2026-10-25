export const PROJECT_STORAGE_KEY = 'veraxi_active_project';
export const PROJECT_URL_PARAM = 'project';

/**
 * Reads the active project name from the browser URL search params (?project=...).
 */
export function getUrlProjectName(): string | null {
  try {
    if (typeof window !== 'undefined' && window.location?.search) {
      const params = new URLSearchParams(window.location.search);
      const val = params.get(PROJECT_URL_PARAM);
      if (val && val.trim()) {
        return val.trim();
      }
    }
  } catch (e) {
    // Ignore URL parsing errors
  }
  return null;
}

/**
 * Reads the active project name from localStorage.
 */
export function getStoredProjectName(): string | null {
  try {
    if (typeof localStorage !== 'undefined') {
      const stored = localStorage.getItem(PROJECT_STORAGE_KEY);
      if (stored && stored.trim()) {
        return stored.trim();
      }
    }
  } catch (e) {
    // Ignore localStorage access errors (e.g. storage disabled/sandbox)
  }
  return null;
}

/**
 * Gets the initial project candidate before project list is loaded.
 * Priority: URL query param -> localStorage -> null.
 */
export function getInitialProjectName(): string | null {
  return getUrlProjectName() || getStoredProjectName();
}

/**
 * Persists the active project to both localStorage and the browser URL query parameter.
 */
export function persistActiveProject(name: string): void {
  if (!name || !name.trim()) return;
  const cleanName = name.trim();

  try {
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(PROJECT_STORAGE_KEY, cleanName);
    }
  } catch (e) {
    // Ignore localStorage errors
  }

  try {
    if (typeof window !== 'undefined' && window.location) {
      const url = new URL(window.location.href);
      if (url.searchParams.get(PROJECT_URL_PARAM) !== cleanName) {
        url.searchParams.set(PROJECT_URL_PARAM, cleanName);
        window.history.replaceState(null, '', url.toString());
      }
    }
  } catch (e) {
    // Ignore history API errors
  }
}

/**
 * Resolves the project name to activate given the available projects list.
 *
 * Priority:
 * 1. preferredName (if provided and exists in projects)
 * 2. URL search param (if valid and exists in projects)
 * 3. localStorage (if valid and exists in projects)
 * 4. First project in projects array
 * 5. null (if projects is empty)
 */
export function resolveActiveProject(
  projects: Array<{ name: string }>,
  preferredName?: string | null
): string | null {
  if (!projects || projects.length === 0) {
    return null;
  }

  // 1. Explicit preferred name (e.g., activeProjectName or user selection)
  if (preferredName && projects.some((p) => p.name === preferredName)) {
    return preferredName;
  }

  // 2. URL query param
  const urlName = getUrlProjectName();
  if (urlName && projects.some((p) => p.name === urlName)) {
    return urlName;
  }

  // 3. Stored in localStorage
  const storedName = getStoredProjectName();
  if (storedName && projects.some((p) => p.name === storedName)) {
    return storedName;
  }

  // 4. Default fallback to first project
  return projects[0].name;
}
