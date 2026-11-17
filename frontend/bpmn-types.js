/** XML element names and bpmn-moddle type names use different capitalization. */
export const activityTypes = [
  "task",
  "userTask",
  "serviceTask",
  "manualTask",
  "businessRuleTask",
  "sendTask",
  "receiveTask",
];
export const nodeTypes = [
  ...activityTypes,
  "startEvent",
  "endEvent",
  "exclusiveGateway",
  "parallelGateway",
];
export function modelerType(xmlType) {
  return "bpmn:" + xmlType[0].toUpperCase() + xmlType.slice(1);
}
export function xmlType(modelerType) {
  const name = modelerType.replace(/^bpmn:/, "");
  return name[0].toLowerCase() + name.slice(1);
}
export const supportedModelerTypes = new Set(nodeTypes.map(modelerType));

export function supportedShapeRule(context = {}) {
  const shape = context.newData || context.newShape || context.shape;
  if (!shape?.type) return undefined;
  return supportedModelerTypes.has(shape.type) ? undefined : false;
}
