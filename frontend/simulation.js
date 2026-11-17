/** Pure token semantics; token multiplicity is preserved even on unsafe graphs. */
export function createSimulation(graph) {
  const incoming = new Map(
    graph.nodes.map((n) => [
      n.id,
      graph.edges.filter((e) => e.target === n.id),
    ]),
  );
  const outgoing = new Map(
    graph.nodes.map((n) => [
      n.id,
      graph.edges.filter((e) => e.source === n.id),
    ]),
  );
  const start = graph.nodes.find((n) => n.type === "startEvent");
  if (!start) throw Error("No start event");
  const state = {
    graph,
    tokens: new Map(),
    ended: 0,
    trace: [{ event: "started", at: new Date().toISOString() }],
  };
  outgoing.get(start.id).forEach((e) => state.tokens.set(e.id, 1));
  return state;
}
export function enabledSteps(state) {
  const enabled = [];
  for (const n of state.graph.nodes) {
    const incoming = state.graph.edges.filter((e) => e.target === n.id);
    const outgoing = state.graph.edges.filter((e) => e.source === n.id);
    const active = incoming.filter((e) => (state.tokens.get(e.id) || 0) > 0);
    if (!incoming.length) continue;
    const parallel = n.type === "parallelGateway";
    if (parallel ? active.length !== incoming.length : !active.length) continue;
    const consumed = parallel ? active : [active[0]];
    const options =
      n.type === "exclusiveGateway" && outgoing.length > 1
        ? outgoing.map((e) => [e])
        : [outgoing];
    for (const produced of options)
      enabled.push({
        node: n,
        consumed,
        produced,
        label:
          (n.name || n.id) +
          (options.length > 1
            ? " → " + (produced[0].name || produced[0].target)
            : ""),
      });
  }
  return enabled;
}
export function advance(state, step) {
  const valid = enabledSteps(state).find(
    (s) =>
      s.node.id === step.node.id &&
      s.produced.map((e) => e.id).join() ===
        step.produced.map((e) => e.id).join(),
  );
  if (!valid) throw Error("This step is no longer enabled");
  valid.consumed.forEach((e) =>
    state.tokens.set(e.id, state.tokens.get(e.id) - 1),
  );
  valid.produced.forEach((e) =>
    state.tokens.set(e.id, (state.tokens.get(e.id) || 0) + 1),
  );
  if (valid.node.type === "endEvent") state.ended++;
  state.trace.push({
    event: "completed",
    id: valid.node.id,
    name: valid.label,
    at: new Date().toISOString(),
  });
  return state;
}
export function completed(state) {
  return state.ended === 1 && [...state.tokens.values()].every((n) => n === 0);
}
