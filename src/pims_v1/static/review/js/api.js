import { el } from "./dom.js";

export const tokenHeader = () => {
  const token = el("token").value.trim();
  return token ? {"x-pims-api-token": token} : {};
};

export const jsonFetch = async (url, options = {}) => {
  const response = await fetch(url, {
    ...options,
    headers: {...(options.headers || {}), ...(options.auth ? tokenHeader() : {})},
  });
  if (!response.ok) throw new Error(`${response.status} ${await response.text()}`);
  return response.json();
};
