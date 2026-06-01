(function () {
  const form = document.querySelector("form[data-min-age]");
  if (!form) {
    return;
  }

  const state = {
    text: "",
    photoUrl: "",
    audioUrl: ""
  };

  const fields = {
    message: form.querySelector("[data-message-input]"),
    photo: form.querySelector("[data-photo-input]"),
    audio: form.querySelector("[data-audio-input]")
  };

  const preview = createPreview(form.querySelector("[data-content-preview]"), state);
  const modals = createModals(form);
  createSubmitGuard(form, preview);
  createTextComposer(form, modals, preview, state, fields);
  createCameraComposer(form, modals, preview, state, fields);
  createAudioComposer(form, modals, preview, state, fields);

  function createSubmitGuard(responseForm, contentPreview) {
    const sendButton = responseForm.querySelector(".send-button[type='submit']");
    if (sendButton) {
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

    responseForm.addEventListener("submit", (event) => {
      const hasText = fields.message && fields.message.value.trim().length > 0;
      const hasPhoto = fields.photo && fields.photo.files && fields.photo.files.length > 0;
      const hasAudio = fields.audio && fields.audio.files && fields.audio.files.length > 0;
      if (!hasText && !hasPhoto && !hasAudio) {
        event.preventDefault();
        showFormMessage(responseForm, "Antes de enviar, deixe uma pista: escreva um recado, tire uma foto ou grave um áudio.");
        contentPreview.render();
      }
    });
  }

  function createModals(scope) {
    const modalEls = Array.from(scope.querySelectorAll("[data-modal]"));
    const openers = Array.from(scope.querySelectorAll("[data-open-modal]"));
    const api = {
      open(name) {
        modalEls.forEach((modal) => {
          modal.classList.toggle("hidden", modal.dataset.modal !== name);
        });
        document.body.classList.add("modal-open");
        const modal = modalEls.find((item) => item.dataset.modal === name);
        const focusable = modal && modal.querySelector("textarea, button, input");
        if (focusable) {
          window.setTimeout(() => focusable.focus(), 20);
        }
        scope.dispatchEvent(new CustomEvent("composer:open", { detail: { name } }));
      },
      close() {
        modalEls.forEach((modal) => modal.classList.add("hidden"));
        document.body.classList.remove("modal-open");
        scope.dispatchEvent(new CustomEvent("composer:close"));
      }
    };

    openers.forEach((button) => {
      button.addEventListener("click", () => api.open(button.dataset.openModal));
    });
    scope.addEventListener("click", (event) => {
      if (event.target.matches("[data-close-modal]") || event.target.matches(".modal")) {
        api.close();
      }
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        api.close();
      }
    });
    return api;
  }

  function createPreview(container, appState) {
    return {
      render() {
        if (!container) {
          return;
        }
        container.classList.remove("empty");
        if (appState.photoUrl) {
          container.innerHTML = `<img src="${appState.photoUrl}" alt="Foto escolhida">`;
          return;
        }
        if (appState.audioUrl) {
          container.innerHTML = `<div class="preview-audio"><span aria-hidden="true">♪</span><audio controls src="${appState.audioUrl}"></audio></div>`;
          return;
        }
        if (appState.text.trim()) {
          container.innerHTML = `<p>${escapeHtml(appState.text)}</p>`;
          return;
        }
        container.classList.add("empty");
        container.innerHTML = "<p>Escolha texto, foto ou áudio para deixar sua pista.</p>";
      }
    };
  }

  function createTextComposer(scope, modals, contentPreview, appState, inputs) {
    const draft = scope.querySelector("[data-text-draft]");
    const saveButton = scope.querySelector("[data-save-text]");
    if (!draft || !saveButton || !inputs.message) {
      return;
    }
    saveButton.addEventListener("click", () => {
      appState.text = draft.value.trim();
      inputs.message.value = appState.text;
      clearFile(inputs.photo);
      clearFile(inputs.audio);
      appState.photoUrl = "";
      appState.audioUrl = "";
      contentPreview.render();
      modals.close();
    });
    scope.addEventListener("composer:open", (event) => {
      if (event.detail.name === "text") {
        draft.value = inputs.message.value;
      }
    });
  }

  function createCameraComposer(scope, modals, contentPreview, appState, inputs) {
    const camera = scope.querySelector("[data-camera]");
    const openButton = scope.querySelector("[data-open-camera]");
    const captureButton = scope.querySelector("[data-capture-photo]");
    const retakeButton = scope.querySelector("[data-retake-photo]");
    const pickButton = scope.querySelector("[data-pick-photo]");
    const video = scope.querySelector("[data-camera-preview]");
    const image = scope.querySelector("[data-photo-preview]");
    const canvas = scope.querySelector("[data-photo-canvas]");
    const status = scope.querySelector("[data-camera-status]");
    let stream = null;

    if (!camera || !inputs.photo) {
      return;
    }

    scope.addEventListener("composer:open", (event) => {
      if (event.detail.name === "photo") {
        openCamera();
      }
    });
    scope.addEventListener("composer:close", stopCamera);

    openButton.addEventListener("click", openCamera);
    pickButton.addEventListener("click", () => inputs.photo.click());
    retakeButton.addEventListener("click", () => {
      inputs.photo.value = "";
      image.removeAttribute("src");
      camera.classList.remove("camera-captured");
      openCamera();
    });
    inputs.photo.addEventListener("change", () => {
      const file = inputs.photo.files && inputs.photo.files[0];
      if (!file) {
        return;
      }
      setPhoto(file, URL.createObjectURL(file));
      modals.close();
    });
    captureButton.addEventListener("click", () => {
      if (!video || !canvas) {
        return;
      }
      const width = video.videoWidth || 960;
      const height = video.videoHeight || 720;
      canvas.width = width;
      canvas.height = height;
      canvas.getContext("2d").drawImage(video, 0, 0, width, height);
      canvas.toBlob((blob) => {
        if (!blob) {
          status.textContent = "Não consegui guardar a foto. Tente de novo.";
          return;
        }
        const file = new File([blob], "foto-da-chapeuzinho.jpg", { type: "image/jpeg" });
        assignFile(inputs.photo, file);
        setPhoto(file, URL.createObjectURL(blob));
        modals.close();
      }, "image/jpeg", 0.88);
    });

    async function openCamera() {
      if (!navigator.mediaDevices || !video) {
        status.textContent = "Neste aparelho, escolha uma foto do arquivo.";
        return;
      }
      try {
        stopCamera();
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: "environment" } },
          audio: false
        });
        video.srcObject = stream;
        captureButton.disabled = false;
        camera.classList.add("camera-live");
        camera.classList.remove("camera-captured");
        status.textContent = "Enquadre sua pista e toque no botão redondo.";
      } catch (error) {
        captureButton.disabled = true;
        status.textContent = "Não consegui abrir a câmera. Você pode escolher uma foto do aparelho.";
      }
    }

    function setPhoto(file, url) {
      stopCamera();
      appState.photoUrl = url;
      appState.audioUrl = "";
      appState.text = "";
      inputs.message.value = "";
      clearFile(inputs.audio);
      image.src = url;
      camera.classList.add("camera-captured");
      camera.classList.remove("camera-live");
      retakeButton.classList.remove("hidden");
      status.textContent = `Foto pronta: ${file.name}`;
      contentPreview.render();
    }

    function stopCamera() {
      if (stream) {
        stream.getTracks().forEach((track) => track.stop());
        stream = null;
      }
      if (video) {
        video.srcObject = null;
      }
      if (captureButton) {
        captureButton.disabled = true;
      }
      camera.classList.remove("camera-live");
    }
  }

  function createAudioComposer(scope, modals, contentPreview, appState, inputs) {
    const recordButton = scope.querySelector("[data-record-audio]");
    const playButton = scope.querySelector("[data-play-audio]");
    const deleteButton = scope.querySelector("[data-delete-audio]");
    const pickButton = scope.querySelector("[data-pick-audio]");
    const status = scope.querySelector("[data-record-status]");
    const previewAudio = scope.querySelector("[data-audio-preview]");
    const recorderBox = scope.querySelector("[data-recorder]");
    let recorder = null;
    let chunks = [];
    let stream = null;

    if (!recordButton || !inputs.audio) {
      return;
    }

    recordButton.addEventListener("click", async () => {
      if (recorder && recorder.state === "recording") {
        recorder.stop();
        return;
      }
      await startRecording();
    });
    playButton.addEventListener("click", () => {
      if (previewAudio.src) {
        previewAudio.play();
      }
    });
    deleteButton.addEventListener("click", () => {
      inputs.audio.value = "";
      appState.audioUrl = "";
      previewAudio.removeAttribute("src");
      playButton.classList.add("hidden");
      deleteButton.classList.add("hidden");
      previewAudio.classList.add("hidden");
      status.textContent = "Toque no círculo para gravar.";
      contentPreview.render();
    });
    pickButton.addEventListener("click", () => inputs.audio.click());
    inputs.audio.addEventListener("change", () => {
      const file = inputs.audio.files && inputs.audio.files[0];
      if (file) {
        setAudio(file, URL.createObjectURL(file));
        modals.close();
      }
    });
    scope.addEventListener("composer:close", stopStream);

    async function startRecording() {
      if (!navigator.mediaDevices || !window.MediaRecorder) {
        status.textContent = "Neste aparelho, escolha um arquivo de áudio.";
        return;
      }
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        chunks = [];
        const audioType = preferredAudioType();
        recorder = audioType ? new MediaRecorder(stream, { mimeType: audioType }) : new MediaRecorder(stream);
        recorder.addEventListener("dataavailable", (event) => {
          if (event.data && event.data.size > 0) {
            chunks.push(event.data);
          }
        });
        recorder.addEventListener("stop", () => {
          const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
          const file = new File([blob], `recado-da-chapeuzinho.${audioExtension(blob.type)}`, { type: blob.type });
          assignFile(inputs.audio, file);
          setAudio(file, URL.createObjectURL(blob));
          stopStream();
        });
        recorder.start();
        recorderBox.classList.add("recording");
        recordButton.setAttribute("aria-label", "Parar gravação");
        status.textContent = "Gravando...";
      } catch (error) {
        status.textContent = "Não consegui abrir o microfone. Você pode escolher um arquivo de áudio.";
      }
    }

    function setAudio(file, url) {
      appState.audioUrl = url;
      appState.photoUrl = "";
      appState.text = "";
      inputs.message.value = "";
      clearFile(inputs.photo);
      previewAudio.src = url;
      previewAudio.classList.remove("hidden");
      playButton.classList.remove("hidden");
      deleteButton.classList.remove("hidden");
      recorderBox.classList.remove("recording");
      recordButton.setAttribute("aria-label", "Gravar áudio");
      status.textContent = `Áudio pronto: ${file.name}`;
      contentPreview.render();
    }

    function stopStream() {
      if (recorderBox) {
        recorderBox.classList.remove("recording");
      }
      if (stream) {
        stream.getTracks().forEach((track) => track.stop());
        stream = null;
      }
    }
  }

  function preferredAudioType() {
    const candidates = [
      "audio/ogg;codecs=opus",
      "audio/webm;codecs=opus",
      "audio/webm"
    ];
    return candidates.find((type) => MediaRecorder.isTypeSupported(type)) || "";
  }

  function audioExtension(type) {
    if (type.includes("ogg")) {
      return "ogg";
    }
    if (type.includes("mp4")) {
      return "m4a";
    }
    if (type.includes("mpeg")) {
      return "mp3";
    }
    if (type.includes("wav")) {
      return "wav";
    }
    return "webm";
  }

  function assignFile(input, file) {
    const transfer = new DataTransfer();
    transfer.items.add(file);
    input.files = transfer.files;
  }

  function clearFile(input) {
    if (input) {
      input.value = "";
    }
  }

  function showFormMessage(responseForm, message) {
    let box = responseForm.querySelector("[data-form-message]");
    if (!box) {
      box = document.createElement("p");
      box.className = "form-message";
      box.setAttribute("data-form-message", "");
      responseForm.prepend(box);
    }
    box.textContent = message;
  }

  function escapeHtml(value) {
    return value.replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;"
    }[char]));
  }
})();
