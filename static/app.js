(function () {
  const buttons = Array.from(document.querySelectorAll("[data-kind]"));
  const panels = Array.from(document.querySelectorAll("[data-panel]"));
  const textPanel = document.querySelector(".message-field");
  const audioButton = document.querySelector("[data-record-audio]");
  const audioStatus = document.querySelector("[data-record-status]");
  const responseForm = document.querySelector("form[data-min-age]");
  const sendButton = responseForm ? responseForm.querySelector(".send-button") : null;
  let recorder = null;
  let chunks = [];

  function setKind(kind) {
    buttons.forEach((button) => {
      const active = button.dataset.kind === kind;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
    panels.forEach((panel) => {
      const visible = panel.dataset.panel === kind || (kind === "text" && panel === textPanel);
      panel.classList.toggle("hidden", !visible);
    });
  }

  buttons.forEach((button) => {
    button.addEventListener("click", () => setKind(button.dataset.kind));
  });

  if (responseForm && sendButton) {
    const waitSeconds = Number(responseForm.dataset.minAge || "0");
    if (waitSeconds > 0) {
      const readyLabel = sendButton.dataset.readyLabel || sendButton.textContent;
      sendButton.disabled = true;
      sendButton.textContent = "Só um instantinho...";
      window.setTimeout(() => {
        sendButton.disabled = false;
        sendButton.textContent = readyLabel;
      }, waitSeconds * 1000);
    }
  }

  if (audioButton && navigator.mediaDevices && window.MediaRecorder) {
    audioButton.addEventListener("click", async () => {
      if (recorder && recorder.state === "recording") {
        recorder.stop();
        return;
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        chunks = [];
        recorder = new MediaRecorder(stream);
        recorder.addEventListener("dataavailable", (event) => chunks.push(event.data));
        recorder.addEventListener("stop", () => {
          const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
          const file = new File([blob], "recado-da-chapeuzinho.webm", { type: blob.type });
          const input = document.querySelector('input[name="media_audio"]');
          const transfer = new DataTransfer();
          transfer.items.add(file);
          input.files = transfer.files;
          stream.getTracks().forEach((track) => track.stop());
          audioButton.textContent = "Gravar de novo";
          audioStatus.textContent = "Áudio pronto para enviar.";
        });
        recorder.start();
        audioButton.textContent = "Parar gravação";
        audioStatus.textContent = "Gravando...";
      } catch (error) {
        audioStatus.textContent = "Não consegui abrir o microfone. Você pode escolher um arquivo de áudio.";
      }
    });
  }
})();
