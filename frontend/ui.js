export const icons = {
  mark: '<svg viewBox="0 0 28 28" fill="none"><path d="M4 4h8v8H4zM16 16h8v8h-8z" fill="currentColor"/><path d="M12 8h8v8M8 12v8h8" stroke="currentColor" stroke-width="2"/></svg>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  chevron: '<path d="m9 5 7 7-7 7"/>',
  download: '<path d="M12 3v12m-5-5 5 5 5-5M5 16v4h14v-4"/>',
  upload: '<path d="M12 16V4m-5 5 5-5 5 5M5 16v4h14v-4"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  undo: '<path d="m9 4-5 5 5 5M4 9h9a7 7 0 0 1 7 7v4"/>',
  redo: '<path d="m15 4 5 5-5 5m5-5h-9a7 7 0 0 0-7 7v4"/>',
  fit: '<path d="M9 4H4v5m11-5h5v5M4 15v5h5m11-5v5h-5"/>',
  search: '<circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/>',
  model:
    '<rect x="3" y="8" width="7" height="8" rx="2"/><path d="M10 12h4m3-4 4 4-4 4-4-4z"/>',
  branch:
    '<path d="M6 3v13a5 5 0 0 0 5 5h7M6 8h6a6 6 0 0 0 6-6"/><circle cx="6" cy="3" r="1"/><circle cx="18" cy="21" r="1"/>',
  shield: '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6zM8 11l3 3 5-6"/>',
  history: '<path d="M3 10a9 9 0 1 1 1 7M3 4v6h6m3-3v6l4 2"/>',
  play: '<path d="m8 4 12 8-12 8z"/>',
  settings:
    '<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3"/><circle cx="15" cy="17" r="3"/>',
  panel:
    '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M15 4v16"/>',
  compare:
    '<rect x="3" y="5" width="7" height="14" rx="1"/><rect x="14" y="5" width="7" height="14" rx="1"/>',
  warning: '<path d="m12 3 10 18H2zM12 9v5m0 3v1"/>',
  trash: '<path d="M3 6h18M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7m4-7v7"/>',
};
export function icon(name) {
  if (name === "mark") return icons.mark;
  return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] || icons.model}</svg>`;
}
export const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
export function download(name, data, type = "application/json") {
  const href = URL.createObjectURL(new Blob([data], { type }));
  const a = document.createElement("a");
  a.href = href;
  a.download = name.replace(/[<>:"/\\|?*]/g, "_");
  a.click();
  setTimeout(() => URL.revokeObjectURL(href), 1000);
}
export async function api(path, data) {
  const controller = new AbortController();
  const timeout = setTimeout(
    () => controller.abort(),
    path === "generate" ? 250000 : path === "ai/test" ? 125000 : 45000,
  );
  try {
    const response = await fetch("/api/" + path, {
      ...(data === undefined
        ? {}
        : {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data),
          }),
      signal: controller.signal,
    });
    const result = await response.json();
    if (!response.ok) {
      const error = new Error(result.error || "Request failed");
      error.code = result.code;
      error.requestId = result.requestId;
      throw error;
    }
    return result;
  } catch (e) {
    if (e.name === "AbortError")
      throw Error(
        "The request timed out. Reload before retrying a save to avoid duplicates.",
      );
    throw e;
  } finally {
    clearTimeout(timeout);
  }
}
