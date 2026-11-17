import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import { BpmnModdle } from "bpmn-moddle";
import { layoutProcess } from "bpmn-auto-layout";
for (const name of ["onboarding", "procurement", "insurance"]) {
  test(`${name} XML resolves semantic and DI references in bpmn-moddle`, async () => {
    const source = await fs.readFile(
      new URL(`../samples/${name}.bpmn`, import.meta.url),
      "utf8",
    );
    const parsed = await new BpmnModdle().fromXML(source);
    assert.equal(parsed.warnings.length, 0, JSON.stringify(parsed.warnings));
    const process = parsed.rootElement.rootElements.find(
      (e) => e.$type === "bpmn:Process",
    );
    const planes = parsed.rootElement.diagrams.flatMap(
      (d) => d.plane.planeElement,
    );
    const visualized = new Set(planes.map((e) => e.bpmnElement?.id));
    for (const element of process.flowElements)
      assert.ok(visualized.has(element.id), `Missing DI: ${element.id}`);
    for (const set of process.laneSets || [])
      for (const lane of set.lanes)
        assert.ok(visualized.has(lane.id), `Missing lane DI: ${lane.id}`);
  });
}
test("official layout preserves every element and sequence flow on an acyclic decision/parallel model", async () => {
  const source = await fs.readFile(
    new URL("../samples/onboarding.bpmn", import.meta.url),
    "utf8",
  );
  const original = await new BpmnModdle().fromXML(source);
  const result = await layoutProcess(source);
  const xml = typeof result === "string" ? result : result.xml;
  const parsed = await new BpmnModdle().fromXML(xml);
  assert.equal(parsed.warnings.length, 0);
  const before = original.rootElement.rootElements.find(
    (e) => e.$type === "bpmn:Process",
  ).flowElements;
  const after = parsed.rootElement.rootElements.find(
    (e) => e.$type === "bpmn:Process",
  ).flowElements;
  assert.deepEqual(
    new Set(after.map((e) => e.id)),
    new Set(before.map((e) => e.id)),
  );
});

import {
  nodeTypes,
  modelerType,
  xmlType,
  supportedModelerTypes,
} from "./bpmn-types.js";
test("editor-supported types match real bpmn-moddle business objects", () => {
  const moddle = new BpmnModdle();
  for (const name of nodeTypes) {
    const object = moddle.create(modelerType(name), { id: "Check" });
    assert.ok(supportedModelerTypes.has(object.$type));
    assert.equal(xmlType(object.$type), name);
  }
});

import { supportedShapeRule } from "./bpmn-types.js";
test("modeling rules accept create and replacement command context shapes without exceptions", () => {
  assert.equal(supportedShapeRule({ shape: { type: "bpmn:Task" } }), undefined);
  assert.equal(
    supportedShapeRule({ newData: { type: "bpmn:ManualTask" } }),
    undefined,
  );
  assert.equal(
    supportedShapeRule({ newData: { type: "bpmn:SubProcess" } }),
    false,
  );
  assert.equal(supportedShapeRule({}), undefined);
});
