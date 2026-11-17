import test from "node:test";
import assert from "node:assert/strict";
import {
  createSimulation,
  enabledSteps,
  advance,
  completed,
} from "./simulation.js";
const nodes = [
  { id: "S", type: "startEvent" },
  { id: "P", type: "parallelGateway" },
  { id: "A", type: "userTask", name: "Review A" },
  { id: "B", type: "serviceTask", name: "Review B" },
  { id: "J", type: "parallelGateway" },
  { id: "E", type: "endEvent" },
];
const pairs = [
  ["S", "P"],
  ["P", "A"],
  ["P", "B"],
  ["A", "J"],
  ["B", "J"],
  ["J", "E"],
];
const graph = {
  nodes,
  edges: pairs.map(([source, target], i) => ({ id: "F" + i, source, target })),
};
test("parallel join waits for both branches in either completion order", () => {
  for (const order of [
    ["A", "B"],
    ["B", "A"],
  ]) {
    const state = createSimulation(graph);
    advance(state, enabledSteps(state)[0]);
    assert.deepEqual(
      enabledSteps(state)
        .map((s) => s.node.id)
        .sort(),
      ["A", "B"],
    );
    advance(
      state,
      enabledSteps(state).find((s) => s.node.id === order[0]),
    );
    assert.equal(
      enabledSteps(state).some((s) => s.node.id === "J"),
      false,
    );
    advance(
      state,
      enabledSteps(state).find((s) => s.node.id === order[1]),
    );
    advance(state, enabledSteps(state)[0]);
    advance(state, enabledSteps(state)[0]);
    assert.equal(completed(state), true);
  }
});
test("token multiplicity is preserved, not collapsed into a set", () => {
  const state = createSimulation(graph);
  state.tokens.set("F0", 2);
  advance(state, enabledSteps(state)[0]);
  assert.equal(state.tokens.get("F0"), 1);
  assert.equal(state.tokens.get("F1"), 1);
});
test("disabled stale actions cannot fire twice", () => {
  const state = createSimulation(graph);
  const step = enabledSteps(state)[0];
  advance(state, step);
  assert.throws(() => advance(state, step), /no longer enabled/);
});
test("exclusive choices create one branch token", () => {
  const g = structuredClone(graph);
  g.nodes[1].type = "exclusiveGateway";
  g.nodes[4].type = "exclusiveGateway";
  const state = createSimulation(g);
  assert.equal(enabledSteps(state).length, 2);
  advance(state, enabledSteps(state)[0]);
  assert.equal(enabledSteps(state).length, 1);
  assert.equal(enabledSteps(state)[0].node.id, "A");
});
