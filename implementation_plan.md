# UI Polish & Refinement Plan

This plan details the exact adjustments needed to achieve the highly polished, Anthropic/Apple-inspired minimalist aesthetic. All changes focus purely on spacing, typography, alignment, and removing unnecessary visual noise (borders, attributions, excessive saturation). 

## User Review Required

> [!NOTE]
> Please review the specific padding and spacing changes below. If you approve, I will execute these across all components.

## Proposed Changes

---

### Global Design System (`index.css`)
- Set `--radius` to `1.125rem` (18px) for a consistent, soft modern appearance.
- Set `--shadow-md` strictly to `0 2px 12px rgba(0,0,0,0.04)`.
- Enforce the 8px/16px/24px spacing grid natively via Tailwind classes (`gap-2`, `gap-4`, `gap-6`, `p-6`).

### Component Refinements

#### [MODIFY] `command-post/web/src/components/MapPanel.jsx`
- Disable the MapLibre attribution entirely (`attributionControl: false`).
- Add slightly more padding inside the overlay cards.

#### [MODIFY] `command-post/web/src/components/Masthead.jsx`
- Reduce the overall height by adjusting padding (`py-3` or `py-4`).
- Vertically center align controls tightly.
- Simplify status chips (remove heavy borders, use softer background fills).

#### [MODIFY] `command-post/web/src/components/IncidentQueue.jsx`
- Reduce card height by 25-30% by condensing internal padding (`py-3 px-4`).
- Make the severity badge a prominent visual anchor on the left.
- Make the incident title the primary visual focus (slightly larger and bolder).
- Reduce the opacity of the secondary metadata and format it purely as uppercase tags.
- Increase the spacing between cards (`gap-4`).

#### [MODIFY] `command-post/web/src/components/IncidentDetail.jsx`
- Increase internal padding to `px-12 py-10` to give the content immense breathing room.
- Replace heavy section borders with subtle dividers (`border-t border-border/40`).
- Make the Dispatch button stronger with `px-8 py-4`, `rounded-[18px]`, and an explicit hover state (`hover:-translate-y-0.5 hover:shadow-md transition-all`).

#### [MODIFY] `command-post/web/src/components/ResourceStatusPanel.jsx`
- Increase internal padding (`p-6`).
- Standardize font sizes to reduce visual jumps between the label and the value.
- Tightly align the label grid to reduce dead space.

#### [MODIFY] `command-post/web/src/components/StatusBar.jsx`
- Replace stark dividers with subtle ones (`divide-border/50`).
- Mute inactive states entirely (e.g., GPS ok is a very soft olive rather than bright green).
- Tightly align all indicators.

## Verification Plan

### Manual Verification
- Visual inspection via browser DOM snapshots to confirm the spacing system is uniformly 8/16/24px.
- Confirm the OpenStreetMap text is removed.
- Verify that borders only exist on major containers and the internal components use whitespace for hierarchy.
