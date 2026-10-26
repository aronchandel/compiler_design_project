---
name: cpp2py IDE
colors:
  surface: '#10141a'
  surface-dim: '#10141a'
  surface-bright: '#353940'
  surface-container-lowest: '#0a0e14'
  surface-container-low: '#181c22'
  surface-container: '#1c2026'
  surface-container-high: '#262a31'
  surface-container-highest: '#31353c'
  on-surface: '#dfe2eb'
  on-surface-variant: '#cbc3d7'
  inverse-surface: '#dfe2eb'
  inverse-on-surface: '#2d3137'
  outline: '#958ea0'
  outline-variant: '#494454'
  surface-tint: '#d0bcff'
  primary: '#d0bcff'
  on-primary: '#3c0091'
  primary-container: '#a078ff'
  on-primary-container: '#340080'
  inverse-primary: '#6d3bd7'
  secondary: '#5de6ff'
  on-secondary: '#00363e'
  secondary-container: '#00cbe6'
  on-secondary-container: '#00515d'
  tertiary: '#4edea3'
  on-tertiary: '#003824'
  tertiary-container: '#00a572'
  on-tertiary-container: '#00311f'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#e9ddff'
  primary-fixed-dim: '#d0bcff'
  on-primary-fixed: '#23005c'
  on-primary-fixed-variant: '#5516be'
  secondary-fixed: '#a2eeff'
  secondary-fixed-dim: '#2fd9f4'
  on-secondary-fixed: '#001f25'
  on-secondary-fixed-variant: '#004e5a'
  tertiary-fixed: '#6ffbbe'
  tertiary-fixed-dim: '#4edea3'
  on-tertiary-fixed: '#002113'
  on-tertiary-fixed-variant: '#005236'
  background: '#10141a'
  on-background: '#dfe2eb'
  surface-variant: '#31353c'
typography:
  headline-xl:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.015em
  headline-md:
    fontFamily: Inter
    fontSize: 15px
    fontWeight: '600'
    lineHeight: 20px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '600'
    lineHeight: 18px
    letterSpacing: -0.005em
  body-lg:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-md:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  code-lg:
    fontFamily: JetBrains Mono
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 22px
  code-md:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 20px
  code-sm:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '400'
    lineHeight: 16px
  label-md:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.02em
  label-sm:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 14px
    letterSpacing: 0.04em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 0.5rem
  gutter-split: 0.25rem
  margin: 0.75rem
  margin-mobile: 0.5rem
  space-xs: 0.25rem
  space-sm: 0.375rem
  space-md: 0.5rem
  space-lg: 0.75rem
  space-xl: 1rem
---

## Brand & Style

This design system embodies the precision, technical depth, and hyper-efficient clarity required by performance engineers and systems developers translating critical C++ codebases into modern Python. Drawing direct lineage from high-performance developer tools, terminal emulators, and contemporary cloud IDEs, the interface projects an aura of surgical accuracy, non-distracting utility, and latent computational power.

The visual style blends **Technical Minimalism** with **Instrument-Grade Functionalism**:
- **Dense, purposeful ergonomics:** Visual chrome is aggressively minimized, prioritizing maximum viewport canvas for dual-pane side-by-side transpilation buffers, AST visualizers, and compilation telemetry.
- **Deep architectural contrast:** The environment stays grounded in profound dark canvas tones, using crisp boundaries to delineate complex workbench tiles without visual heaviness.
- **Vibrant precision accents:** High-chroma electric violet and cyan serve as functional beacons for compilation state transitions, semantic parsing feedback, and live diff highlights, avoiding decorative noise.

## Colors

The palette is engineered for prolonged sessions in low-light environments, prioritizing legibility, code token differentiation, and zero eye fatigue.

- **Background & Canvas (`#0D1117`):** The absolute ground layer across the primary IDE workspace and editor canvas.
- **Panels & Shell Chrome (`#161B22`):** Structural panels including sidebars, terminal docks, inspector drawers, and tab strips.
- **Elevated Surfaces (`#21262D`):** Dropdown menus, tooltips, command palettes, and active tab highlights.
- **Structural Outlines (`#30363D`):** 1px boundaries dividing panes, gutter dividers, splitters, and cards.
- **Primary Accent (`#8B5CF6` - Electric Violet):** Primary interactive actions, active build states, compilation dispatch triggers, and primary focus rings.
- **Secondary Accent (`#22D3EE` - Cyan):** AST links, type inference annotations, Python target symbols, and informational diagnostics.
- **Success (`#10B981` - Emerald):** Zero compilation errors, verified benchmark parity, successful unit tests.
- **Warning (`#F59E0B` - Amber):** Transpiler performance degradation hints, manual memory deallocation warnings, type coercion notices.
- **Danger / Error (`#EF4444` - Crimson):** C++ compilation fatal errors, unresolved linkage, syntax parsing crashes.
- **Text & Data Tokens:**
  - Foreground Primary: `#F0F6FC`
  - Foreground Muted: `#8B949E`
  - Foreground Disabled / Gutter: `#484F58`

## Typography

Typography prioritizes information density, strict tabular alignment, and zero ambiguity between visually similar glyphs (`0` vs `O`, `l` vs `1`).

- **Interface Shell (Inter):** Applied across global menus, breadcrumbs, modal dialogs, status alerts, and property inspectors. Its neutral grotesque geometry prevents eye fatigue and sits cleanly against dense monospaced viewports.
- **Code & Machine Metadata (JetBrains Mono):** Applied inside C++ source buffers, converted Python targets, terminal stdout/stderr channels, diff views, assembly inspectors, AST tables, and numeric memory addresses. Features ligatures optimized for programming (`->`, `::`, `=>`, `!=`, `==`).

## Layout & Spacing

The layout utilizes a strict, dock-oriented tile and panel system designed for zero wasted screen surface.

- **Workspace Paneling:** Built on dynamic multi-split panes (Horizontal and Vertical splits). Editor panes conform to flexible 50/50 split views with interactive 4px resizable sash dividers (`gutter-split`).
- **Density Profile:** Compact IDE density. Default toolbars, tab headers, tree nodes, and breadcrumbs occupy compact heights (28px to 32px), preserving maximum vertical space for lines of code.
- **Breakpoints & Adaptation:**
  - **Desktop (>1024px):** Dual synchronized code viewports (Source C++ vs Target Python), collapsible sidebar (File Explorer, Symbol AST, Settings), bottom console/terminal pane.
  - **Tablet (768px - 1023px):** Side-by-side or stacked tabbed editors; side panel docks automatically into icon-rail mode.
  - **Mobile (<768px):** Toggle-switched view (C++ tab or Python tab), bottom navigation sheet for compilation diagnostics.

## Elevation & Depth

Visual hierarchy is maintained through **Tonal Surface Stacking** and **Crisp Structural Outlines** rather than diffused shadows, mirroring the engineering aesthetic of professional IDE environments.

- **Level 0 (Workspace Canvas):** `#0D1117` with flush surfaces for raw code editors.
- **Level 1 (Docked Containers & Toolbars):** `#161B22` enclosed by `1px solid #30363D` borders. No shadow.
- **Level 2 (Active Focus & Splitters):** `#21262D` surfaces with selective `#8B5CF6` 1px border indicators or 2px active tab accent lines.
- **Level 3 (Overlays, Context Menus & Command Palettes):** `#161B22` backed by a 1px border of `#30363D` and a sharp, low-spread directional shadow (`0 8px 24px rgba(1, 4, 9, 0.75)`).
- **Focus States:** High-visibility keyboard focus rings using `0 0 0 2px rgba(139, 92, 246, 0.4)` coupled with a crisp `#8B5CF6` border.

## Shapes

The design system employs a **Soft (Level 1)** geometric curve profile. Sharp structural lines dominate the macro workspace, while subtle, precision corners soften interactive controls.

- **Panels, Splitters & Tabs:** 0px radius at junctions to form unbroken, clean docking planes. Tab corners use 4px top radius (`rounded-t-sm`).
- **Interactive Controls (Buttons, Inputs, Badges):** Fixed 4px (`0.25rem`) border radius, reinforcing tactile mechanical precision.
- **Tooltips & Popovers:** 6px radius (`0.375rem`).
- **Pill Badges:** Strictly reserved for live execution status indicators and notification counters (e.g., error counts).

## Components

### Buttons & Action Bars
- **Primary (Compile / Transpile):** Background `#8B5CF6`, text `#FFFFFF`, font `Inter` 12px weight 600. Hover: `#7C3AED`. Active: `#6D28D9`. 4px radius, 6px 12px padding.
- **Secondary / Ghost:** Background `transparent`, border `1px solid #30363D`, text `#C9D1D9`. Hover: background `#21262D`, border `#8B949E`.
- **Destructive:** Background `transparent`, border `1px solid rgba(239, 68, 68, 0.4)`, text `#EF4444`. Hover: background `rgba(239, 68, 68, 0.1)`.

### Editor Tabs & Splitters
- **Tabs:** Background `#161B22`, border-right `1px solid #30363D`, text `#8B949E`, 28px height. Active tab: background `#0D1117`, text `#F0F6FC`, top indicator border `2px solid #8B5CF6`. Close icon appears on hover or active state.
- **Splitters / Resizers:** 3px visual thickness, neutral state transparent or `#30363D`, hover/drag state `#8B5CF6`.

### Inputs, Search & Command Palette
- **Code Inputs & Filters:** Background `#0D1117`, border `1px solid #30363D`, color `#F0F6FC`, font `JetBrains Mono` 12px. Focus: border `#8B5CF6`, outline none.
- **Command Palette (`Ctrl+K`):** Centered modal, width 640px, background `#161B22`, border `1px solid #30363D`, input field height 44px with a secondary cyan search glyph.

### Badges, Diagnostics & AST Chips
- **Error Chip:** Background `rgba(239, 68, 68, 0.12)`, border `1px solid rgba(239, 68, 68, 0.3)`, text `#EF4444`, font `JetBrains Mono` 11px.
- **Warning Chip:** Background `rgba(245, 158, 11, 0.12)`, border `1px solid rgba(245, 158, 11, 0.3)`, text `#F59E0B`.
- **AST / Type Inferred Chip:** Background `rgba(34, 211, 238, 0.1)`, border `1px solid rgba(34, 211, 238, 0.3)`, text `#22D3EE`.

### Code Buffers & Diff View
- **Gutter:** Width 48px, background `#0D1117`, text `#484F58`, font `JetBrains Mono` 12px right-aligned.
- **Diff Removals (C++ removed):** Background `rgba(239, 68, 68, 0.15)`, gutter bar `3px solid #EF4444`.
- **Diff Insertions (Python generated):** Background `rgba(16, 185, 129, 0.15)`, gutter bar `3px solid #10B981`.

### Tree Views & Project Explorer
- **Items:** Height 24px, 12px `Inter`, horizontal padding 8px with 16px indentation increments. Selection: background `#21262D`, text `#F0F6FC`, left accent bar `#8B5CF6`.