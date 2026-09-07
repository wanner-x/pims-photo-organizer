export const el = (id) => document.getElementById(id);

export const fmt = (value) => new Intl.NumberFormat("zh-CN").format(value ?? 0);

export const setStatus = (message) => { el("status").textContent = message; };

export const withButtonLoading = async (button, loadingText, work) => {
  if (!button || button.disabled) return;
  const originalText = button.textContent;
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  button.textContent = loadingText;
  try {
    return await work();
  } finally {
    button.textContent = originalText;
    button.removeAttribute("aria-busy");
    button.disabled = false;
  }
};
