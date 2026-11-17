/** Layout is isolated from the UI thread and checked for semantic/DI coverage. */
export async function arrangeXML(xml) {
  const worker = new Worker(new URL("./layout.worker.js", import.meta.url), {
    type: "module",
  });
  try {
    const result = await new Promise((resolve, reject) => {
      const timer = setTimeout(
        () => reject(Error("Layout exceeded 15 seconds")),
        15000,
      );
      worker.onmessage = (e) => {
        clearTimeout(timer);
        e.data.error ? reject(Error(e.data.error)) : resolve(e.data);
      };
      worker.onerror = () => {
        clearTimeout(timer);
        reject(Error("Layout worker failed"));
      };
      worker.postMessage(xml);
    });
    const parser = new DOMParser();
    const before = parser.parseFromString(xml, "application/xml");
    const after = parser.parseFromString(result.xml, "application/xml");
    if (after.querySelector("parsererror"))
      throw Error("Layout returned invalid XML");
    const types = new Set([
      "startEvent",
      "endEvent",
      "task",
      "userTask",
      "serviceTask",
      "manualTask",
      "businessRuleTask",
      "sendTask",
      "receiveTask",
      "exclusiveGateway",
      "parallelGateway",
      "sequenceFlow",
      "lane",
    ]);
    const semantic = [...before.getElementsByTagName("*")]
      .filter((e) => types.has(e.localName))
      .map((e) => e.id);
    const di = new Set(
      [...after.getElementsByTagName("*")]
        .filter((e) => ["BPMNShape", "BPMNEdge"].includes(e.localName))
        .map((e) => e.getAttribute("bpmnElement")),
    );
    if (semantic.some((id) => !di.has(id)))
      throw Error(
        "Layout could not preserve diagram coverage for all elements. Existing geometry was retained.",
      );
    return result.xml;
  } finally {
    worker.terminate();
  }
}
