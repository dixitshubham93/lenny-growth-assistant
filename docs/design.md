# Design Document
## The Lenny Growth Assistant

**Version:** 0.1 — Discovery Placeholder  
**Status:** Phase 1b — Outline Only. Detailed UI design happens in Phase 9.  
**Source of Truth:** [docs/Assigment.md](./Assigment.md)  
**Last Updated:** 2026-08-26

> [!NOTE]
> This document is a discovery-level placeholder. The detailed UI/UX design, interaction states,
> responsive behaviour, and accessibility decisions will be specified in Phase 9, after the backend
> and agent layer are validated. The sections below record early principles and known constraints
> that must be reflected in the final design.

---

## 1. UI/UX Principles (Early Decisions)

1. **Clarity over cleverness** — The user came to solve a product problem, not to explore a UI. Every element earns its place.
2. **Trust through transparency** — Source citations are always visible; the active LLM provider/model is always indicated. The user knows what the assistant is drawing on.
3. **Artifact as a first-class citizen** — The Artifact Viewer is not a secondary pane or a modal. It sits beside the chat as an equal panel when an artifact is present.
4. **Conversation is the interface** — The chat experience is primary. Skills and artifact generation are accessible but not intrusive.
5. **Fail gracefully and honestly** — Error states are informative, not generic. If the assistant cannot answer, it says so clearly rather than producing a confident-sounding non-answer.

---

## 2. Information Architecture (Intended — to be finalised in Phase 9)

```
┌────────────────────────────────────────────────────────┐
│                   Application Shell                     │
│  ┌───────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │ Session   │  │   Chat Panel    │  │  Artifact    │ │
│  │ Sidebar   │  │                 │  │  Viewer      │ │
│  │           │  │  Messages       │  │  (conditional│ │
│  │ - New     │  │  Source cites   │  │   panel)     │ │
│  │   session │  │  Input box      │  │              │ │
│  │ - Session │  │  Ship30 toggle  │  │  Markdown or │ │
│  │   list    │  │  Provider badge │  │  sandboxed   │ │
│  │           │  │                 │  │  iframe      │ │
│  └───────────┘  └─────────────────┘  └──────────────┘ │
└────────────────────────────────────────────────────────┘
```

**Three-panel layout (desktop primary):**
- Left: Session sidebar (collapsible)
- Centre: Chat panel (always visible)
- Right: Artifact Viewer (visible only when an artifact is active)

---

## 3. Key Interaction States (to be detailed in Phase 9)

| State | Notes |
|-------|-------|
| Empty session | Prompt the user with example questions |
| Loading / streaming response | Visible indicator; do not block input |
| Grounded response with citations | Citations rendered below the message |
| Ship 30 skill active | Clear indication the essay skill is on |
| Artifact generated | Artifact Viewer opens; renders beside chat |
| Insufficient evidence | Honest message; no hallucinated answer |
| LLM provider error | User-facing error with retry guidance |
| New session created | Chat panel clears; session appears in sidebar |

---

## 4. Artifact Viewer Security (Confirmed Design Constraint)

This is a confirmed design constraint, not a detail to be deferred.

- **HTML artifacts:** Rendered inside a `<iframe srcdoc="...">` with `sandbox` attribute.
  The sandbox will NOT include `allow-scripts`. JavaScript is fully blocked.
- **Markdown artifacts:** Rendered via `react-markdown` with `rehype-sanitize`.
  Raw HTML passthrough is disabled.
- **What the evaluator should see:** A clearly rendered document beside the chat.
  Not a raw code block. Not a new browser tab.
- **Security documentation:** The design.md (when complete) must explain what is permitted,
  what is blocked, and why — so an evaluator can verify the isolation strategy.

---

## 5. Responsive Behaviour (Intent)

- Desktop (≥ 1024px): Three-panel layout as described in §2
- Tablet (768px – 1023px): Session sidebar collapses to icon rail; artifact viewer slides over chat when active
- Mobile (< 768px): Single-panel; session sidebar is a drawer; artifact viewer replaces chat panel when active

*Detailed breakpoints and layout specifications: Phase 9.*

---

## 6. Accessibility (Intent)

- Keyboard navigation for all interactive elements
- ARIA labels on all icon-only controls
- Focus management on panel transitions
- Sufficient colour contrast (WCAG AA minimum)
- Screen reader compatibility for chat messages and source citations

*Detailed accessibility audit and remediation: Phase 9.*

---

## 7. Open Design Questions (for Phase 9)

| # | Question |
|---|----------|
| DQ1 | Should the Ship 30 toggle be a button in the input area or a sidebar control? |
| DQ2 | How should source citations be displayed — inline links, footnotes, or an expandable panel? |
| DQ3 | Should the LLM provider/model indicator be in the header, input area, or sidebar? |
| DQ4 | Should the Artifact Viewer be a resizable panel or fixed-width? |
| DQ5 | How should multiple artifacts within a session be navigated? |
| DQ6 | What is the empty-state experience that best prompts a first-time user? |

---

*Detailed UI/UX design, component specifications, and interaction patterns will be added in Phase 9.*

## 5. Artifact Security & Rendering Isolation

The artifact viewer is designed to render generated content (like Ship 30 essays) securely inside a client-side environment. Since LLMs can theoretically generate arbitrary or malicious HTML/JavaScript, the application must aggressively sandbox all generated content.

### Implementation Details:
1. **HTML Isolation via Iframe Sandboxing:** 
   When the agent returns an HTML artifact, the frontend injects it directly into a visually seamless `<iframe>` element. 
   The iframe is secured using the HTML5 `sandbox` attribute:
   ```html
   <iframe 
     sandbox="allow-same-origin"
     title="Generated HTML artifact">
   </iframe>
   ```
2. **What is Blocked:** 
   Script execution (`allow-scripts` is intentionally omitted). The artifact cannot execute JavaScript, spawn popups, submit forms, or access the parent window's DOM or HTTP session cookies.
3. **What is Permitted:** 
   Native HTML styling and CSS layout. The `allow-same-origin` tag permits the iframe contents to retain structural CSS rules while remaining completely inert defensively.
4. **Markdown Fallback:** 
   If the artifact generated is pure Markdown (such as the Ship 30 writing skill mode), it is sanitized and parsed locally via an inert Javascript Markdown engine (`marked.js`), guaranteeing strict content isolation.

### Why this approach was chosen:
Containerizing generated content within an iframe sandbox provides the highest level of security known for web rendering. Attempting to parse and sanitize dynamic HTML via Regex or DOM purification is notoriously flaky. An iframe effectively transfers the security burden directly to the browser's deeply tested process isolation boundaries.
