"""BPMN subset compiler, Provop-inspired transformations and bounded token analysis."""

import copy, re, time, xml.etree.ElementTree as ET

B = "http://www.omg.org/spec/BPMN/20100524/MODEL"
D = "http://www.omg.org/spec/BPMN/20100524/DI"
C = "http://www.omg.org/spec/DD/20100524/DC"
I = "http://www.omg.org/spec/DD/20100524/DI"
for prefix, uri in [("bpmn", B), ("bpmndi", D), ("dc", C), ("di", I)]:
    ET.register_namespace(prefix, uri)
ACTIVITIES = {
    "task",
    "userTask",
    "serviceTask",
    "manualTask",
    "businessRuleTask",
    "sendTask",
    "receiveTask",
}
TYPES = ACTIVITIES | {"startEvent", "endEvent", "exclusiveGateway", "parallelGateway"}


def compile_process(text):
    if not isinstance(text, str) or len(text) > 30000:
        raise ValueError("Description must be text up to 30,000 characters")
    lines = [
        x.strip()
        for x in text.splitlines()
        if x.strip() and not x.strip().startswith("#")
    ]
    if not lines:
        raise ValueError("Enter at least one activity")
    if len(lines) > 150:
        raise ValueError("Maximum 150 lines")
    nodes = []
    edges = []

    def node(kind, name=""):
        n = {"id": f"N{len(nodes)+1}", "type": kind, "name": name}
        nodes.append(n)
        return n["id"]

    def link(a, b, label=""):
        edges.append(
            {"id": f"F{len(edges)+1}", "source": a, "target": b, "name": label}
        )

    start = node("startEvent", "Start")

    def block(i, prev, stops):
        while i < len(lines) and lines[i].lower() not in stops:
            line = lines[i]
            low = line.lower()
            if low.startswith("if "):
                split = node("exclusiveGateway", line[3:].rstrip(":"))
                link(prev, split)
                i, a = block(i + 1, split, {"else", "endif"})
                if i >= len(lines):
                    raise ValueError("IF needs ELSE and ENDIF")
                if lines[i].lower() != "else":
                    raise ValueError("IF needs an ELSE branch")
                first = [e for e in edges if e["source"] == split]
                if not first:
                    raise ValueError("Empty IF branch")
                first[0]["name"] = "Yes"
                i, b = block(i + 1, split, {"endif"})
                if i >= len(lines):
                    raise ValueError("Missing ENDIF")
                outgoing = [e for e in edges if e["source"] == split]
                if len(outgoing) != 2:
                    raise ValueError("Both IF branches need activities")
                outgoing[1]["name"] = "No"
                join = node("exclusiveGateway")
                link(a, join)
                link(b, join)
                prev = join
            elif low == "parallel":
                split = node("parallelGateway")
                link(prev, split)
                ends = []
                while True:
                    i, end = block(i + 1, split, {"branch", "endparallel"})
                    if i >= len(lines):
                        raise ValueError("Missing ENDPARALLEL")
                    if end == split:
                        raise ValueError("Empty parallel branch")
                    ends.append(end)
                    if lines[i].lower() == "endparallel":
                        break
                if len(ends) < 2:
                    raise ValueError(
                        "PARALLEL needs at least two branches separated by BRANCH"
                    )
                join = node("parallelGateway")
                for end in ends:
                    link(end, join)
                prev = join
            elif low in {"else", "endif", "branch", "endparallel"}:
                raise ValueError(f"Unexpected {line}")
            else:
                kind = "task"
                name = line
                role = None
                match = re.match(
                    r"^(task|user|service|manual|rule|send|receive)(?:\[([^\]]+)\])?:\s*(.*)$",
                    line,
                    re.I,
                )
                if match:
                    kinds = {
                        "task": "task",
                        "user": "userTask",
                        "service": "serviceTask",
                        "manual": "manualTask",
                        "rule": "businessRuleTask",
                        "send": "sendTask",
                        "receive": "receiveTask",
                    }
                    kind = kinds[match[1].lower()]
                    role = match[2]
                    name = match[3].strip()
                if not name or len(name) > 200:
                    raise ValueError(
                        f"Line {i+1}: activity names require 1–200 characters"
                    )
                n = node(kind, name)
                if role:
                    nodes[-1]["role"] = role.strip()
                link(prev, n)
                prev = n
            i += 1
        return i, prev

    _, last = block(0, start, set())
    end = node("endEvent", "End")
    link(last, end)
    if any(n.get("role") for n in nodes):
        for n in nodes:
            n.setdefault("role", "Coordination")
    return {"nodes": nodes, "edges": edges}


def validate(g):
    invalid = {
        "valid": False,
        "errors": ["Graph requires arrays of nodes and edges with valid text fields"],
        "warnings": [],
    }
    if (
        not isinstance(g, dict)
        or not isinstance(g.get("nodes"), list)
        or not isinstance(g.get("edges"), list)
    ):
        return invalid
    for n in g["nodes"]:
        if (
            not isinstance(n, dict)
            or any(not isinstance(n.get(k), str) for k in ("id", "type"))
            or not isinstance(n.get("name", ""), str)
        ):
            return invalid
        if (
            len(n.get("name", "")) > 200
            or not isinstance(n.get("description", ""), str)
            or len(n.get("description", "")) > 4000
            or not isinstance(n.get("role", ""), str)
            or len(n.get("role", "")) > 100
        ):
            return invalid
    for e in g["edges"]:
        if (
            not isinstance(e, dict)
            or any(not isinstance(e.get(k), str) for k in ("id", "source", "target"))
            or not isinstance(e.get("name", ""), str)
        ):
            return invalid
    ns = g.get("nodes", [])
    es = g.get("edges", [])
    ids = [n["id"] for n in ns]
    errors = []
    if any(len(i) > 200 for i in ids):
        return invalid
    if not ns or len(ns) > 250 or len(es) > 600:
        return {
            "valid": False,
            "errors": ["Model must have 1–250 nodes and at most 600 flows"],
            "warnings": [],
        }
    if len(set(ids)) != len(ids):
        errors.append("Duplicate node IDs")
    if len({e["id"] for e in es}) != len(es):
        errors.append("Duplicate flow IDs")
    if set(ids) & {e["id"] for e in es}:
        errors.append("Node and flow IDs collide")
    for n in ns:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", n["id"]):
            errors.append("Invalid XML ID: " + n["id"])
        if n["type"] not in TYPES:
            errors.append("Unsupported element: " + n["type"])
    inc = {i: [] for i in ids}
    out = {i: [] for i in ids}
    for e in es:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", e["id"]):
            errors.append("Invalid flow ID: " + e["id"])
        if e["source"] not in out or e["target"] not in inc:
            errors.append("Dangling flow: " + e["id"])
            continue
        out[e["source"]].append(e["target"])
        inc[e["target"]].append(e["source"])
    starts = [n["id"] for n in ns if n["type"] == "startEvent"]
    ends = [n["id"] for n in ns if n["type"] == "endEvent"]
    if len(starts) != 1 or len(ends) != 1:
        errors.append("Exactly one start and one end required")

    def reach(seeds, adj):
        seen = set(seeds)
        todo = list(seeds)
        while todo:
            for v in adj[todo.pop()]:
                if v not in seen:
                    seen.add(v)
                    todo.append(v)
        return seen

    if set(ids) - reach(starts, out):
        errors.append("Unreachable nodes exist")
    if set(ids) - reach(ends, inc):
        errors.append("Some nodes cannot reach the end")
    degree = {i: len(inc[i]) for i in ids}
    todo = [i for i in ids if degree[i] == 0]
    count = 0
    while todo:
        v = todo.pop()
        count += 1
        for w in out[v]:
            degree[w] -= 1
            if degree[w] == 0:
                todo.append(w)
    if count != len(ns):
        errors.append("Cycles are outside the supported analysis subset")
    for n in ns:
        i = n["id"]
        a = len(inc[i])
        b = len(out[i])
        t = n["type"]
        if t == "startEvent" and (a or b != 1):
            errors.append("Start requires zero incoming and one outgoing")
        elif t == "endEvent" and (a != 1 or b):
            errors.append("End requires one incoming and zero outgoing")
        elif t.endswith("Task") or t == "task":
            if a != 1 or b != 1:
                errors.append(f"Task {i} requires one incoming and one outgoing")
        elif t.endswith("Gateway"):
            if not ((a == 1 and b >= 2) or (a >= 2 and b == 1)):
                errors.append(f"Gateway {i} must split or join")
    return {
        "valid": not errors,
        "errors": list(dict.fromkeys(errors)),
        "warnings": [
            "Analysis supports acyclic single-process models; this is not full BPMN conformance certification."
        ],
    }


def xml(g, title="Process"):
    check = validate(g)
    if not check["valid"]:
        raise ValueError("; ".join(check["errors"]))
    used = {n["id"] for n in g["nodes"]} | {e["id"] for e in g["edges"]}

    def unique(candidate):
        value = candidate
        suffix = 1
        while value in used:
            suffix += 1
            value = f"{candidate}_{suffix}"
        used.add(value)
        return value

    process_id = unique("Process_1")
    root = ET.Element(
        f"{{{B}}}definitions",
        {
            "id": unique("Definitions_1"),
            "targetNamespace": "https://process-studio.local",
        },
    )
    proc = ET.SubElement(
        root,
        f"{{{B}}}process",
        {"id": process_id, "name": title, "isExecutable": "false"},
    )
    ns = g["nodes"]
    es = g["edges"]
    inc = {n["id"]: [] for n in ns}
    out = {n["id"]: [] for n in ns}
    for e in es:
        inc[e["target"]].append(e)
        out[e["source"]].append(e)
    role_names = list(dict.fromkeys(n.get("role") for n in ns if n.get("role")))
    lane_ids = {role: unique(f"StudioLane_{i+1}") for i, role in enumerate(role_names)}
    if role_names:
        lanes = ET.SubElement(proc, f"{{{B}}}laneSet", {"id": unique("StudioLaneSet")})
        for index, role in enumerate(role_names):
            lane = ET.SubElement(
                lanes, f"{{{B}}}lane", {"id": lane_ids[role], "name": role}
            )
            for n in ns:
                if n.get("role") == role:
                    ET.SubElement(lane, f"{{{B}}}flowNodeRef").text = n["id"]
    for n in ns:
        el = ET.SubElement(
            proc, f"{{{B}}}{n['type']}", {"id": n["id"], "name": n.get("name", "")}
        )
        if n.get("description"):
            ET.SubElement(el, f"{{{B}}}documentation").text = n["description"]
        for tag, items in [("incoming", inc[n["id"]]), ("outgoing", out[n["id"]])]:
            for e in items:
                ET.SubElement(el, f"{{{B}}}{tag}").text = e["id"]
    for e in es:
        ET.SubElement(
            proc,
            f"{{{B}}}sequenceFlow",
            {
                "id": e["id"],
                "sourceRef": e["source"],
                "targetRef": e["target"],
                "name": e.get("name", ""),
            },
        )
    diagram = ET.SubElement(root, f"{{{D}}}BPMNDiagram", {"id": unique("Diagram_1")})
    plane = ET.SubElement(
        diagram,
        f"{{{D}}}BPMNPlane",
        {"id": unique("Plane_1"), "bpmnElement": process_id},
    )
    rank = {}
    pending = list(ns)
    while pending:
        for n in pending[:]:
            if all(e["source"] in rank for e in inc[n["id"]]):
                rank[n["id"]] = max(
                    [rank[e["source"]] + 1 for e in inc[n["id"]]] or [0]
                )
                pending.remove(n)
    levels = {}
    pos = {}
    for n in ns:
        levels.setdefault(rank[n["id"]], []).append(n)
    rows = max(map(len, levels.values()))
    role_offsets = {}
    role_heights = {}
    if role_names:
        top = 70
        for role in role_names:
            maximum = max(
                sum(n.get("role") == role for n in items) for items in levels.values()
            )
            height = max(180, maximum * 140 + 60)
            role_offsets[role] = top
            role_heights[role] = height
            top += height
        for index, role in enumerate(role_names):
            sh = ET.SubElement(
                plane,
                f"{{{D}}}BPMNShape",
                {
                    "id": unique(lane_ids[role] + "_di"),
                    "bpmnElement": lane_ids[role],
                    "isHorizontal": "true",
                },
            )
            ET.SubElement(
                sh,
                f"{{{C}}}Bounds",
                dict(
                    x="40",
                    y=str(role_offsets[role]),
                    width=str((max(rank.values()) + 1) * 210 + 130),
                    height=str(role_heights[role]),
                ),
            )
    for level, items in levels.items():
        role_slots = {}
        for j, n in enumerate(items):
            gateway = n["type"].endswith("Gateway")
            event = n["type"].endswith("Event")
            w, h = (50, 50) if gateway else (36, 36) if event else (140, 80)
            x = 110 + level * 210
            y = 100 + (j - (len(items) - 1) / 2) * 160 + rows * 80
            if role_names:
                role = n.get("role", role_names[0])
                slot = role_slots.get(role, 0)
                role_slots[role] = slot + 1
                y = role_offsets[role] + 60 + slot * 140
            pos[n["id"]] = (x, y, w, h)
            sh = ET.SubElement(
                plane,
                f"{{{D}}}BPMNShape",
                {"id": unique(n["id"] + "_di"), "bpmnElement": n["id"]},
            )
            ET.SubElement(
                sh,
                f"{{{C}}}Bounds",
                dict(x=str(x), y=str(y), width=str(w), height=str(h)),
            )
            if (gateway or event) and n.get("name"):
                label = ET.SubElement(sh, f"{{{D}}}BPMNLabel")
                ET.SubElement(
                    label,
                    f"{{{C}}}Bounds",
                    dict(
                        x=str(x + w / 2 - 65),
                        y=str(y + h + 8),
                        width="130",
                        height="42",
                    ),
                )
    for e in es:
        a, b = pos[e["source"]], pos[e["target"]]
        x1, y1 = a[0] + a[2], a[1] + a[3] / 2
        x2, y2 = b[0], b[1] + b[3] / 2
        ed = ET.SubElement(
            plane,
            f"{{{D}}}BPMNEdge",
            {"id": unique(e["id"] + "_di"), "bpmnElement": e["id"]},
        )
        points = (
            [(x1, y1), ((x1 + x2) / 2, y1), ((x1 + x2) / 2, y2), (x2, y2)]
            if y1 != y2
            else [(x1, y1), (x2, y2)]
        )
        for x, y in points:
            ET.SubElement(ed, f"{{{I}}}waypoint", {"x": str(x), "y": str(y)})
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def parse_xml(source):
    if not isinstance(source, str):
        raise ValueError("BPMN XML must be text")
    if "<!DOCTYPE" in source.upper() or "<!ENTITY" in source.upper():
        raise ValueError("DTD/entities are forbidden")
    if not isinstance(source, str) or len(source) > 2_000_000:
        raise ValueError("BPMN XML must be text up to 2 MB")
    root = ET.fromstring(source)
    if root.tag != f"{{{B}}}definitions":
        raise ValueError("Expected BPMN 2.0 definitions namespace")
    all_ids = [el.get("id") for el in root.iter() if el.get("id")]
    if len(all_ids) != len(set(all_ids)):
        raise ValueError("Duplicate IDs in BPMN document")
    procs = root.findall(f"{{{B}}}process")
    if len(procs) != 1 or root.find(f"{{{B}}}collaboration") is not None:
        raise ValueError("Import requires one process without pools/collaboration")
    if procs[0].get("isExecutable") == "true":
        raise ValueError(
            "Executable BPMN imports are outside this modeling application's supported subset"
        )
    nodes = []
    edges = []
    roles = {}
    for lane in procs[0].iter(f"{{{B}}}lane"):
        for ref in lane.findall(f"{{{B}}}flowNodeRef"):
            if ref.text in roles:
                raise ValueError("A node cannot belong to multiple lanes")
            roles[ref.text] = lane.get("name") or lane.get("id")
    for child in procs[0].iter():
        local = child.tag.split("}")[-1]
        if not child.tag.startswith("{" + B + "}"):
            raise ValueError(
                "Foreign XML elements in process semantics are unsupported"
            )
        for key, value in child.attrib.items():
            if key.startswith("{") and not key.startswith(
                "{http://www.w3.org/2001/XMLSchema-instance}"
            ):
                raise ValueError(
                    "Vendor execution attributes are outside the supported subset"
                )
            if key in {
                "implementation",
                "isForCompensation",
                "startQuantity",
                "completionQuantity",
            } and value not in {"##unspecified", "false", "1"}:
                raise ValueError("Unsupported executable activity semantics: " + key)
        if local == "childLaneSet":
            raise ValueError("Nested lanes are outside the supported subset")
        if local.endswith("EventDefinition") or local in {
            "conditionExpression",
            "multiInstanceLoopCharacteristics",
            "standardLoopCharacteristics",
        }:
            raise ValueError("Unsupported BPMN semantics: " + local)
        if local == "extensionElements" and len(child):
            raise ValueError(
                "Executable/vendor extensions are outside the supported subset"
            )
        if child.get("default") is not None:
            raise ValueError(
                "Default/conditional flows are outside the supported subset"
            )
    for el in procs[0]:
        t = el.tag.split("}")[-1]
        if t == "sequenceFlow":
            edges.append(
                {
                    "id": el.attrib["id"],
                    "source": el.attrib["sourceRef"],
                    "target": el.attrib["targetRef"],
                    "name": el.get("name", ""),
                }
            )
        elif t in TYPES:
            n = {"id": el.attrib["id"], "type": t, "name": el.get("name", "")}
            if n["id"] in roles:
                n["role"] = roles[n["id"]]
            doc = el.find(f"{{{B}}}documentation")
            if doc is not None and doc.text:
                n["description"] = doc.text
            allowed = {"incoming", "outgoing", "documentation", "extensionElements"}
            for child in el:
                if child.tag.split("}")[-1] not in allowed:
                    raise ValueError(
                        "Unsupported activity/event detail: " + child.tag.split("}")[-1]
                    )
            nodes.append(n)
        elif t not in {"documentation", "extensionElements", "laneSet"}:
            raise ValueError("Unsupported BPMN element: " + t)
    g = {"nodes": nodes, "edges": edges}
    result = validate(g)
    if not result["valid"]:
        raise ValueError("; ".join(result["errors"]))
    return g


def derive(base, operations):
    from validation import operations_value

    operations = operations_value(operations)
    check = validate(base)
    if not check["valid"]:
        raise ValueError("Invalid base graph: " + "; ".join(check["errors"]))
    g = copy.deepcopy(base)
    for index, op in enumerate(operations):
        nodes = {n["id"]: n for n in g["nodes"]}
        target = op.get("target")
        action = op.get("action")
        if target not in nodes:
            raise ValueError(f"Operation {index+1}: missing target {target}")
        n = nodes[target]
        if action == "modify":
            if not op.get("name", "").strip():
                raise ValueError("MODIFY needs a name")
            n["name"] = op["name"]
        elif action in {"delete", "move"}:
            if n["type"] not in ACTIVITIES:
                raise ValueError("Only activities may be deleted/moved")
            incoming = [e for e in g["edges"] if e["target"] == target]
            outgoing = [e for e in g["edges"] if e["source"] == target]
            if len(incoming) != 1 or len(outgoing) != 1:
                raise ValueError("Activity must have one incoming and outgoing")
            incoming[0]["target"] = outgoing[0]["target"]
            g["edges"].remove(outgoing[0])
            g["nodes"].remove(n)
            if action == "move":
                after = op.get("after")
                if after == target or after not in nodes:
                    raise ValueError("Invalid MOVE destination")
                candidates = [e for e in g["edges"] if e["source"] == after]
                if len(candidates) != 1:
                    raise ValueError("MOVE destination needs exactly one outgoing flow")
                edge = candidates[0]
                dest = edge["target"]
                edge["target"] = target
                g["nodes"].append(n)
                g["edges"].append(
                    {
                        "id": outgoing[0]["id"],
                        "source": target,
                        "target": dest,
                        "name": "",
                    }
                )
        elif action == "insert":
            candidates = [e for e in g["edges"] if e["source"] == target]
            if len(candidates) != 1:
                raise ValueError("INSERT target needs one outgoing flow")
            if not op.get("name", "").strip():
                raise ValueError("INSERT needs a name")
            suffix = op.get("id", str(index + 1))
            nid = f"Option_{suffix}"
            eid = f"OptionFlow_{suffix}"
            if nid in nodes or any(e["id"] == eid for e in g["edges"]):
                raise ValueError("Generated option ID collision")
            edge = candidates[0]
            dest = edge["target"]
            edge["target"] = nid
            new_node = {
                "id": nid,
                "type": op.get("type", "userTask"),
                "name": op["name"],
            }
            if op.get("role"):
                new_node["role"] = op["role"]
            elif n.get("role"):
                new_node["role"] = n["role"]
            g["nodes"].append(new_node)
            g["edges"].append({"id": eid, "source": nid, "target": dest, "name": ""})
        else:
            raise ValueError("Unknown operation: " + str(action))
    result = validate(g)
    if not result["valid"]:
        raise ValueError("; ".join(result["errors"]))
    return g


def analyze(g, limit=10000, timeout=3.0):
    check = validate(g)
    if not check["valid"]:
        return dict(check, sound=False, complete=False)
    es = g["edges"]
    ns = {n["id"]: n for n in g["nodes"]}
    inc = {i: [] for i in ns}
    out = {i: [] for i in ns}
    for j, e in enumerate(es):
        inc[e["target"]].append(j)
        out[e["source"]].append(j)
    start = next(i for i in ns if ns[i]["type"] == "startEvent")
    initial = [0] * len(es)
    initial[out[start][0]] = 1
    queue = [(tuple(initial), 0)]
    seen = set(queue)
    dead = []
    finals = 0
    fired = set()
    predecessor = {queue[0]: None}
    deadline = time.monotonic() + timeout
    reason = None
    witness = None
    while queue:
        if len(seen) >= limit or time.monotonic() > deadline:
            reason = (
                "State limit reached" if len(seen) >= limit else "Time limit reached"
            )
            break
        state, ended = queue.pop()
        enabled = []
        for i, n in ns.items():
            incoming = inc[i]
            if not incoming:
                continue
            parallel = n["type"] == "parallelGateway"
            choices = (
                [incoming]
                if parallel and all(state[k] for k in incoming)
                else [] if parallel else [[k] for k in incoming if state[k]]
            )
            for consumed in choices:
                produced = (
                    [[k] for k in out[i]]
                    if n["type"] == "exclusiveGateway"
                    else [out[i]]
                )
                for add in produced:
                    enabled.append((i, consumed, add))
        if not enabled:
            if ended == 1 and not any(state):
                finals += 1
            else:
                dead.append({"tokens": list(state), "completed": ended})
                if witness is None:
                    witness = (state, ended)
        for i, consumed, add in enabled:
            fired.add(i)
            s = list(state)
            for k in consumed:
                s[k] -= 1
            for k in add:
                s[k] += 1
            nxt = (tuple(s), ended + (ns[i]["type"] == "endEvent"))
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
                predecessor[nxt] = ((state, ended), i)
                if len(seen) >= limit:
                    break
    complete = not queue
    sound = complete and not dead and finals > 0 and len(fired) == len(ns) - 1
    trace = []
    while witness is not None and predecessor[witness] is not None:
        previous, node_id = predecessor[witness]
        trace.append({"id": node_id, "name": ns[node_id].get("name") or node_id})
        witness = previous
    trace.reverse()
    return dict(
        check,
        reason=reason,
        counterexample=trace,
        sound=sound,
        complete=complete,
        states=len(seen),
        deadlocks=len(dead),
        terminalStates=finals,
        unfired=[i for i in ns if i != start and i not in fired],
    )


def source_traceability(graph, source):
    """Map compiled activity names back to their exact source lines, in lexical order."""
    lines = []
    offset = 0
    for raw in source.splitlines(keepends=True):
        stripped = raw.strip()
        match = re.match(
            r"^(?:task|user|service|manual|rule|send|receive)(?:\[[^\]]+\])?:\s*(.*)$",
            stripped,
            re.I,
        )
        name = match[1] if match else stripped
        if (
            stripped.lower()
            not in {"parallel", "branch", "endparallel", "else", "endif"}
            and not stripped.lower().startswith("if ")
            and not stripped.startswith("#")
        ):
            position = raw.find(name)
            lines.append((name, offset + position))
        offset += len(raw)
    records = []
    cursor = 0
    for node in graph["nodes"]:
        if node["type"] not in ACTIVITIES:
            continue
        for i in range(cursor, len(lines)):
            name, start = lines[i]
            if name == node["name"]:
                records.append(
                    {
                        "id": node["id"],
                        "name": name,
                        "type": node["type"],
                        "quote": name,
                        "start": start,
                        "end": start + len(name),
                    }
                )
                cursor = i + 1
                break
    return records
