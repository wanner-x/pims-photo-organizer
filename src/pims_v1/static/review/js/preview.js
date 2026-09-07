import { el } from "./dom.js";

export const videoExts = new Set([".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"]);
export const imageExts = new Set([".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"]);

export const makePreview = (asset) => {
  const ext = (asset.file_ext || "").toLowerCase();
  if (videoExts.has(ext)) {
    const video = document.createElement("video");
    video.className = "preview";
    video.src = asset.media_url;
    video.muted = true;
    video.playsInline = true;
    video.preload = "metadata";
    video.addEventListener("click", (event) => {
      event.preventDefault();
      video.pause();
      openPreview(asset);
    });
    return video;
  }
  const img = document.createElement("img");
  img.className = "preview";
  img.alt = asset.file_name || "媒体预览";
  img.src = imageExts.has(ext) ? asset.thumbnail_url : "";
  img.onerror = () => {
    if (imageExts.has(ext) && img.src !== asset.media_url) img.src = asset.media_url;
    else img.style.visibility = "hidden";
  };
  img.addEventListener("click", () => openPreview(asset));
  return img;
};

export const pauseInlinePreviews = () => {
  document.querySelectorAll("video.preview").forEach((video) => {
    video.pause();
  });
};

export const openPreview = (asset) => {
  pauseInlinePreviews();
  const modal = el("preview-modal");
  const content = el("preview-modal-content");
  content.replaceChildren();
  const ext = (asset.file_ext || "").toLowerCase();
  if (videoExts.has(ext)) {
    const video = document.createElement("video");
    video.src = asset.media_url;
    video.controls = true;
    video.autoplay = true;
    content.append(video);
  } else {
    const img = document.createElement("img");
    img.alt = asset.file_name || "预览";
    img.src = asset.media_url || asset.thumbnail_url;
    content.append(img);
  }
  modal.classList.add("open");
  modal.setAttribute("aria-hidden", "false");
};

export const closePreview = () => {
  const modal = el("preview-modal");
  el("preview-modal-content").replaceChildren();
  modal.classList.remove("open");
  modal.setAttribute("aria-hidden", "true");
};

export const initPreview = () => {
  el("close-preview").addEventListener("click", closePreview);
  el("preview-modal").addEventListener("click", (event) => {
    if (event.target === el("preview-modal")) closePreview();
  });
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closePreview();
  });
};
