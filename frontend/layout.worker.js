import { layoutProcess } from "bpmn-auto-layout";
self.onmessage = async ({ data }) => {
  try {
    const result = await layoutProcess(data);
    self.postMessage({
      xml: typeof result === "string" ? result : result.xml,
      warnings:
        typeof result === "string"
          ? []
          : result.warnings?.map((w) => w.message) || [],
    });
  } catch (e) {
    self.postMessage({ error: e.message });
  }
};
