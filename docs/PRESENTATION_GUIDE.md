# Final-project presentation and viva

## Defensible project statement

“We built a process-family workbench that turns descriptions into reviewable BPMN models, links generated activities to their source, derives contextual variants through explicit operations, and checks control-flow behavior while preserving changes and recovery history.”

The research contribution is an integrated, evaluated engineering artifact. Do not claim to have invented BPMN, Provop, LLM generation, formal verification, or an enterprise process engine.

## Suggested demonstration

1. Explain duplication across country/product/customer processes and why a family plus recipes helps.
2. Show your configured model endpoint. Enter a new natural-language description, generate, inspect source quotes/assumptions, and accept the preview. Change the text and show the output changes. If endpoint access is unavailable, explicitly switch to the structured offline compiler; do not claim that demo is LLM inference.
3. Select a task, inspect source evidence, change its documentation or type, and save a base revision.
4. Create a contextual variant using the visual recipe builder. Preview, save and compare it with the base.
5. Change the base so a recipe target disappears. Show the impact warning, retained conflict, and repaired target. Restore a historical base if helpful.
6. Run family validation, explain the manifest fingerprint, then simulate a decision and parallel synchronization.
7. Export BPMN, backup the family, restore into a new family and show history/audit continuity.
8. Finish with test evidence and supported-scope boundaries.

## Questions

**Is it hardcoded?** No. The offline compiler processes current explicit syntax. The natural-language adapter submits the current description to the chosen model and validates its returned graph. Examples only populate editable input. Contract and browser tests check changed descriptions and preview invalidation.

**How do you reduce invented work?** Every generated activity needs an exact quote in the supplied description. A validator-guided repair is allowed once. Quotes and assumptions are displayed for human review. Matching a quote does not prove that the interpretation is right.

**Why is the process sound?** Only a fully explored model within the supported subset can pass. Token-state exploration checks completion, residual tokens, deadlocks and dead activities. Incomplete exploration never counts as sound. Data conditions and time semantics are excluded.

**Why stable IDs?** Recipe targets and traceability refer to IDs. Visual type replacement preserves activity identity; inserted activities use operation-specific IDs so reordering recipes does not rename them.

**What does the fingerprint prove?** It identifies the exact graph/recipe/version manifest checked by this analyzer. It is a reproducibility aid, not a signature, security attestation or regulatory certificate.

**Is it industry-ready?** It is prepared for trusted local single-user process modeling. Organizational authentication, collaboration, public deployment and production workflow execution need additional architecture and independent evaluation. Stating these boundaries is part of the engineering work.

**What backs it?** BPMN 2.0 interchange and bpmn-js; Provop-inspired operations; VIVACE lifecycle framing; recent text-to-model literature motivating structured outputs, repair and explicit semantic review. See PROJECT_REPORT.md for sources.
