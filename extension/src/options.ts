import { loadSettings, saveSettings } from "./apiClient";

function getInput(id: string): HTMLInputElement {
  const element = document.getElementById(id);
  if (!(element instanceof HTMLInputElement)) {
    throw new Error(`missing input #${id}`);
  }
  return element;
}

async function populateForm(): Promise<void> {
  const settings = await loadSettings();
  getInput("base-url").value = settings.baseUrl;
  getInput("api-key").value = settings.apiKey;
}

async function handleSubmit(event: SubmitEvent): Promise<void> {
  event.preventDefault();
  const baseUrl = getInput("base-url").value.trim();
  const apiKey = getInput("api-key").value.trim();
  await saveSettings({ baseUrl, apiKey });

  const status = document.getElementById("save-status");
  if (status) {
    status.textContent = "Salvo.";
    setTimeout(() => {
      status.textContent = "";
    }, 2000);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  void populateForm();
  document.getElementById("settings-form")?.addEventListener("submit", (event) => {
    void handleSubmit(event as SubmitEvent);
  });
});
