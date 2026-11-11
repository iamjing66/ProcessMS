/**
 * 上传相关公共能力：文件校验、拖拽选择区、进度条
 * 供 文件管理（上传）与 文件详情（升版）复用
 */
import { ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE } from "./config.js";
import { escapeHtml, formatFileSize } from "./format.js";

/** 校验文件类型与大小，返回中文错误信息（通过返回空字符串） */
export function validateFile(file) {
  if (!file) return "请选择要上传的文件";
  if (file.size === 0) return "不能上传空文件";
  const name = (file.name || "").toLowerCase();
  const dotIndex = name.lastIndexOf(".");
  const ext = dotIndex >= 0 ? name.slice(dotIndex) : "";
  if (!ALLOWED_EXTENSIONS.includes(ext)) {
    return `不支持的文件类型 ${ext || "（无扩展名）"}，支持：${ALLOWED_EXTENSIONS.join(" ")}`;
  }
  if (file.size > MAX_UPLOAD_SIZE) {
    return `文件大小超过限制（最大 ${MAX_UPLOAD_SIZE / 1024 / 1024}MB）`;
  }
  return "";
}

/**
 * 初始化文件选择区（点击/拖拽）
 * @param {HTMLElement} scope 弹窗内容容器
 * @param {object} options { dropId, inputId, selectedId, onSelect(file, error) }
 */
export function setupDropZone(scope, options = {}) {
  const { dropId, inputId, selectedId, onSelect } = options;
  const drop = scope.querySelector(dropId ? "#" + dropId : ".file-drop");
  const input = scope.querySelector(inputId ? "#" + inputId : 'input[type="file"]');
  const selectedBox = scope.querySelector(selectedId ? "#" + selectedId : ".file-selected-slot");
  if (!drop || !input) return { getFile: () => null, clear: () => {} };

  let selectedFile = null;
  const accept = ALLOWED_EXTENSIONS.join(",");
  input.setAttribute("accept", accept);

  function showSelected(file, error) {
    if (!selectedBox) return;
    if (!file) {
      selectedBox.innerHTML = "";
      return;
    }
    if (error) {
      selectedBox.innerHTML = `<div class="file-selected" style="border-color:#ffccc7;background:#fff1f0">
        <svg class="icon" style="color:#f53f3f"><use href="#icon-warning"/></svg>
        <span class="file-name">${escapeHtml(file.name)}</span>
        <span class="file-size" style="color:#f53f3f">${escapeHtml(error)}</span>
      </div>`;
      return;
    }
    selectedBox.innerHTML = `<div class="file-selected">
      <svg class="icon" style="color:#1677ff"><use href="#icon-file"/></svg>
      <span class="file-name" title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</span>
      <span class="file-size">${formatFileSize(file.size)}</span>
    </div>`;
  }

  function acceptFile(file) {
    const error = validateFile(file);
    selectedFile = error ? null : file;
    showSelected(file, error);
    if (typeof onSelect === "function") onSelect(selectedFile, error);
  }

  drop.addEventListener("click", (event) => {
    // 避免 input.click() 冒泡回 drop 造成递归
    if (event.target === input) return;
    input.click();
  });
  input.addEventListener("change", () => {
    if (input.files && input.files[0]) acceptFile(input.files[0]);
  });
  ["dragenter", "dragover"].forEach((eventName) => {
    drop.addEventListener(eventName, (event) => {
      event.preventDefault();
      drop.classList.add("dragover");
    });
  });
  ["dragleave", "drop"].forEach((eventName) => {
    drop.addEventListener(eventName, (event) => {
      event.preventDefault();
      drop.classList.remove("dragover");
    });
  });
  drop.addEventListener("drop", (event) => {
    const file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
    if (file) acceptFile(file);
  });

  return {
    getFile: () => selectedFile,
    clear() {
      selectedFile = null;
      input.value = "";
      showSelected(null);
      if (typeof onSelect === "function") onSelect(null, "");
    },
  };
}

/** 进度条控制 */
export function setupProgress(scope, progressSelector = ".upload-progress") {
  const wrapper = scope.querySelector(progressSelector);
  const bar = wrapper ? wrapper.querySelector(".progress-bar") : null;
  const text = wrapper ? wrapper.querySelector(".progress-text") : null;
  return {
    show() {
      if (wrapper) wrapper.hidden = false;
      if (bar) bar.style.width = "0%";
      if (text) text.textContent = "上传中 0%";
    },
    update(percent) {
      const value = Math.max(0, Math.min(100, Number(percent) || 0));
      if (bar) bar.style.width = value + "%";
      if (text) text.textContent = value >= 100 ? "上传完成，正在处理…" : `上传中 ${value}%`;
    },
    hide() {
      if (wrapper) wrapper.hidden = true;
    },
  };
}
