const form = document.querySelector("#run-form");
const repoInput = document.querySelector("#repo-path");
const runButton = document.querySelector("#run-button");
const status = document.querySelector("#run-status");
const output = document.querySelector("#run-output");

function showResult(state, label, message) {
  status.dataset.state = state;
  status.textContent = label;
  output.textContent = message;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const repo = repoInput.value.trim();

  if (!repo) {
    showResult("error", "Repository required", "Enter a local path or HTTPS Git URL.");
    repoInput.focus();
    return;
  }

  runButton.disabled = true;
  repoInput.disabled = true;
  showResult("running", "Running", "Resetting repository and starting pytest…");

  try {
    const response = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ repo }),
    });
    const payload = await response.json();

    if (!response.ok) {
      throw new Error(payload.error || `Request failed with status ${response.status}`);
    }

    showResult(
      payload.success ? "success" : "stopped",
      payload.success ? "Tests pass" : "Stopped safely",
      payload.output || "OpenClaw finished without console output.",
    );
  } catch (error) {
    showResult("error", "Could not run", error.message || "Unexpected request error.");
  } finally {
    runButton.disabled = false;
    repoInput.disabled = false;
    status.focus();
  }
});
