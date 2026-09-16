/**
 * Minimal MV3 service worker: on install, seeds a default Local API base
 * URL if none is set yet. It never touches the API key and never makes a
 * network request on its own — every fetch happens from popup.ts, and
 * only ever to the Local API (see apiClient.ts).
 */

const DEFAULT_BASE_URL = "http://127.0.0.1:8765";

browser.runtime.onInstalled.addListener(() => {
  void browser.storage.local.get(["baseUrl"]).then((stored) => {
    if (typeof stored.baseUrl !== "string" || stored.baseUrl.length === 0) {
      void browser.storage.local.set({ baseUrl: DEFAULT_BASE_URL });
    }
  });
});
