import { test, describe, beforeEach } from 'node:test';
import assert from 'node:assert';
import {
  PROJECT_STORAGE_KEY,
  PROJECT_URL_PARAM,
  getUrlProjectName,
  getStoredProjectName,
  getInitialProjectName,
  persistActiveProject,
  resolveActiveProject
} from './project-storage.ts';

describe('project-storage tests', () => {
  let mockStorage: Record<string, string> = {};
  let currentUrl = 'http://localhost:1420/';

  beforeEach(() => {
    mockStorage = {};
    currentUrl = 'http://localhost:1420/';

    // Mock localStorage
    (globalThis as any).localStorage = {
      getItem: (key: string) => mockStorage[key] ?? null,
      setItem: (key: string, value: string) => {
        mockStorage[key] = String(value);
      },
      removeItem: (key: string) => {
        delete mockStorage[key];
      },
      clear: () => {
        mockStorage = {};
      }
    };

    // Mock window and history
    (globalThis as any).window = {
      get location() {
        const parsed = new URL(currentUrl);
        return {
          href: currentUrl,
          search: parsed.search
        };
      },
      history: {
        replaceState: (_data: any, _unused: string, newUrl: string) => {
          currentUrl = newUrl;
        }
      }
    };
  });

  test('getStoredProjectName retrieves item from localStorage', () => {
    assert.strictEqual(getStoredProjectName(), null);
    mockStorage[PROJECT_STORAGE_KEY] = '04_php';
    assert.strictEqual(getStoredProjectName(), '04_php');
  });

  test('getUrlProjectName retrieves project from URL search query', () => {
    assert.strictEqual(getUrlProjectName(), null);
    currentUrl = 'http://localhost:1420/?project=04_php';
    assert.strictEqual(getUrlProjectName(), '04_php');
  });

  test('getInitialProjectName prioritizes URL over localStorage', () => {
    mockStorage[PROJECT_STORAGE_KEY] = '01_costco';
    currentUrl = 'http://localhost:1420/?project=04_php';
    assert.strictEqual(getInitialProjectName(), '04_php');

    // When URL has no project param, falls back to localStorage
    currentUrl = 'http://localhost:1420/';
    assert.strictEqual(getInitialProjectName(), '01_costco');
  });

  test('persistActiveProject updates both localStorage and URL', () => {
    persistActiveProject('04_php');
    assert.strictEqual(mockStorage[PROJECT_STORAGE_KEY], '04_php');
    assert.strictEqual(currentUrl, 'http://localhost:1420/?project=04_php');
  });

  test('resolveActiveProject resolves preferredName when it exists', () => {
    const projects = [
      { name: '01_costco' },
      { name: '02_market' },
      { name: '04_php' }
    ];
    const resolved = resolveActiveProject(projects, '04_php');
    assert.strictEqual(resolved, '04_php');
  });

  test('resolveActiveProject falls back to URL or stored when preferred is invalid', () => {
    mockStorage[PROJECT_STORAGE_KEY] = '04_php';
    const projects = [
      { name: '01_costco' },
      { name: '02_market' },
      { name: '04_php' }
    ];
    // Non-existent preferred
    const resolved = resolveActiveProject(projects, '99_non_existent');
    assert.strictEqual(resolved, '04_php');
  });

  test('resolveActiveProject falls back to first project when stored is invalid', () => {
    mockStorage[PROJECT_STORAGE_KEY] = '99_deleted_project';
    const projects = [
      { name: '01_costco' },
      { name: '02_market' }
    ];
    const resolved = resolveActiveProject(projects, null);
    assert.strictEqual(resolved, '01_costco');
  });

  test('resolveActiveProject returns null for empty project list', () => {
    assert.strictEqual(resolveActiveProject([], '04_php'), null);
  });
});
