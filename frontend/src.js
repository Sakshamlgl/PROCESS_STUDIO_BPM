import Modeler from "bpmn-js/lib/Modeler";
import Viewer from "bpmn-js/lib/NavigatedViewer";
import RuleProvider from "diagram-js/lib/features/rules/RuleProvider";
import {
  activityTypes,
  modelerType,
  xmlType,
  supportedModelerTypes,
  supportedShapeRule,
} from "./bpmn-types.js";
import { api, esc, icon, download } from "./ui.js";
import { arrangeXML } from "./layout.js";
import {
  createSimulation,
  enabledSteps,
  advance,
  completed,
} from "./simulation.js";
import "bpmn-js/dist/assets/diagram-js.css";
import "bpmn-js/dist/assets/bpmn-js.css";
import "bpmn-js/dist/assets/bpmn-font/css/bpmn.css";
import "./style.css";

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const supported = supportedModelerTypes;
class SupportedRules extends RuleProvider {
  init() {
    this.addRule("shape.create", 1500, supportedShapeRule);
    this.addRule("shape.replace", 1500, supportedShapeRule);
  }
}
SupportedRules.$inject = ["eventBus"];
const samples = {
  onboarding: {
    name: "Customer onboarding",
    source:
      "user: Receive application\nservice: Verify identity\nif Application approved?\nparallel\nuser: Prepare contract\nbranch\nservice: Open account\nendparallel\nuser: Welcome customer\nelse\nuser: Explain rejection\nendif\nservice: Archive application",
  },
  procurement: {
    name: "Purchase-to-pay",
    source:
      "user[Requester]: Submit requisition\nuser[Finance]: Approve budget\nparallel\nuser[Procurement]: Evaluate supplier\nbranch\nservice[Operations]: Check stock availability\nendparallel\nuser[Procurement]: Issue purchase order\nuser[Operations]: Confirm receipt\nuser[Finance]: Reconcile invoice\nservice[Finance]: Schedule payment",
  },
  insurance: {
    name: "Insurance claims",
    source:
      "user: Register claim\nservice: Check policy coverage\nif Covered by policy?\nuser: Assess damage\nif Fraud review required?\nuser: Investigate claim\nelse\nservice: Estimate settlement\nendif\nuser: Authorize payment\nelse\nuser: Explain coverage decision\nendif\nservice: Close claim",
  },
};
let family = null,
  selected = null,
  selectedElement = null,
  panel = "inspect",
  dirty = false,
  loading = false,
  busy = false,
  sim = null;
let draftTimer,
  documentEpoch = 0,
  recipe = [],
  context = {},
  baseViewXML = null,
  comparisonViewers = [];
const layoutCache = new Map();
const app = $("#app");
app.innerHTML = `
<aside class="library">
  <a class="wordmark" href="#" aria-label="Process Studio home"><span>${icon("mark")}</span><strong>Process<span>Studio</span></strong><sup>02</sup></a>
  <button class="new-family" id="new" aria-label="Create process family">${icon("plus")}<span>New family</span><kbd>N</kbd></button>
  <div class="library-label"><span>PROCESS LIBRARY</span><span id="familycount">00</span></div>
  <label class="search-field">${icon("search")}<input id="searchfamilies" placeholder="Find a family…" aria-label="Find a family"></label>
  <div id="familylist" class="family-list"></div>
  <div class="library-bottom"><button id="restorebackup">${icon("upload")} Restore backup</button><button id="guide">${icon("model")} Modeling guide</button><div class="connection"><i></i><span id="connection">Local workspace</span><span class="version">v2.0</span></div></div>
</aside>
<main class="studio">
  <header class="project-header"><div class="project-heading"><div class="breadcrumb">WORKSPACE <span>/</span> PROCESS FAMILY</div><div class="title-row"><h1 id="title">Untitled workspace</h1><span id="revision" class="revision-tag">READY</span></div></div><div class="header-actions"><button id="importbpmn" class="quiet" aria-label="Import BPMN">${icon("upload")}<span>Import BPMN</span></button><button id="createfromtext" class="quiet" aria-label="Generate from description">${icon("plus")}<span>From description</span></button><button id="save" class="solid" aria-label="Save base">${icon("check")}<span>Save base</span><kbd>⌘/Ctrl S</kbd></button></div></header>
  <div class="variant-bar"><div class="variant-path">${icon("branch")}<span>FAMILY</span></div><div id="varianttabs" class="variant-tabs"></div><button id="newvariant" class="variant-add" title="Configure a new variant">${icon("plus")} Variant</button></div>
  <div class="workbench"><section class="diagram-area"><div class="diagram-top"><div><span class="state-dot"></span><strong id="diagramtitle">Process canvas</strong><span id="modebadge">EDITABLE BASE</span></div><div class="diagram-tools"><button id="undo" class="icon-button" title="Undo">${icon("undo")}</button><button id="redo" class="icon-button" title="Redo">${icon("redo")}</button><span class="divider"></span><button id="zoomout" class="icon-button" title="Zoom out">−</button><button id="zoomreset" class="zoom-level" title="Actual size">100%</button><button id="zoomin" class="icon-button" title="Zoom in">＋</button><button id="fit" class="icon-button" title="Fit diagram">${icon("fit")}</button><button id="togglepanel" class="icon-button" title="Toggle inspector">${icon("panel")}</button></div></div>
  <div id="draftbanner" class="draft-banner" hidden></div><div id="conflictbanner" class="conflict-banner" hidden></div><div class="diagram-stage"><div id="modelercanvas" class="diagram-canvas"></div><div id="viewercanvas" class="diagram-canvas" hidden></div><div id="empty" class="canvas-empty"><div class="empty-symbol">${icon("mark")}</div><div class="eyebrow">YOUR NEXT PROCESS STARTS HERE</div><h2>Make the process clear.<br>Keep the variations together.</h2><p>Create a base model, define what changes,<br>and validate every path through the family.</p><button id="emptycreate" class="solid">${icon("plus")} Create a process family</button><button id="emptysample" class="text-button">Open the onboarding example ${icon("chevron")}</button></div></div>
  <div id="simulation" class="simulation-dock" hidden></div>
  <div class="canvas-bottom"><span id="savestate">No model loaded</span><div><button id="autolayout">${icon("settings")} Arrange</button><button id="compare">${icon("compare")} Compare</button><button id="exportbpmn">${icon("download")} BPMN</button><button id="exportsvg">SVG</button></div></div></section>
  <aside class="inspector"><nav class="inspector-nav">${[
    ["inspect", "settings", "Inspect"],
    ["variants", "branch", "Variants"],
    ["verify", "shield", "Verify"],
    ["history", "history", "History"],
  ]
    .map(
      ([id, i, name]) =>
        `<button data-panel="${id}" title="${name}">${icon(i)}<span>${name}</span></button>`,
    )
    .join("")}</nav><div id="inspectorbody"></div></aside></div>
  <footer class="statusbar"><div><span class="status-indicator"></span><span id="metrics">BPMN 2.0 workspace</span></div><span id="scope">Local, single-user · Control-flow modeling</span><span id="activity" aria-live="polite"></span></footer>
</main>
<div id="notification" role="status" hidden></div>
<dialog id="generator" class="generator-dialog"><div class="dialog-header"><div><div class="eyebrow">PROCESS AUTHORING</div><h2>Start with the work.</h2></div><button data-close="generator" class="icon-button" aria-label="Close">${icon("close")}</button></div><div class="generator-grid"><form id="generatorform"><label class="field-label">Family name<input id="gname" maxlength="200" required placeholder="e.g. Customer onboarding"></label><div class="label-row"><label class="field-label" for="gsource">Process description</label><span id="linecount">0 lines</span></div><textarea id="gsource" spellcheck="false" required aria-describedby="syntaxhint"></textarea><div id="generationerror" class="inline-error" hidden></div><div class="generator-actions"><span id="syntaxhint">One activity per line. Explicit blocks keep decisions unambiguous.</span><button class="solid" type="submit">Generate family ${icon("chevron")}</button></div></form><aside class="authoring-guide"><div class="eyebrow">A SMALL LANGUAGE. REAL BPMN.</div><h3>Describe the sequence.<br>Make the choices explicit.</h3><p>Every line becomes a model element. Nested decisions and parallel work are compiled into connected BPMN gateways.</p><div class="syntax-example"><b>Activity</b><code>user: Review application<br>service: Verify identity</code><b>Decision</b><code>if Approved?<br>  Prepare contract<br>else<br>  Explain rejection<br>endif</code><b>Parallel work</b><code>parallel<br>  Check inventory<br>branch<br>  Check credit<br>endparallel</code><b>Swimlane ownership</b><code>user[Finance]: Approve budget</code></div><div class="sample-buttons"><span>TRY A WORKFLOW</span>${Object.entries(
  samples,
)
  .map(
    ([id, v]) =>
      `<button type="button" data-sample="${id}">${esc(v.name)} ${icon("chevron")}</button>`,
  )
  .join(
    "",
  )}</div><p class="fine-print">Deterministic generation, with no external AI dependency. Generated models are non-executable BPMN interchange documents.</p></aside></div></dialog>
<dialog id="comparemodal" class="compare-dialog"><div class="dialog-header"><div><div class="eyebrow">FAMILY COMPARISON</div><h2 id="comparetitle">Base → variant</h2></div><button data-close="comparemodal" class="icon-button" aria-label="Close">${icon("close")}</button></div><div id="diffsummary" class="diff-summary"></div><div class="compare-panes"><section><h3>REFERENCE BASE</h3><div id="basecompare"></div></section><section><h3>DERIVED VARIANT</h3><div id="variantcompare"></div></section></div></dialog>
<input id="bpmnfile" type="file" accept=".bpmn,.xml" hidden><input id="backupfile" type="file" accept=".json" hidden>`;

const modeler = new Modeler({
  container: $("#modelercanvas"),
  additionalModules: [
    { __init__: ["supportedRules"], supportedRules: ["type", SupportedRules] },
  ],
});
const viewer = new Viewer({ container: $("#viewercanvas") });
const currentVariant = () => family?.variants.find((v) => v.id === selected);
const editor = () => (selected || sim ? viewer : modeler);
const draftKey = () => (family ? "process-studio.draft." + family.id : null);
function notify(message, error = false) {
  const n = $("#notification");
  n.hidden = false;
  n.className = error ? "error" : "";
  n.innerHTML = `${icon(error ? "warning" : "check")}<span>${esc(message)}</span><button aria-label="Dismiss notification">${icon("close")}</button>`;
  n.querySelector("button").onclick = () => (n.hidden = true);
  if (!error) setTimeout(() => (n.hidden = true), 6000);
}
function run(fn) {
  return async (...args) => {
    args[0]?.preventDefault?.();
    if (busy) return;
    busy = true;
    app.classList.add("is-busy");
    $("#activity").textContent = "Working…";
    try {
      return await fn(...args);
    } catch (e) {
      notify(
        e.message + (e.requestId ? " · Request " + e.requestId : ""),
        true,
      );
    } finally {
      busy = false;
      app.classList.remove("is-busy");
      $("#activity").textContent = "";
    }
  };
}
function assertFamily() {
  if (!family) throw Error("Create or open a family first.");
}
function assertBase() {
  assertFamily();
  if (selected) throw Error("Switch to the base model to edit it.");
  if (sim) throw Error("Stop simulation before editing.");
}
async function canLeave() {
  if (!dirty) return true;
  clearTimeout(draftTimer);
  try {
    const { xml } = await modeler.saveXML({ format: true });
    localStorage.setItem(
      draftKey(),
      JSON.stringify({ xml, revision: family.revision, at: Date.now() }),
    );
  } catch {
    return confirm(
      "A recovery draft could not be stored. Leave and discard unsaved changes? Export BPMN first if you need to keep them.",
    );
  }
  return confirm(
    "Your base has unsaved changes. Leave this view? A local recovery draft has been saved.",
  );
}
function resetSelection() {
  selectedElement = null;
}
function humanType(type) {
  return (
    type
      ?.replace("bpmn:", "")
      .replace(/([a-z])([A-Z])/g, "$1 $2")
      .toLowerCase() || "element"
  );
}
function selectedGraph() {
  return currentVariant()?.graph || family?.graph;
}
function graphFromModeler() {
  const root = modeler.get("canvas").getRootElement().businessObject;
  return {
    nodes: (root.flowElements || [])
      .filter((n) => supported.has(n.$type))
      .map((n) => ({ id: n.id, type: xmlType(n.$type), name: n.name || "" })),
    edges: (root.flowElements || [])
      .filter((n) => n.$type === "bpmn:SequenceFlow")
      .map((n) => ({
        id: n.id,
        source: n.sourceRef.id,
        target: n.targetRef.id,
        name: n.name || "",
      })),
  };
}
function stopSimulation() {
  sim = null;
  $("#simulation").hidden = true;
  $("#modelercanvas").hidden = !!selected;
  $("#viewercanvas").hidden = !selected;
  editor().get("canvas").resized();
}
function renderStatus() {
  $("#title").textContent = family?.name || "Untitled workspace";
  $("#revision").textContent = family
    ? "REV " + String(family.revision).padStart(2, "0")
    : "READY";
  const v = currentVariant();
  $("#diagramtitle").textContent = v?.name || "Reference base";
  $("#modebadge").textContent =
    v?.status === "conflict"
      ? "BASE SHOWN FOR REPAIR"
      : selected
        ? "DERIVED · READ ONLY"
        : sim
          ? "SIMULATION"
          : "EDITABLE BASE";
  $("#save").disabled = !family || !!selected || !!sim || !dirty;
  $("#undo").disabled = !!selected || !!sim;
  $("#redo").disabled = !!selected || !!sim;
  $("#compare").disabled = !selected || v?.status === "conflict";
  $("#autolayout").disabled = !family || !!selected || !!sim;
  $("#savestate").innerHTML = dirty
    ? '<i class="unsaved"></i> Unsaved changes · recovery draft kept locally'
    : family
      ? `${icon("check")} Saved · revision ${family.revision}`
      : "No model loaded";
  const g = selectedGraph();
  $("#metrics").textContent = g
    ? `${g.nodes.length} elements / ${g.edges.length} flows / ${family.variants.length} variants`
    : "BPMN 2.0 workspace";
}
function renderVariantTabs() {
  $("#varianttabs").innerHTML = family
    ? `<button data-variant="" class="${!selected ? "active" : ""}">${icon("model")} Reference base</button>` +
      family.variants
        .map(
          (v) =>
            `<button data-variant="${v.id}" class="${selected === v.id ? "active" : ""} ${v.status === "conflict" ? "has-conflict" : ""}"><span class="variant-dot"></span>${esc(v.name)}${v.status === "conflict" ? icon("warning") : ""}</button>`,
        )
        .join("")
    : '<span class="no-family">No family selected</span>';
  $$("[data-variant]").forEach(
    (b) =>
      (b.onclick = run(async () => {
        if (!(await canLeave())) return;
        if (panel === "variants") keepRecipe();
        selected = b.dataset.variant || null;
        await showFamily();
      })),
  );
}
async function refreshLibrary() {
  const fs = await api("families");
  $("#familycount").textContent = String(fs.length).padStart(2, "0");
  const search = $("#searchfamilies").value.toLowerCase();
  $("#familylist").innerHTML =
    fs
      .filter((f) => f.name.toLowerCase().includes(search))
      .map(
        (f, i) =>
          `<button data-family="${f.id}" aria-label="${esc(f.name)} · ${f.variantCount} variants" class="family-card ${family?.id === f.id ? "active" : ""}"><span class="family-number">${String(i + 1).padStart(2, "0")}</span><span class="family-card-content"><strong>${esc(f.name)}</strong><small>${f.variantCount} variants <span>·</span> rev ${f.revision}</small></span>${icon("chevron")}</button>`,
      )
      .join("") ||
    '<p class="library-empty">No matching families.<br>Create one to get started.</p>';
  $$("[data-family]").forEach(
    (b) => (b.onclick = run(() => openFamily(b.dataset.family))),
  );
  return fs;
}
async function openFamily(id) {
  if (!(await canLeave())) return;
  family = await api("families/" + id);
  selected = null;
  dirty = false;
  localStorage.setItem("process-studio.last-family", id);
  await showFamily();
}
async function layout(xml, quiet = false) {
  try {
    return await arrangeXML(xml);
  } catch (e) {
    if (!quiet) notify("Automatic arrangement unavailable: " + e.message, true);
    return xml;
  }
}
function fitDiagram(target, readable = false) {
  const canvas = target.get("canvas"),
    outer = canvas.getContainer();
  const items = target
    .get("elementRegistry")
    .getAll()
    .filter((e) => e.parent && !e.hidden);
  const points = [];
  for (const e of items) {
    if (e.waypoints) points.push(...e.waypoints);
    else if (Number.isFinite(e.x))
      points.push({ x: e.x, y: e.y }, { x: e.x + e.width, y: e.y + e.height });
  }
  if (!points.length) return;
  const left = target === modeler ? 95 : 35,
    right = 35;
  const minX = Math.min(...points.map((p) => p.x)),
    maxX = Math.max(...points.map((p) => p.x)),
    minY = Math.min(...points.map((p) => p.y)),
    maxY = Math.max(...points.map((p) => p.y));
  const fit = Math.min(
    (outer.clientWidth - left - right) / Math.max(1, maxX - minX),
    (outer.clientHeight - 80) / Math.max(1, maxY - minY),
    1,
  );
  const scale = Math.max(0.1, readable ? Math.max(fit, 0.8) : fit);
  canvas.viewbox({
    x: minX - left / scale,
    y: (minY + maxY) / 2 - outer.clientHeight / (2 * scale),
    width: outer.clientWidth / scale,
    height: outer.clientHeight / scale,
  });
}
async function showFamily() {
  clearTimeout(draftTimer);
  lastAnalysis = null;
  lastRelease = null;
  documentEpoch++;
  loading = true;
  stopSimulation();
  resetSelection();
  try {
    const v = currentVariant();
    let source = family?.xml;
    if (v?.status === "current") {
      const key =
        family.id + ":" + family.revision + ":" + v.id + ":" + v.version;
      if (!layoutCache.has(key)) {
        if (layoutCache.size > 40) layoutCache.clear();
        layoutCache.set(key, await layout(v.xml, true));
      }
      source = layoutCache.get(key);
    }
    $("#conflictbanner").hidden = v?.status !== "conflict";
    if (v?.status === "conflict") {
      $("#conflictbanner").innerHTML =
        `${icon("warning")}<div><b>Variant needs repair</b><span>${esc(v.error)}. The reference base is shown so you can choose a replacement target.</span></div><button id="repair">Open recipe</button>`;
      $("#repair").onclick = () => setPanel("variants");
      panel = "variants";
    }
    $("#modelercanvas").hidden = !!selected;
    $("#viewercanvas").hidden = !selected;
    if (source) {
      const target = selected ? viewer : modeler;
      await target.importXML(source);
      fitDiagram(target, true);
    }
    dirty = false;
    $("#empty").hidden = !!family;
    renderStatus();
    renderVariantTabs();
    renderPanel();
    showDraftRecovery();
    await refreshLibrary();
  } finally {
    loading = false;
  }
}
function showDraftRecovery() {
  $("#draftbanner").hidden = true;
  if (!family || selected) return;
  let draft;
  try {
    draft = JSON.parse(localStorage.getItem(draftKey()) || "null");
  } catch {
    return;
  }
  if (!draft?.xml) return;
  $("#draftbanner").hidden = false;
  $("#draftbanner").innerHTML =
    `<span>${icon("history")} Local recovery draft from ${esc(new Date(draft.at).toLocaleString())}${draft.revision !== family.revision ? " · based on an older revision" : ""}</span><div><button id="recoverdraft">Recover to canvas</button><button id="discarddraft">Discard draft</button></div>`;
  $("#recoverdraft").onclick = run(async () => {
    loading = true;
    try {
      await modeler.importXML(draft.xml);
      dirty = true;
      $("#draftbanner").hidden = true;
      renderStatus();
      notify("Draft recovered. Review before saving to the current base.");
    } finally {
      loading = false;
    }
  });
  $("#discarddraft").onclick = () => {
    if (confirm("Remove this local recovery draft?")) {
      localStorage.removeItem(draftKey());
      $("#draftbanner").hidden = true;
    }
  };
}
modeler.on("commandStack.changed", () => {
  if (loading || !family || selected || sim) return;
  dirty = true;
  lastAnalysis = null;
  lastRelease = null;
  renderStatus();
  clearTimeout(draftTimer);
  const epoch = documentEpoch,
    key = draftKey(),
    revision = family.revision;
  draftTimer = setTimeout(async () => {
    try {
      const { xml } = await modeler.saveXML({ format: true });
      if (epoch === documentEpoch)
        localStorage.setItem(
          key,
          JSON.stringify({ xml, revision, at: Date.now() }),
        );
    } catch {
      notify(
        "Local recovery storage is unavailable. Export BPMN to keep a copy.",
        true,
      );
    }
  }, 450);
});
for (const e of [modeler, viewer]) {
  e.on("element.click", ({ element }) => {
    if (element.type === "label") element = element.labelTarget;
    selectedElement = element;
    $("#selectedtarget") && ($("#selectedtarget").value = element.id);
    if (panel === "inspect") renderPanel();
  });
  e.on("canvas.viewbox.changed", ({ viewbox }) => {
    $("#zoomreset").textContent = Math.round(viewbox.scale * 100) + "%";
  });
}
function setPanel(name) {
  panel = name;
  renderPanel();
}
function renderPanel() {
  $$("[data-panel]").forEach((b) =>
    b.classList.toggle("active", b.dataset.panel === panel),
  );
  if (panel === "inspect") renderInspector();
  if (panel === "variants") renderRecipes();
  if (panel === "verify") renderVerification();
  if (panel === "history") renderHistory();
}
function renderInspector() {
  const p = $("#inspectorbody");
  const el = selectedElement;
  const bo = el?.businessObject;
  if (!family) {
    p.innerHTML = `<div class="panel-kicker">MODEL INSPECTOR</div><h2>A place for every detail.</h2><p class="panel-intro">Open a process family, then select an element to inspect its name, type, ownership and documentation.</p><div class="inspector-illustration">${icon("model")}</div><div class="help-card"><b>Model with intention</b><p>Use verb + object for activity names. Phrase decisions as questions. Label outgoing decision flows with the alternatives.</p></div>`;
    return;
  }
  if (!bo || (!supported.has(bo.$type) && bo.$type !== "bpmn:SequenceFlow")) {
    p.innerHTML = `<div class="panel-kicker">REFERENCE MODEL</div><h2>${esc(family.name)}</h2><p class="panel-intro">One base process. ${family.variants.length} contextual ${family.variants.length === 1 ? "variant" : "variants"}.</p><div class="definition-list"><div><span>Base revision</span><strong>${family.revision}</strong></div><div><span>Model elements</span><strong>${family.graph.nodes.length}</strong></div><div><span>Conflicted variants</span><strong class="${family.variants.some((v) => v.status === "conflict") ? "text-warning" : ""}">${family.variants.filter((v) => v.status === "conflict").length}</strong></div></div><div class="section-heading">ELEMENT DIRECTORY</div><label class="search-field light">${icon("search")}<input id="elementsearch" placeholder="Find a task or gateway…" aria-label="Find a model element"></label><div id="elementdirectory" class="element-directory"></div><div class="help-card"><b>Click to inspect</b><p>Select a shape or flow on the canvas. Changes to the base are propagated when you save.</p></div><button id="renamefamily" class="outline wide">Rename family</button>`;
    const populate = () => {
      const filter = $("#elementsearch").value.toLowerCase();
      const nodes = selectedGraph()?.nodes || [];
      $("#elementdirectory").innerHTML = nodes
        .filter((n) => (n.name + " " + n.id).toLowerCase().includes(filter))
        .map(
          (n) =>
            `<button data-element="${esc(n.id)}"><span class="element-type">${n.type.endsWith("Gateway") ? "◇" : n.type.endsWith("Event") ? "○" : "▢"}</span><span>${esc(n.name || humanType(n.type))}<small>${esc(n.id)}</small></span></button>`,
        )
        .join("");
      $$("[data-element]").forEach(
        (b) =>
          (b.onclick = () => {
            const target = editor()
              .get("elementRegistry")
              .get(b.dataset.element);
            if (target) {
              selectedElement = target;
              editor().get("canvas").scrollToElement(target);
              renderInspector();
            }
          }),
      );
    };
    $("#elementsearch").oninput = populate;
    populate();
    $("#renamefamily").onclick = run(async () => {
      assertBase();
      const name = prompt("Family name", family.name);
      if (!name?.trim()) return;
      const { xml } = await modeler.saveXML({ format: true });
      family = await api("save", {
        family: family.id,
        revision: family.revision,
        name,
        xml,
      });
      clearTimeout(draftTimer);
      localStorage.removeItem(draftKey());
      dirty = false;
      await showFamily();
      notify("Family renamed and base saved.");
    });
    return;
  }
  const readOnly = !!selected || !!sim;
  const kind = humanType(bo.$type);
  const lane = (bo.lanes || [])[0];
  p.innerHTML = `<div class="panel-kicker">${bo.$type === "bpmn:SequenceFlow" ? "SEQUENCE FLOW" : "SELECTED ELEMENT"}</div><h2>${esc(bo.name || kind)}</h2><div class="element-identity"><span>${esc(kind)}</span><code>${esc(bo.id)}</code></div>${readOnly ? '<div class="read-only-note">Derived view · change the recipe to modify this variant.</div>' : ""}<form id="propertiesform"><label class="field-label">Name<textarea id="elementname" class="property-name" maxlength="200" ${readOnly ? "readonly" : ""}>${esc(bo.name || "")}</textarea></label>${activityTypes.includes(xmlType(bo.$type)) ? `<label class="field-label">Activity type<select id="elementtype" ${readOnly ? "disabled" : ""}>${activityTypes.map((t) => `<option value="${t}" ${bo.$type === modelerType(t) ? "selected" : ""}>${esc(humanType(t))}</option>`).join("")}</select></label>` : ""}<label class="field-label">Documentation<textarea id="elementdescription" class="description-field" maxlength="4000" ${readOnly ? "readonly" : ""}>${esc(bo.documentation?.[0]?.text || "")}</textarea></label>${lane ? `<div class="definition-list"><div><span>Lane owner</span><strong>${esc(lane.name || lane.id)}</strong></div></div>` : ""}${!readOnly ? '<button type="submit" class="solid wide">Apply changes</button>' : ""}</form><div class="section-heading">MODELING NOTE</div><div class="modeling-note">${bo.$type.endsWith("Gateway") ? "Use exclusive gateways for alternatives and parallel gateways for concurrent work. A parallel join waits for every incoming branch." : bo.$type === "bpmn:SequenceFlow" ? "Name exclusive alternatives clearly. Conditions are represented as design labels; this application does not evaluate business expressions." : "A clear activity name describes an action and its business object. Documentation carries business meaning without crowding the diagram."}</div><button id="useinrecipe" class="outline wide">${icon("branch")} Use in variant recipe</button>`;
  const evidence = family.generation?.traceability?.find((t) => t.id === bo.id);
  if (evidence) {
    const changed =
      evidence.name !== bo.name || modelerType(evidence.type) !== bo.$type;
    $("#propertiesform").insertAdjacentHTML(
      "afterend",
      `<section class="source-evidence"><div class="section-heading">SOURCE EVIDENCE ${changed ? '<span class="text-warning">ACTIVITY CHANGED</span>' : ""}</div><blockquote>${esc(evidence.quote)}</blockquote><p>${changed ? "This activity has changed since it was generated. Recheck whether the original evidence still supports it." : "Exact passage from the original business description. Quote presence is verified; business interpretation still requires review."}</p><small>Characters ${evidence.start}–${evidence.end} · original input</small></section>`,
    );
  } else if (
    currentVariant()?.operations.some(
      (op) => op.action === "insert" && bo.id === "Option_" + op.id,
    )
  ) {
    $("#propertiesform").insertAdjacentHTML(
      "afterend",
      '<div class="source-evidence"><div class="section-heading">VARIANT PROVENANCE</div><p>This activity was introduced by the selected variant recipe.</p></div>',
    );
  }
  $("#propertiesform").onsubmit = run(async (e) => {
    e.preventDefault();
    assertBase();
    let element = selectedElement;
    const type = $("#elementtype")?.value;
    if (type && element.type !== modelerType(type)) {
      element = modeler
        .get("bpmnReplace")
        .replaceElement(element, { type: modelerType(type) });
      selectedElement = element;
    }
    const description = $("#elementdescription").value;
    const documentation = description
      ? [
          modeler
            .get("moddle")
            .create("bpmn:Documentation", { text: description }),
        ]
      : [];
    modeler.get("modeling").updateProperties(element, {
      name: $("#elementname").value.trim(),
      documentation,
    });
    renderInspector();
    notify("Element updated. Save the base to propagate changes.");
  });
  $("#useinrecipe").onclick = () => {
    setPanel("variants");
    editOperation();
  };
}
let recipeDraftKey = null,
  recipeName = "",
  recipeContext = {};
function recipeKey() {
  return family?.id + ":" + (selected || "new");
}
const recipeDrafts = new Map();
function keepRecipe() {
  if ($("#variantname"))
    recipeDrafts.set(recipeDraftKey, {
      name: $("#variantname").value,
      context: readContextRows(false),
      operations: structuredClone(recipe),
    });
}
function readContextRows(strict = true) {
  const value = {};
  for (const row of $$(".context-row")) {
    const key = row.querySelector("[data-context-key]").value.trim(),
      v = row.querySelector("[data-context-value]").value.trim();
    if (!key && !v) continue;
    if (!key) {
      if (strict) throw Error("Every context value needs a key.");
      continue;
    }
    if (Object.hasOwn(value, key) && strict)
      throw Error("Context keys must be unique.");
    value[key] = v;
  }
  return value;
}
function renderRecipes() {
  const p = $("#inspectorbody");
  if (!family) {
    p.innerHTML =
      '<div class="panel-kicker">VARIABILITY</div><h2>Configure the differences.</h2><p class="panel-intro">Create a base family before defining contextual variants.</p>';
    return;
  }
  const v = currentVariant();
  recipeDraftKey = recipeKey();
  const draft = recipeDrafts.get(recipeDraftKey);
  recipe = structuredClone(draft?.operations || v?.operations || []);
  recipeName = draft?.name ?? v?.name ?? "";
  recipeContext = draft?.context ?? v?.context ?? {};
  p.innerHTML = `<div class="panel-kicker">${v?.status === "conflict" ? "REPAIR VARIANT" : v ? "EDIT VARIANT" : "NEW VARIANT"}</div><h2>${v ? "Make the differences explicit." : "Same process. Different context."}</h2><p class="panel-intro">An ordered recipe transforms the saved reference base. The base stays intact.</p><label class="field-label">Variant name<input id="variantname" maxlength="200" value="${esc(recipeName)}" placeholder="e.g. India · Business accounts"></label><div class="section-heading section-actions"><span>BUSINESS CONTEXT</span><button id="addcontext" class="text-button">${icon("plus")} Add</button></div><div id="contextrows"></div><div class="section-heading section-actions"><span>CHANGE RECIPE <b id="recipecount"></b></span><button id="addoperation" class="text-button">${icon("plus")} Add</button></div><div id="recipecards"></div><div id="operationeditor" hidden></div><div class="recipe-controls"><button id="previewrecipe" class="outline">Preview changes</button><button id="saverecipe" class="solid">${v ? "Update variant" : "Create variant"}</button></div>${v ? `<div class="variant-details"><span>Variant version ${v.version}</span><button id="duplicatevariant" class="text-button">Duplicate</button><button id="deletevariant" class="text-button danger">Move to trash</button></div>` : ""}<details class="advanced"><summary>Advanced recipe JSON</summary><textarea id="recipejson" spellcheck="false"></textarea><button id="applyjson" class="outline wide">Load JSON into recipe</button><p>Explicit operation IDs keep inserted activity references stable when reordered.</p></details><div class="help-card"><b>Configuration, not duplication</b><p>Base changes automatically re-derive every recipe. Missing target IDs are surfaced as conflicts that you can repair here.</p></div>`;
  renderContext(recipeContext);
  renderRecipeCards();
  $("#variantname").oninput = keepRecipe;
  $("#addcontext").onclick = () => {
    addContextRow("", "");
    keepRecipe();
  };
  $("#addoperation").onclick = () => editOperation();
  $("#saverecipe").onclick = run(async () => {
    if (dirty)
      throw Error("Save the base before creating or updating variants.");
    keepRecipe();
    const payload = {
      family: family.id,
      revision: family.revision,
      name: $("#variantname").value,
      context: readContextRows(),
      operations: recipe,
    };
    if (v) {
      payload.id = v.id;
      payload.version = v.version;
    }
    const updated = await api(v ? "update-variant" : "variant", payload);
    recipeDrafts.delete(recipeDraftKey);
    family = updated;
    if (!v)
      selected =
        family.variants.find((x) => x.name === payload.name.trim())?.id || null;
    await showFamily();
    notify("Variant validated and saved.");
  });
  $("#previewrecipe").onclick = run(async () => {
    keepRecipe();
    if (dirty) throw Error("Save the base before previewing a recipe.");
    const result = await api("preview-variant", {
      family: family.id,
      revision: family.revision,
      operations: recipe,
    });
    await showComparison(
      {
        name: $("#variantname").value || "Recipe preview",
        graph: result.graph,
        xml: await layout(result.xml, true),
      },
      result.analysis,
    );
  });
  $("#applyjson").onclick = () => {
    try {
      const ops = JSON.parse($("#recipejson").value);
      if (!Array.isArray(ops) || ops.length > 100)
        throw Error("Use an array of at most 100 operations.");
      recipe = ops;
      keepRecipe();
      renderRecipeCards();
      notify("JSON loaded. Preview to validate the recipe.");
    } catch (e) {
      notify(e.message, true);
    }
  };
  if (v) {
    $("#duplicatevariant").onclick = run(async () => {
      keepRecipe();
      const draft = recipeDrafts.get(recipeDraftKey);
      selected = null;
      recipeDrafts.set(family.id + ":new", {
        ...draft,
        name: draft.name + " copy",
      });
      await showFamily();
    });
    $("#deletevariant").onclick = run(async () => {
      if (
        !confirm("Move this variant to trash? It can be restored from History.")
      )
        return;
      family = await api("delete-variant", {
        family: family.id,
        revision: family.revision,
        id: v.id,
        version: v.version,
      });
      recipeDrafts.delete(recipeDraftKey);
      selected = null;
      await showFamily();
      notify("Variant moved to trash.");
    });
  }
}
function renderContext(value) {
  $("#contextrows").innerHTML = "";
  for (const [k, v] of Object.entries(value)) addContextRow(k, String(v));
  if (!Object.keys(value).length) addContextRow("", "");
}
function addContextRow(key, value) {
  const row = document.createElement("div");
  row.className = "context-row";
  row.innerHTML = `<input data-context-key aria-label="Context key" placeholder="Country" value="${esc(key)}"><input data-context-value aria-label="Context value" placeholder="India" value="${esc(value)}"><button class="icon-button" title="Remove context">${icon("close")}</button>`;
  row.querySelector("button").onclick = () => {
    row.remove();
    keepRecipe();
  };
  row.querySelectorAll("input").forEach((i) => (i.oninput = keepRecipe));
  $("#contextrows").append(row);
}
function renderRecipeCards() {
  $("#recipecount").textContent = String(recipe.length).padStart(2, "0");
  $("#recipecards").innerHTML = recipe.length
    ? recipe
        .map(
          (op, i) =>
            `<article class="recipe-card"><span class="recipe-number">${String(i + 1).padStart(2, "0")}</span><div class="recipe-card-main"><span class="operation-label ${esc(op.action)}">${esc(op.action)}</span><strong>${esc(op.name || op.target)}</strong><small>${esc(op.target)}${op.after ? " → " + esc(op.after) : ""}${op.id ? " · " + esc(op.id).slice(0, 15) : ""}</small><div class="recipe-card-actions"><button data-edit-op="${i}">Edit</button><button data-up-op="${i}" ${i === 0 ? "disabled" : ""} title="Move operation earlier">↑</button><button data-down-op="${i}" ${i === recipe.length - 1 ? "disabled" : ""} title="Move operation later">↓</button><button data-remove-op="${i}" title="Remove operation">${icon("close")}</button></div></div></article>`,
        )
        .join("")
    : '<div class="recipe-empty"><span>01</span><p>No changes yet.<br>Add an operation to specialize this process.</p></div>';
  $("#recipejson").value = JSON.stringify(recipe, null, 2);
  $$("[data-edit-op]").forEach(
    (b) => (b.onclick = () => editOperation(Number(b.dataset.editOp))),
  );
  $$("[data-remove-op]").forEach(
    (b) =>
      (b.onclick = () => {
        recipe.splice(Number(b.dataset.removeOp), 1);
        keepRecipe();
        renderRecipeCards();
      }),
  );
  for (const [attr, delta] of [
    ["upOp", -1],
    ["downOp", 1],
  ])
    $$(`[data-${attr === "upOp" ? "up" : "down"}-op]`).forEach(
      (b) =>
        (b.onclick = () => {
          const i = Number(b.dataset[attr]);
          [recipe[i], recipe[i + delta]] = [recipe[i + delta], recipe[i]];
          keepRecipe();
          renderRecipeCards();
        }),
    );
}
function editOperation(index) {
  const op =
    index === undefined
      ? {
          action: "insert",
          target: selectedElement?.id || "",
          name: "",
          id: "Op_" + crypto.randomUUID().replaceAll("-", ""),
        }
      : recipe[index];
  const nodes = [
    ...family.graph.nodes,
    ...recipe
      .filter((o) => o.action === "insert" && o.id)
      .map((o) => ({ id: "Option_" + o.id, name: o.name })),
  ];
  const container = $("#operationeditor");
  container.hidden = false;
  container.innerHTML = `<form id="opform"><div class="section-heading">${index === undefined ? "ADD CHANGE" : "EDIT CHANGE"}</div><label class="field-label">Operation<select id="opaction">${["insert", "modify", "delete", "move"].map((a) => `<option ${a === op.action ? "selected" : ""}>${a}</option>`).join("")}</select></label><label class="field-label">Target element<input id="selectedtarget" list="nodeids" value="${esc(op.target)}" required placeholder="Click an element or choose its ID"><datalist id="nodeids">${nodes.map((n) => `<option value="${esc(n.id)}">${esc(n.name || humanType(n.type))}</option>`).join("")}</datalist></label><label id="opnamelabel" class="field-label">Activity name<input id="opname" maxlength="200" value="${esc(op.name || "")}"></label><label id="opafterlabel" class="field-label">Insert after element<input id="opafter" list="nodeids" value="${esc(op.after || "")}"></label><label id="optypelabel" class="field-label">Activity type<select id="optype">${activityTypes.map((t) => `<option value="${t}" ${t === (op.type || "userTask") ? "selected" : ""}>${humanType(t)}</option>`).join("")}</select></label><label id="oprolelabel" class="field-label">Lane owner (optional)<input id="oprole" maxlength="100" value="${esc(op.role || "")}"></label><div class="recipe-controls"><button type="button" id="cancelop" class="outline">Cancel</button><button type="submit" class="solid">${index === undefined ? "Add change" : "Apply change"}</button></div></form>`;
  const update = () => {
    const a = $("#opaction").value;
    $("#opnamelabel").hidden = !["insert", "modify"].includes(a);
    $("#opafterlabel").hidden = a !== "move";
    $("#optypelabel").hidden = a !== "insert";
    $("#oprolelabel").hidden = a !== "insert";
  };
  $("#opaction").onchange = update;
  update();
  $("#cancelop").onclick = () => (container.hidden = true);
  $("#opform").onsubmit = (e) => {
    e.preventDefault();
    const action = $("#opaction").value;
    const next = {
      id: op.id || "Op_" + crypto.randomUUID().replaceAll("-", ""),
      action,
      target: $("#selectedtarget").value.trim(),
    };
    if (!next.target) return notify("Choose a target element.", true);
    if (["insert", "modify"].includes(action)) {
      next.name = $("#opname").value.trim();
      if (!next.name) return notify("Enter an activity name.", true);
    }
    if (action === "move") {
      next.after = $("#opafter").value.trim();
      if (!next.after) return notify("Choose a move destination.", true);
    }
    if (action === "insert") {
      next.type = $("#optype").value;
      if ($("#oprole").value.trim()) next.role = $("#oprole").value.trim();
    }
    if (index === undefined) recipe.push(next);
    else recipe[index] = next;
    container.hidden = true;
    keepRecipe();
    renderRecipeCards();
  };
  container.scrollIntoView({ block: "nearest", behavior: "smooth" });
}
function analysisCard(a, name = "Current diagram") {
  const state = a.sound
    ? "pass"
    : a.complete
      ? "fail"
      : a.valid
        ? "incomplete"
        : "fail";
  const label = a.sound
    ? "Sound control flow"
    : a.complete
      ? "Behavior needs attention"
      : a.valid
        ? "Analysis incomplete"
        : "Invalid structure";
  return `<div class="analysis-card ${state}"><div class="analysis-heading">${icon(a.sound ? "check" : "warning")}<div><small>${esc(name)}</small><h3>${label}</h3></div></div><div class="analysis-stats"><div><strong>${a.states ?? "—"}</strong><span>states explored</span></div><div><strong>${a.deadlocks ?? "—"}</strong><span>deadlocks</span></div></div><p>${a.complete ? "All reachable states explored." : esc(a.reason || "Exploration did not complete.")}</p>${(a.errors || []).map((e) => `<p class="validation-error">${esc(e)}</p>`).join("")}${a.unfired?.length ? `<p>Unfired elements: ${a.unfired.map(esc).join(", ")}</p>` : ""}${a.counterexample?.length ? `<details><summary>Path to a deadlock</summary><ol>${a.counterexample.map((n) => `<li>${esc(n.name)} <code>${esc(n.id)}</code></li>`).join("")}</ol></details>` : ""}</div>`;
}
let lastAnalysis = null,
  lastRelease = null;
function renderVerification() {
  const p = $("#inspectorbody");
  p.innerHTML = `<div class="panel-kicker">QUALITY & BEHAVIOR</div><h2>Check every path.</h2><p class="panel-intro">Inspect the current diagram or validate the entire family before handoff.</p><button id="analyze" class="solid wide">${icon("shield")} Analyze current diagram</button><div id="analysisresult"></div><div class="section-heading">INTERACTIVE SIMULATION</div><p class="body-small">Follow enabled activities, choose alternatives, and watch parallel branches synchronize.</p><button id="simulate" class="outline wide">${icon("play")} Start simulation</button><div id="trace"></div><div class="section-heading">FAMILY RELEASE CHECK</div><p class="body-small">Every saved variant must derive without conflicts and pass complete control-flow analysis.</p><button id="checkfamily" class="outline wide">Validate all saved variants</button><div id="familychecks"></div><div class="scope-note"><b>What this proves</b><p>Control-flow completion and deadlock checks for one acyclic BPMN process. Up to 10,000 states / 3 seconds per model. Data conditions, external services and regulatory correctness are outside this check.</p></div>`;
  if (lastAnalysis && lastAnalysis.key === family?.id + ":" + selected)
    $("#analysisresult").innerHTML = analysisCard(lastAnalysis.value);
  $("#analyze").onclick = run(async () => {
    assertFamily();
    if (currentVariant()?.status === "conflict")
      throw Error("Repair this variant before analyzing its derived behavior.");
    const { xml } = await editor().saveXML({ format: true });
    const a = await api("analyze", { xml });
    lastAnalysis = { key: family.id + ":" + selected, value: a };
    $("#analysisresult").innerHTML =
      analysisCard(a) +
      `<button id="downloadanalysis" class="text-button">${icon("download")} Download report</button>`;
    $("#downloadanalysis").onclick = () =>
      download(
        "analysis.json",
        JSON.stringify(
          {
            family: family.name,
            revision: family.revision,
            variant: currentVariant()?.name || "Base",
            analysis: a,
          },
          null,
          2,
        ),
      );
  });
  $("#simulate").onclick = run(startSimulation);
  $("#checkfamily").onclick = run(async () => {
    assertFamily();
    if (dirty)
      throw Error(
        "Save the current base before running a family release check.",
      );
    lastRelease = await api("release", {
      family: family.id,
      revision: family.revision,
    });
    $("#familychecks").innerHTML =
      `<div class="release-summary ${lastRelease.approved ? "approved" : ""}">${icon(lastRelease.approved ? "check" : "warning")}<strong>${lastRelease.approved ? "Family ready for modeling handoff" : "Family has unresolved issues"}</strong></div>` +
      lastRelease.checks
        .map(
          (c) =>
            `<div class="release-row"><span>${esc(c.name)}</span><b class="${c.analysis.sound ? "text-success" : "text-warning"}">${c.analysis.sound ? "Pass" : "Review"}</b></div>`,
        )
        .join("") +
      `<div class="release-fingerprint"><span>VALIDATION FINGERPRINT</span><code>${esc(lastRelease.fingerprint)}</code></div><button id="releasereport" class="text-button">Download validation report</button>${lastRelease.approved ? '<button id="releasebundle" class="solid wide">Download validated family backup</button>' : ""}`;
    $("#releasereport").onclick = () => {
      const { backup, ...report } = lastRelease;
      download("family-validation.json", JSON.stringify(report, null, 2));
    };
    if ($("#releasebundle"))
      $("#releasebundle").onclick = () =>
        download(
          family.name + "-validated.json",
          JSON.stringify(lastRelease.backup, null, 2),
        );
  });
  if (sim) renderSimulation();
}
function renderHistory() {
  const p = $("#inspectorbody");
  if (!family) {
    p.innerHTML =
      '<div class="panel-kicker">HISTORY</div><h2>Keep the reasoning.</h2><p class="panel-intro">Saved base revisions and variant changes will appear here.</p>';
    return;
  }
  p.innerHTML = `<div class="panel-kicker">EVOLUTION & RECOVERY</div><h2>Changes with a trail.</h2><p class="panel-intro">Restore previous bases as new revisions. Recover deleted variants without rebuilding their recipes.</p><button id="backup" class="solid wide">${icon("download")} Export complete family backup</button><div class="section-heading">BASE REVISIONS</div><div class="history-list">${family.history.map((h) => `<div class="history-row"><span class="history-dot"></span><div><b>Revision ${h.revision}</b><small>${esc(h.created)} UTC</small></div><button data-restore="${h.id}" ${h.revision === family.revision ? "disabled" : ""}>${h.revision === family.revision ? "Current" : "Restore"}</button></div>`).join("")}</div><div class="section-heading">VARIANT TRASH <b>${family.trash.length}</b></div>${family.trash.map((v) => `<div class="trash-row"><span>${esc(v.name)}</span><button data-recover="${v.id}">Restore</button></div>`).join("") || '<p class="body-small">No deleted variants.</p>'}<div class="section-heading">AUDIT TRAIL <span>LAST 100</span></div><div class="audit-list">${family.audit.map((a) => `<article><strong>${esc(a.action.replaceAll(".", " "))}</strong><time>${esc(a.created)} UTC</time><small>${esc(a.detail)}</small></article>`).join("") || '<p class="body-small">Earlier v1 changes have no audit entries.</p>'}</div>`;
  $("#backup").onclick = run(async () => {
    const backup = await api("families/" + family.id + "/backup");
    download(family.name + ".json", JSON.stringify(backup, null, 2));
    notify(
      "Complete family backup exported, including recipes and historical bases.",
    );
  });
  $$("[data-restore]").forEach(
    (b) =>
      (b.onclick = run(async () => {
        if (!(await canLeave())) return;
        if (
          !confirm(
            "Restore this historical base as a new revision? All active variant recipes will be re-derived.",
          )
        )
          return;
        family = await api("restore", {
          family: family.id,
          revision: family.revision,
          history: Number(b.dataset.restore),
        });
        selected = null;
        recipeDrafts.clear();
        await showFamily();
        notify("Historical base restored as a new revision.");
      })),
  );
  $$("[data-recover]").forEach(
    (b) =>
      (b.onclick = run(async () => {
        const v = family.trash.find((v) => v.id === b.dataset.recover);
        family = await api("restore-variant", {
          family: family.id,
          revision: family.revision,
          id: v.id,
          version: v.version,
        });
        await showFamily();
        notify("Variant restored.");
      })),
  );
}
async function saveBase() {
  assertBase();
  if (!dirty) {
    notify("The base is already saved.");
    return;
  }
  const { xml } = await modeler.saveXML({ format: true });
  const impact = await api("preview-base", {
    family: family.id,
    revision: family.revision,
    xml,
  });
  if (
    impact.conflicts.length &&
    !confirm(
      "This base change creates conflicts in " +
        impact.conflicts.map((c) => c.name).join(", ") +
        ". Save the base and retain these recipes for repair?",
    )
  )
    return;
  family = await api("save", {
    family: family.id,
    revision: family.revision,
    xml,
  });
  clearTimeout(draftTimer);
  localStorage.removeItem(draftKey());
  dirty = false;
  lastAnalysis = null;
  await showFamily();
  notify(
    impact.conflicts.length
      ? "Base saved. Conflicted recipes are retained for repair."
      : "Base saved. All variant recipes re-derived.",
  );
}
async function startSimulation() {
  assertFamily();
  if (sim) stopSimulation();
  if (currentVariant()?.status === "conflict")
    throw Error("Repair the variant before simulating it.");
  const { xml } = await editor().saveXML({ format: true });
  const analysis = await api("analyze", { xml });
  if (!analysis.sound)
    throw Error(
      "Simulation requires complete, sound control-flow analysis. Run Analyze for details.",
    );
  const source = selected ? selectedGraph() : graphFromModeler();
  sim = createSimulation(source);
  $("#modelercanvas").hidden = true;
  $("#viewercanvas").hidden = false;
  await viewer.importXML(xml);
  fitDiagram(viewer, true);
  renderStatus();
  renderSimulation();
}
function renderSimulation() {
  if (!sim) return;
  const canvas = viewer.get("canvas");
  viewer
    .get("elementRegistry")
    .getAll()
    .forEach((e) => canvas.removeMarker(e.id, "token-active"));
  for (const [id, count] of sim.tokens)
    if (count) canvas.addMarker(id, "token-active");
  const steps = enabledSteps(sim);
  $("#simulation").hidden = false;
  $("#simulation").innerHTML =
    `<div class="simulation-heading"><span class="simulation-label">${icon("play")} SIMULATION</span><strong>${completed(sim) ? "Process completed" : steps.length + " enabled " + (steps.length === 1 ? "step" : "steps")}</strong><button id="stopsimulation" class="icon-button" title="Stop simulation">${icon("close")}</button></div><div class="enabled-steps">${steps.map((s, i) => `<button data-step="${i}"><span>${esc(humanType(s.node.type))}</span>${esc(s.label)} ${icon("chevron")}</button>`).join("")}${completed(sim) ? "<p>Exactly one completion. No tokens remain.</p>" : ""}</div>`;
  $$("[data-step]").forEach(
    (b) =>
      (b.onclick = () => {
        advance(sim, steps[Number(b.dataset.step)]);
        renderSimulation();
      }),
  );
  $("#stopsimulation").onclick = () => {
    stopSimulation();
    renderStatus();
    if (panel === "verify") renderVerification();
  };
  if ($("#trace")) {
    $("#trace").innerHTML =
      `<div class="trace-header"><b>Execution trace</b><button id="exporttrace" class="text-button">Export</button></div><ol class="trace-list">${sim.trace.map((e) => `<li>${esc(e.name || "Process started")}</li>`).join("")}</ol>`;
    $("#exporttrace").onclick = () =>
      download(
        "simulation-trace.json",
        JSON.stringify(
          {
            family: family.name,
            revision: family.revision,
            variant: currentVariant()?.name || "Base",
            completed: completed(sim),
            trace: sim.trace,
          },
          null,
          2,
        ),
      );
  }
}
async function showComparison(variant, analysis) {
  if (!variant?.graph)
    throw Error("No derived model is available. Repair the recipe first.");
  comparisonViewers.forEach((v) => v.destroy());
  comparisonViewers = [];
  const base = new Map(family.graph.nodes.map((n) => [n.id, n])),
    other = new Map(variant.graph.nodes.map((n) => [n.id, n]));
  const changes = [];
  for (const [id, n] of other) {
    if (!base.has(id)) changes.push({ type: "added", name: n.name || id, id });
    else if (
      base.get(id).name !== n.name ||
      base.get(id).type !== n.type ||
      base.get(id).role !== n.role
    )
      changes.push({
        type: "changed",
        name: (base.get(id).name || id) + " → " + (n.name || id),
        id,
      });
  }
  for (const [id, n] of base)
    if (!other.has(id))
      changes.push({ type: "removed", name: n.name || id, id });
  const flowA = new Set(
      family.graph.edges.map((e) => e.source + "→" + e.target + ":" + e.name),
    ),
    flowB = new Set(
      variant.graph.edges.map((e) => e.source + "→" + e.target + ":" + e.name),
    );
  $("#comparetitle").textContent = "Reference → " + variant.name;
  $("#diffsummary").innerHTML =
    `<div class="diff-counts"><span><b>${changes.filter((c) => c.type === "added").length}</b> added</span><span><b>${changes.filter((c) => c.type === "removed").length}</b> removed</span><span><b>${changes.filter((c) => c.type === "changed").length}</b> changed</span><span><b>${[...flowB].filter((e) => !flowA.has(e)).length}</b> new flow connections</span>${analysis ? `<span class="${analysis.sound ? "text-success" : "text-warning"}">${analysis.sound ? "Sound control flow" : "Behavior needs review"}</span>` : ""}</div><div class="diff-items">${changes.map((c) => `<span class="${c.type}">${esc(c.type)}: ${esc(c.name)}</span>`).join("")}</div>`;
  $("#comparemodal").showModal();
  for (const [container, source, isBase] of [
    ["#basecompare", family.xml, true],
    ["#variantcompare", variant.xml, false],
  ]) {
    $(container).innerHTML = "";
    const view = new Viewer({ container: $(container) });
    comparisonViewers.push(view);
    await view.importXML(source);
    view.get("canvas").zoom("fit-viewport", "auto");
    for (const c of changes)
      if (view.get("elementRegistry").get(c.id))
        view.get("canvas").addMarker(c.id, "diff-" + c.type);
  }
}
let aiStatus = {
  configured: false,
  provider: "ollama",
  baseUrl: "http://localhost:11434",
  model: "",
};
let generationCandidate = null,
  generationPreview = null;
const naturalSamples = {
  onboarding:
    "A customer submits an account application. The system verifies their identity. If the application is approved, the team prepares a contract while the system opens the account in parallel. After both are done, welcome the customer. If it is rejected, explain the rejection. Finally, archive the application.",
  procurement:
    "The requester submits a purchase requisition. Finance approves the budget. Procurement evaluates the supplier while Operations checks stock availability in parallel. After both checks, Procurement issues a purchase order. Operations confirms receipt, Finance reconciles the invoice, and the system schedules payment.",
  insurance:
    "Register an insurance claim and check policy coverage. If it is covered, assess the damage. If fraud review is required, investigate the claim; otherwise estimate the settlement. Authorize payment after this review. If the claim is not covered, explain the coverage decision. Close the claim at the end.",
};
$("#generatorform").insertAdjacentHTML(
  "afterbegin",
  `<div class="generation-mode"><label class="field-label">Description mode<select id="gmode"><option value="natural">Natural language · connected model</option><option value="structured">Structured language · offline compiler</option></select></label><button id="modelsettings" type="button" class="text-button">Model settings</button></div><div id="modelnotice" class="model-notice"></div>`,
);
$("#gname")
  .closest("label")
  .insertAdjacentHTML(
    "beforebegin",
    `<label class="example-picker">Example workflows<select id="examples"><option value="">Load an example…</option>${Object.entries(
      samples,
    )
      .map(([id, v]) => `<option value="${id}">${esc(v.name)}</option>`)
      .join("")}</select></label>`,
  );
$("#examples").onchange = () => {
  const id = $("#examples").value;
  if (!id) return;
  $("#gname").value = samples[id].name;
  $("#gsource").value =
    $("#gmode").value === "natural" ? naturalSamples[id] : samples[id].source;
  invalidateGeneration();
  updateLineCount();
  $("#examples").value = "";
};
$("#generatorform").insertAdjacentHTML(
  "beforeend",
  '<div id="generationreview" hidden></div>',
);
$('#generatorform button[type="submit"]').innerHTML =
  "Generate diagram " + icon("chevron");
$(".library-bottom").insertAdjacentHTML(
  "afterbegin",
  `<button id="openmodelsettings">${icon("settings")} Model settings</button>`,
);
document.body.insertAdjacentHTML(
  "beforeend",
  `<dialog id="modeldialog" class="model-dialog"><div class="dialog-header"><div><div class="eyebrow">GENERATION ENGINE</div><h2>Connect your model.</h2></div><button id="closemodel" class="icon-button" aria-label="Close model settings">${icon("close")}</button></div><form id="modelform"><p>Use a local Ollama model or your own OpenAI-compatible chat endpoint. The business description is sent only when you request generation.</p><label class="field-label">Provider<select id="aiprovider"><option value="ollama">Ollama · local model</option><option value="openai-compatible">OpenAI-compatible · chat completions</option></select></label><label class="field-label">API base URL<input id="aiurl" required placeholder="http://localhost:11434"></label><label class="field-label">Installed model name<input id="aimodel" required placeholder="Enter the model available on your endpoint"></label><label class="field-label">API key (remote providers)<input id="aikey" type="password" autocomplete="off" placeholder="Leave blank to keep current key"></label><div class="model-storage-note">Keys stay in server process memory and are never returned to the browser or included in backups. Restarting the server resets settings unless configured through environment variables.</div><div id="modeltestresult" role="status"></div><div class="recipe-controls"><button id="testmodel" type="button" class="outline">Test connection</button><button type="submit" class="solid">Save configuration</button></div><details><summary>Local setup</summary><p>Install Ollama from its official website, start it, and pull a model that supports reliable JSON generation. Enter that exact model name above. The application does not bundle or download model weights.</p></details></form></dialog>`,
);
function invalidateGeneration() {
  generationCandidate = null;
  $("#generationreview").hidden = true;
}
function generationSignature() {
  return JSON.stringify({
    name: $("#gname").value,
    source: $("#gsource").value,
    mode: $("#gmode").value,
  });
}
function updateModelNotice() {
  const guide = $(".authoring-guide");
  guide.innerHTML =
    $("#gmode").value === "natural"
      ? `<div class="eyebrow">BUSINESS DESCRIPTION → BPMN</div><h3>Your process.<br>Your words.</h3><p>Describe the real work, who performs it, and what happens when decisions go either way. The connected model creates a graph from this text; structural and behavior checks run before preview.</p><div class="syntax-example"><b>Include the essentials</b><code>What starts the process?<br>Who performs each activity?<br>What can happen at each decision?<br>Which tasks run in parallel?<br>What marks completion?</code><b>Review the assumptions</b><code>AI generation can misinterpret business meaning. The preview makes the result reviewable before it becomes a saved family.</code></div><p class="fine-print">Description content is sent to your configured endpoint. Unsupported loop, timer or multi-pool requirements must be reviewed as approximations.</p>`
      : `<div class="eyebrow">EXPLICIT LANGUAGE → BPMN</div><h3>Precise steps.<br>Predictable structure.</h3><p>The offline compiler translates your current input directly. It does not select a sample based on keywords.</p><div class="syntax-example"><b>Activity</b><code>user: Review request<br>service: Verify identity</code><b>Decision</b><code>if Approved?<br>  Prepare contract<br>else<br>  Explain rejection<br>endif</code><b>Parallel work</b><code>parallel<br>  Check inventory<br>branch<br>  Check credit<br>endparallel</code><b>Swimlane</b><code>user[Finance]: Approve budget</code></div>`;

  const natural = $("#gmode").value === "natural";
  $("#syntaxhint").textContent = natural
    ? "Your text is sent to the connected model. Review its interpretation before saving."
    : "One activity per line. Explicit blocks keep decisions unambiguous.";
  $("#modelnotice").innerHTML = natural
    ? aiStatus.configured
      ? `Model: <b>${esc(aiStatus.model)}</b> · description sent to ${esc(aiStatus.baseUrl)}. Review generated assumptions before saving.`
      : "No model connected. Open Model settings, or choose Structured language for offline generation."
    : "Offline compiler. One activity per line; explicit if / else / endif and parallel blocks. Changes are compiled from your current text.";
  $('#generatorform button[type="submit"]').innerHTML =
    (natural && !aiStatus.configured ? "Connect a model" : "Generate diagram") +
    " " +
    icon("chevron");
}
async function openModelSettings() {
  aiStatus = await api("ai/status");
  $("#aiprovider").value = aiStatus.provider;
  $("#aiurl").value = aiStatus.baseUrl;
  $("#aimodel").value = aiStatus.model;
  $("#aikey").value = "";
  $("#aikey").placeholder = aiStatus.keyConfigured
    ? "Key configured · blank keeps it"
    : "API key, if required";
  $("#modeltestresult").textContent = "";
  $("#modeldialog").showModal();
}
$("#modelsettings").onclick = run(openModelSettings);
$("#openmodelsettings").onclick = run(openModelSettings);
$("#closemodel").onclick = () => $("#modeldialog").close();
$("#aiprovider").onchange = () => {
  $("#aiurl").value =
    $("#aiprovider").value === "ollama"
      ? "http://localhost:11434"
      : "https://api.openai.com/v1";
};
async function saveModelConfig() {
  aiStatus = await api("ai/config", {
    provider: $("#aiprovider").value,
    baseUrl: $("#aiurl").value,
    model: $("#aimodel").value,
    apiKey: $("#aikey").value || null,
  });
  $("#aikey").value = "";
  updateModelNotice();
}
$("#modelform").onsubmit = run(async () => {
  await saveModelConfig();
  $("#modeldialog").close();
  notify("Model configuration saved for this server session.");
});
$("#testmodel").onclick = run(async () => {
  await saveModelConfig();
  const result = await api("ai/test", {});
  $("#modeltestresult").textContent = result.message;
});
function openGenerator(sample = null, fresh = false) {
  if (sample) {
    $("#gname").value = samples[sample].name;
    $("#gsource").value =
      $("#gmode").value === "natural"
        ? naturalSamples[sample]
        : samples[sample].source;
  } else if (!fresh && family?.source) {
    $("#gname").value = family.name + " · revised";
    $("#gsource").value = family.source;
    $("#gmode").value =
      family.generation?.mode === "natural-language" ? "natural" : "structured";
  } else {
    $("#gname").value = "";
    $("#gsource").value = "";
  }
  $("#generationerror").hidden = true;
  invalidateGeneration();
  updateLineCount();
  updateModelNotice();
  $("#generator").showModal();
}
function updateLineCount() {
  $("#linecount").textContent = $("#gsource").value.length + " characters";
}
$("#gsource").oninput = () => {
  updateLineCount();
  invalidateGeneration();
};
$("#gname").oninput = invalidateGeneration;
$("#gmode").onchange = () => {
  invalidateGeneration();
  updateLineCount();
  updateModelNotice();
};
$("#generatorform").onsubmit = run(async () => {
  if ($("#gmode").value === "natural" && !aiStatus.configured) {
    await openModelSettings();
    return;
  }
  try {
    invalidateGeneration();
    const signature = generationSignature(),
      name = $("#gname").value.trim(),
      source = $("#gsource").value;
    const candidate = await api(
      $("#gmode").value === "natural" ? "generate" : "compile",
      { name, source },
    );
    const xml = await layout(candidate.xml);
    if (generationSignature() !== signature)
      throw Error(
        "The description changed while generating. Generate again from the updated text.",
      );
    generationCandidate = {
      ...candidate,
      xml,
      name,
      source: candidate.source ?? source,
      signature,
    };
    $("#generationerror").hidden = true;
    $("#generationreview").hidden = false;
    $("#generationreview").innerHTML =
      `<div class="generation-review-heading"><div><span class="eyebrow">REVIEW BEFORE SAVING</span><h3>${candidate.graph.nodes.length} elements · ${candidate.graph.edges.length} flows</h3></div><span class="text-success">${candidate.analysis.sound ? "Sound control flow" : "Review analysis"}</span></div><div id="generationpreview"></div>${candidate.assumptions?.length ? `<div class="generation-assumptions"><b>Model assumptions / approximations</b><ul>${candidate.assumptions.map((a) => `<li>${esc(a)}</li>`).join("")}</ul></div>` : ""}<p class="body-small">Review whether this captures your business meaning. Validation checks control flow, not whether the model interpreted every requirement correctly.</p><button id="commitgeneration" class="solid wide">Create this process family</button>`;
    generationPreview?.destroy();
    generationPreview = new Viewer({ container: $("#generationpreview") });
    await generationPreview.importXML(xml);
    generationPreview.get("canvas").zoom("fit-viewport", "auto");
    const trace = candidate.generation?.traceability || [];
    if (trace.length) {
      $("#generationreview").insertAdjacentHTML(
        "beforeend",
        `<details class="source-map"><summary>${trace.length} activities linked to source evidence</summary>${trace.map((t) => `<div><b>${esc(t.name)}</b><blockquote>${esc(t.quote)}</blockquote><small>${esc(t.id)} · characters ${t.start}–${t.end}</small></div>`).join("")}</details>`,
      );
    }
    $("#commitgeneration").onclick = run(async () => {
      if (
        !generationCandidate ||
        generationCandidate.signature !== generationSignature()
      )
        throw Error("Generate again after changing the description.");
      if (!(await canLeave())) return;
      const c = generationCandidate;
      family = await api("families", {
        name: c.name,
        source: c.source,
        xml: c.xml,
        generation: c.generation || {
          mode: "structured",
          provider: "offline-compiler",
          model: "",
        },
        assumptions: c.assumptions || [],
      });
      selected = null;
      dirty = false;
      localStorage.setItem("process-studio.last-family", family.id);
      $("#generator").close();
      await showFamily();
      notify("Process family created from the reviewed description.");
    });
    $("#generationreview").scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  } catch (e) {
    $("#generationerror").hidden = false;
    $("#generationerror").textContent = e.message;
    throw e;
  }
});
$$("[data-sample]").forEach(
  (b) =>
    (b.onclick = () => {
      $("#gname").value = samples[b.dataset.sample].name;
      $("#gsource").value =
        $("#gmode").value === "natural"
          ? naturalSamples[b.dataset.sample]
          : samples[b.dataset.sample].source;
      invalidateGeneration();
      updateLineCount();
    }),
);
$$("[data-close]").forEach(
  (b) => (b.onclick = () => $("#" + b.dataset.close).close()),
);
$$("[data-panel]").forEach(
  (b) =>
    (b.onclick = () => {
      if (panel === "variants") keepRecipe();
      setPanel(b.dataset.panel);
    }),
);
$("#new").onclick = () => openGenerator(null, true);
$("#createfromtext").onclick = () => openGenerator();
$("#emptycreate").onclick = () => openGenerator(null, true);
$("#emptysample").onclick = () => openGenerator("onboarding");
$("#guide").onclick = () => openGenerator("onboarding");
$("#searchfamilies").oninput = run(refreshLibrary);
$("#newvariant").onclick = run(async () => {
  assertFamily();
  if (!(await canLeave())) return;
  if (panel === "variants") keepRecipe();
  selected = null;
  await showFamily();
  setPanel("variants");
});
$("#save").onclick = run(saveBase);
$("#undo").onclick = () => {
  if (!selected && !sim) modeler.get("commandStack").undo();
};
$("#redo").onclick = () => {
  if (!selected && !sim) modeler.get("commandStack").redo();
};
$("#fit").onclick = () => family && fitDiagram(editor());
$("#zoomin").onclick = () =>
  family &&
  editor()
    .get("canvas")
    .zoom(Math.min(3, editor().get("canvas").zoom() * 1.25));
$("#zoomout").onclick = () =>
  family &&
  editor()
    .get("canvas")
    .zoom(Math.max(0.1, editor().get("canvas").zoom() / 1.25));
$("#zoomreset").onclick = () => family && editor().get("canvas").zoom(1);
$("#togglepanel").onclick = () => {
  $(".workbench").classList.toggle("inspector-closed");
  editor().get("canvas").resized();
};
$("#autolayout").onclick = run(async () => {
  assertBase();
  const { xml } = await modeler.saveXML({ format: true });
  const arranged = await arrangeXML(xml);
  loading = true;
  try {
    await modeler.importXML(arranged);
    dirty = true;
    renderStatus();
    fitDiagram(modeler, true);
  } finally {
    loading = false;
  }
  const { xml: recovery } = await modeler.saveXML({ format: true });
  localStorage.setItem(
    draftKey(),
    JSON.stringify({
      xml: recovery,
      revision: family.revision,
      at: Date.now(),
    }),
  );
  notify("Diagram arranged. Review and save the base.");
});
$("#compare").onclick = run(async () => {
  assertFamily();
  const v = currentVariant();
  if (!v) throw Error("Select a variant to compare with the base.");
  if (dirty) throw Error("Save the base before comparing it.");
  await showComparison({ ...v, xml: await layout(v.xml, true) });
});
$("#exportbpmn").onclick = run(async () => {
  assertFamily();
  if (currentVariant()?.status === "conflict")
    throw Error("Repair this variant before exporting its diagram.");
  const { xml } = await editor().saveXML({ format: true });
  download(
    (currentVariant()?.name || family.name) + ".bpmn",
    xml,
    "application/xml",
  );
});
$("#exportsvg").onclick = run(async () => {
  assertFamily();
  const { svg } = await editor().saveSVG();
  download(
    (currentVariant()?.name || family.name) + ".svg",
    svg,
    "image/svg+xml",
  );
});
$("#importbpmn").onclick = () => $("#bpmnfile").click();
$("#restorebackup").onclick = () => $("#backupfile").click();
$("#bpmnfile").onchange = run(async (e) => {
  try {
    const file = e.target.files[0];
    if (!file || !(await canLeave())) return;
    if (file.size > 2_000_000) throw Error("BPMN imports are limited to 2 MB.");
    let xml = await file.text();
    const checked = await api("compile", { xml });
    if (!xml.includes("BPMNShape")) xml = await layout(checked.xml);
    family = await api("families", {
      name: file.name.replace(/\.(bpmn|xml)$/i, ""),
      xml,
    });
    selected = null;
    dirty = false;
    await showFamily();
    notify("BPMN imported as a new family.");
  } finally {
    e.target.value = "";
  }
});
$("#backupfile").onchange = run(async (e) => {
  try {
    const file = e.target.files[0];
    if (!file || !(await canLeave())) return;
    if (file.size > 10_000_000) throw Error("Backups are limited to 10 MB.");
    family = await api("import-backup", {
      backup: JSON.parse(await file.text()),
    });
    selected = null;
    dirty = false;
    await showFamily();
    notify(
      "Backup restored into a new family. Existing families were preserved.",
    );
  } finally {
    e.target.value = "";
  }
});
window.addEventListener("beforeunload", (e) => {
  if (dirty) {
    e.preventDefault();
    e.returnValue = "";
  }
});
window.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
    e.preventDefault();
    if (family && !selected && !sim) run(saveBase)();
  }
  if (
    e.key.toLowerCase() === "n" &&
    !e.ctrlKey &&
    !e.metaKey &&
    !["INPUT", "TEXTAREA", "SELECT"].includes(
      document.activeElement?.tagName,
    ) &&
    !$$("dialog[open]").length
  ) {
    e.preventDefault();
    openGenerator();
  }
});
async function boot() {
  renderStatus();
  renderVariantTabs();
  renderPanel();
  aiStatus = await api("ai/status");
  updateModelNotice();
  const health = await api("health");
  $("#connection").textContent =
    health.status === "ok" ? "Local workspace" : "Unavailable";
  const fs = await refreshLibrary();
  const id = localStorage.getItem("process-studio.last-family");
  if (fs.length) {
    family = await api(
      "families/" + (fs.find((f) => f.id === id)?.id || fs[0].id),
    );
    await showFamily();
  }
}
run(boot)();
