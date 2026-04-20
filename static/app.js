const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('fileInput');
const selectedFile = document.getElementById('selectedFile');
const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const runtimeModeSelect = document.getElementById('runtimeMode');
const runtimeInfo = document.getElementById('runtimeInfo');
const statusEl = document.getElementById('status');
const preview = document.getElementById('preview');
const downloadBtn = document.getElementById('downloadBtn');
const saveToFolderBtn = document.getElementById('saveToFolderBtn');
const pickFolderBtn = document.getElementById('pickFolderBtn');
const folderInfo = document.getElementById('folderInfo');
const resultCard = document.getElementById('resultCard');
const resultSummary = document.getElementById('resultSummary');
const saveLocation = document.getElementById('saveLocation');

let selected = null;
let lastResult = null;
let chosenDirHandle = null;
let currentJobId = null;
let pollTimer = null;
let capabilities = null;
const defaultTitle = document.title;

function setDocumentState(label) {
  document.title = label ? `${label} | ${defaultTitle}` : defaultTitle;
}

function showStatus(message, type = 'muted') {
  statusEl.textContent = message;
  statusEl.className = `status-banner status-${type}`;
}

function showResult(summary, location) {
  resultSummary.textContent = summary;
  saveLocation.textContent = location;
  resultCard.classList.remove('hidden');
}

function hideResult() {
  resultCard.classList.add('hidden');
  resultSummary.textContent = '';
  saveLocation.textContent = '';
}

function setFile(file) {
  selected = file;
  if (!file) {
    selectedFile.classList.add('hidden');
    selectedFile.textContent = '';
    return;
  }

  selectedFile.classList.remove('hidden');
  selectedFile.innerHTML = `<strong>Valittu tiedosto:</strong> ${file.name} (${(file.size / 1024 / 1024).toFixed(1)} MB)`;
}

function formatDuration(seconds) {
  const totalSeconds = Math.max(0, Math.round(seconds ?? 0));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const secs = totalSeconds % 60;

  if (hours > 0) {
    const parts = [`${hours} h`, `${minutes} min`];
    if (secs > 0) {
      parts.push(`${secs} s`);
    }
    return parts.join(' ');
  }

  if (minutes > 0) {
    return secs > 0 ? `${minutes} min ${secs} s` : `${minutes} min`;
  }

  return `${secs} s`;
}

function buildSummary(data) {
  const parts = [];
  const mediaDurationSeconds = data.media_duration_seconds ?? data.duration;

  if (data.runtime_label) {
    parts.push(`Suoritustila: ${data.runtime_label}`);
  }
  if (data.language) {
    parts.push(`kieli: ${data.language}`);
  }
  if (typeof mediaDurationSeconds === 'number') {
    parts.push(`tiedoston pituus: ${formatDuration(mediaDurationSeconds)}`);
  }
  if (typeof data.processing_time_seconds === 'number') {
    parts.push(`kasittelyaika: ${formatDuration(data.processing_time_seconds)}`);
  }
  parts.push(`segmentteja: ${data.segment_count}`);

  return `${parts.join(', ')}.`;
}

function resetPolling() {
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}

function setBusyState(isBusy) {
  startBtn.disabled = isBusy;
  stopBtn.disabled = !isBusy;
  pickFolderBtn.disabled = isBusy;
  fileInput.disabled = isBusy;
  runtimeModeSelect.disabled = isBusy;
  downloadBtn.disabled = isBusy || !lastResult;
  saveToFolderBtn.disabled = isBusy || !lastResult || !chosenDirHandle;
}

function applyCapabilities(data) {
  capabilities = data;
  const gpuOption = runtimeModeSelect.querySelector('option[value="gpu"]');

  if (data.cuda_available) {
    gpuOption.disabled = false;
    runtimeInfo.textContent = `CUDA havaittu (${data.cuda_device_count} laite/tta). Auto voi kayttaa GPU:ta.`;
    return;
  }

  if (runtimeModeSelect.value === 'gpu') {
    runtimeModeSelect.value = data.default_runtime_mode || 'auto';
  }
  gpuOption.disabled = true;
  runtimeInfo.textContent = 'CUDA-GPU:ta ei havaittu. Auto kayttaa CPU:ta.';
}

async function loadCapabilities() {
  try {
    const response = await fetch('/capabilities');
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || 'Capabilities fetch failed.');
    }
    applyCapabilities(data);
  } catch (err) {
    runtimeInfo.textContent = 'GPU-ominaisuuksien tarkistus epaonnistui. Voit silti kayttaa Auto- tai CPU-tilaa.';
  }
}

function buildStartMessage() {
  const runtimeMode = runtimeModeSelect.value;
  if (runtimeMode === 'gpu') {
    return 'Transkriptio kaynnissa. GPU-tila voi nopeuttaa kasittelya pitkillakin tiedostoilla.';
  }
  if (runtimeMode === 'cpu') {
    return 'Transkriptio kaynnissa. CPU-kasittely voi kestaa hetken pitkan tiedoston kanssa.';
  }
  if (capabilities?.cuda_available) {
    return 'Transkriptio kaynnissa. Auto yrittaa kayttaa GPU:ta, jos se on vapaana.';
  }
  return 'Transkriptio kaynnissa. Auto kayttaa CPU:ta, koska GPU ei ole saatavilla.';
}

function notifyUser(title, body) {
  if (!('Notification' in window)) {
    return;
  }

  if (Notification.permission === 'granted') {
    new Notification(title, { body });
    return;
  }

  if (Notification.permission !== 'denied') {
    Notification.requestPermission().then((permission) => {
      if (permission === 'granted') {
        new Notification(title, { body });
      }
    }).catch(() => {});
  }
}

function buildDownloadBlob() {
  if (!lastResult) {
    return null;
  }
  return new Blob([lastResult.content], { type: 'text/plain;charset=utf-8' });
}

function triggerBrowserDownload() {
  const blob = buildDownloadBlob();
  if (!blob) return;

  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = lastResult.filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);

  showResult(buildSummary(lastResult), `Tiedosto lahetettiin selaimen latauskansioon nimella ${lastResult.filename}.`);
  showStatus('Valmis. Tiedosto ladattiin selaimen kautta.', 'success');
}

async function pollJobStatus() {
  if (!currentJobId) return;

  try {
    const response = await fetch(`/transcribe/status/${currentJobId}`);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || 'Tilakysely epaonnistui.');
    }

    if (data.status === 'queued' || data.status === 'running') {
      showStatus(data.message || 'Transkriptio kaynnissa...', 'muted');
      pollTimer = setTimeout(pollJobStatus, 1000);
      return;
    }

    resetPolling();

    if (data.status === 'completed') {
      lastResult = data.result;
      preview.value = data.result.preview || data.result.content || '';
      const summary = buildSummary(data.result);
      showResult(summary, 'Tiedosto on valmis tallennettavaksi. Valitse tallennustapa alta.');
      showStatus(`Valmis. ${summary}`, 'success');
      setDocumentState('Valmis');
      notifyUser('Transkriptio valmis', `${data.result.filename} on valmis.`);
      currentJobId = null;
      setBusyState(false);
      return;
    }

    if (data.status === 'cancelled') {
      preview.value = '';
      showResult('Kasittely keskeytettiin kayttajan pyynnosta.', 'Tiedostoa ei tallennettu.');
      showStatus('Transkriptio keskeytettiin.', 'error');
      setDocumentState('Keskeytetty');
      currentJobId = null;
      setBusyState(false);
      return;
    }

    throw new Error(data.message || 'Transkriptio epaonnistui.');
  } catch (err) {
    resetPolling();
    currentJobId = null;
    showStatus(`Virhe: ${err.message}`, 'error');
    showResult('Kasittely keskeytyi virheeseen.', 'Tiedostoa ei tallennettu.');
    setDocumentState('Virhe');
    setBusyState(false);
  }
}

dropzone.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', (e) => setFile(e.target.files[0]));

['dragenter', 'dragover'].forEach((eventName) => {
  dropzone.addEventListener(eventName, (e) => {
    e.preventDefault();
    dropzone.classList.add('dragover');
  });
});

['dragleave', 'drop'].forEach((eventName) => {
  dropzone.addEventListener(eventName, (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
  });
});

dropzone.addEventListener('drop', (e) => {
  const file = e.dataTransfer.files[0];
  if (file) setFile(file);
});

pickFolderBtn.addEventListener('click', async () => {
  if (!window.showDirectoryPicker) {
    folderInfo.textContent = 'Tama selain ei tue kansion valintaa. Valmis tiedosto voidaan silti ladata normaalisti latauskansioon.';
    return;
  }

  try {
    chosenDirHandle = await window.showDirectoryPicker();
    folderInfo.textContent = `Valittu kansio: ${chosenDirHandle.name}`;
    if (lastResult) {
      saveToFolderBtn.disabled = false;
    }
  } catch (err) {
    folderInfo.textContent = 'Kansion valinta peruttiin.';
  }
});

startBtn.addEventListener('click', async () => {
  if (!selected) {
    showStatus('Valitse ensin video- tai aanitiedosto.', 'error');
    return;
  }

  const formData = new FormData();
  formData.append('file', selected);
  formData.append('output_format', document.getElementById('format').value);
  formData.append('model_name', document.getElementById('model').value);
  formData.append('runtime_mode', runtimeModeSelect.value);

  preview.value = '';
  lastResult = null;
  hideResult();
  resetPolling();
  currentJobId = null;
  setDocumentState('Kasitellaan');
  showStatus(buildStartMessage(), 'muted');
  setBusyState(true);

  try {
    const response = await fetch('/transcribe/start', { method: 'POST', body: formData });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || 'Tuntematon virhe');
    }

    currentJobId = data.job_id;
    showStatus(data.message || 'Transkriptio kaynnissa. Voit keskeyttaa sen Stop-painikkeella.', 'muted');
    pollTimer = setTimeout(pollJobStatus, 700);
  } catch (err) {
    showStatus(`Virhe: ${err.message}`, 'error');
    showResult('Kasittely keskeytyi virheeseen.', 'Tiedostoa ei tallennettu.');
    setDocumentState('Virhe');
    setBusyState(false);
  }
});

stopBtn.addEventListener('click', async () => {
  if (!currentJobId) return;

  stopBtn.disabled = true;
  showStatus('Keskeytys pyynto lahetetty. Odotetaan palvelimen vahvistusta...', 'muted');

  try {
    const response = await fetch(`/transcribe/cancel/${currentJobId}`, { method: 'POST' });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || 'Keskeytys epaonnistui.');
    }
  } catch (err) {
    showStatus(`Virhe: ${err.message}`, 'error');
    stopBtn.disabled = false;
  }
});

downloadBtn.addEventListener('click', () => {
  if (!lastResult) return;
  triggerBrowserDownload();
  notifyUser('Tiedosto ladattu', `${lastResult.filename} lahetettiin selaimen latauskansioon.`);
});

saveToFolderBtn.addEventListener('click', async () => {
  if (!lastResult || !chosenDirHandle) return;

  try {
    const fileHandle = await chosenDirHandle.getFileHandle(lastResult.filename, { create: true });
    const writable = await fileHandle.createWritable();
    await writable.write(lastResult.content);
    await writable.close();

    showResult(buildSummary(lastResult), `Tiedosto tallennettiin kansioon ${chosenDirHandle.name} nimella ${lastResult.filename}.`);
    showStatus(`Valmis. Tiedosto tallennettiin kansioon ${chosenDirHandle.name}.`, 'success');
    setDocumentState('Tallennettu');
    notifyUser('Tallennus valmis', `${lastResult.filename} tallennettiin kansioon ${chosenDirHandle.name}.`);
  } catch (err) {
    showStatus(`Tallennus epaonnistui: ${err.message}`, 'error');
    showResult(buildSummary(lastResult), 'Tallennus valittuun kansioon epaonnistui.');
    setDocumentState('Virhe');
  }
});

loadCapabilities();
