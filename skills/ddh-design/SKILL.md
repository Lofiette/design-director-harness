---
name: ddh-design
description: Design or review product flows, forms, dense work interfaces and responsive screens. Produce interaction states, design system decisions, visual acceptance criteria and handoff.
---

# Design direction

1. Establish who is doing what, the real entry point, the product constraint and the source of design authority. Inspect existing UI or source evidence before proposing a change. For reference-led work, extract observable rules for layout, type, density, imagery, motion and brand. Route consequential gaps through ddh-direct intake before writing dependent design, including drafts.
2. Choose the interaction pattern by task frequency, consequence of error, information density and recovery needs. For a form, remove fields the system can derive and specify validation, focus, retry and save behavior. For a professional interface, cover keyboard use, selection, bulk actions and partial failure when applicable.
3. Specify the normal path and relevant empty, loading, error, permission, success and responsive states. Reuse design tokens and components. Document meaningful exceptions and identify their owner.
4. Execute with an available design, image, browser or code tool. Select the smallest tool surface for the artifact. For a configured Console provider, use [the Figma Console route](references/figma-console.md). Capture the rendered view at representative widths and exercise the relevant states. Check keyboard flow, focus, semantics, contrast and motion as applicable.
5. When a CPT design specialist is available and can answer a distinct question, load its method for that gap. Use `cpt-accessibility-review` for semantics or keyboard flow, `cpt-design-system-governance` for a component or token exception, and `cpt-professional-data-interface-design` for dense operator workflows. Give the specialist the current criteria and scope, then fold the result into the same design and acceptance record.
6. Hand off the source reference, named components and tokens, state and responsive behavior, acceptance checks, captured evidence and remaining gaps. Use [the acceptance matrix](references/acceptance.md) when reviewing implementation or a complex flow.
