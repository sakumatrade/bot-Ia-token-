/**
 * Minimal ambient declaration for the WebExtension `browser` global
 * (the promise-based namespace Safari, like Firefox, provides — as
 * opposed to Chrome's callback-based `chrome.*`). Only the surface this
 * extension actually uses is declared, on purpose: no scripting, tabs
 * querying beyond opening one, or any host-reaching API beyond storage.
 */

interface BrowserStorageArea {
  get(keys: string[]): Promise<Record<string, unknown>>;
  set(items: Record<string, unknown>): Promise<void>;
}

interface BrowserRuntime {
  onInstalled: {
    addListener(callback: () => void): void;
  };
}

interface BrowserTabs {
  create(options: { url: string }): Promise<unknown>;
}

interface BrowserApi {
  storage: { local: BrowserStorageArea };
  runtime: BrowserRuntime;
  tabs: BrowserTabs;
}

declare const browser: BrowserApi;
