# PowLoot Frontend Design Specification (AI Reference)

> This document is a machine-readable design specification extracted from the existing PowLoot codebase.
> It is intended for AI agents to faithfully reproduce, extend, or modify the UI while maintaining visual consistency.

---

## 1. Technology Stack

| Layer | Choice |
|---|---|
| Framework | None (Vanilla HTML/CSS/JS) |
| CSS Method | Custom Properties (CSS Variables) + plain CSS |
| Layout | CSS Grid + Flexbox |
| Fonts | Google Fonts (remote) |
| Icons | Inline SVG (Feather-like style) |
| JS Modules | Single-file scripts (`app.js`, `admin.js`) |
| UI Libraries | None |
| Build Tools | None (direct static files) |

---

## 2. File Structure

```
public/
  custom.css     # Global design system (shared by all pages)
  home.html      # Main mining interface (imports custom.css + app.js)
  admin.html     # Admin dashboard (imports custom.css + inline <style> + admin.js)
  app.js         # Mining page logic
  admin.js       # Admin page logic
```

Key convention: `custom.css` contains the shared design system. Page-specific styles (admin only) are embedded in `<style>` tags within the HTML file.

---

## 3. Design Tokens (CSS Variables)

### 3.1 Dark Theme (default, `:root` and `[data-theme="dark"]`)

```css
/* Backgrounds (4-level depth system, darkest to lightest) */
--bg:              #060608
--bg2:             #0d0d12
--bg3:             #13131a
--bg4:             #1a1a24

/* Surfaces (translucent overlays) */
--surface:         rgba(255,255,255,0.03)
--surface-hover:   rgba(255,255,255,0.055)

/* Borders */
--border:          rgba(255,255,255,0.07)
--border-bright:   rgba(255,255,255,0.13)

/* Text (3-level hierarchy) */
--text:            #ededf5          /* Primary */
--text2:           #7878a0          /* Secondary */
--text3:           #44445a          /* Tertiary / labels */

/* Accent (Purple) */
--accent:          #7c6af7          /* Primary interactive */
--accent2:         #a08cf9          /* Lighter / hover */
--accent-dim:      rgba(124,106,247,0.14)   /* Tinted background */
--accent-glow:     rgba(124,106,247,0.28)   /* Glow / border highlight */

/* Semantic Colors */
--green:           #34d399          /* Success */
--green-dim:       rgba(52,211,153,0.13)    /* Success background */
--yellow:          #fbbf24          /* Warning */
--red:             #f87171          /* Error / danger */

/* Shadows */
--shadow-lg:       0 24px 64px rgba(0,0,0,0.7)
```

### 3.2 Light Theme (`[data-theme="light"]`)

```css
--bg:              #f2f2f7
--bg2:             #e8e8f0
--bg3:             #dcdce8
--bg4:             #d0d0e0
--surface:         rgba(0,0,0,0.03)
--surface-hover:   rgba(0,0,0,0.055)
--border:          rgba(0,0,0,0.09)
--border-bright:   rgba(0,0,0,0.16)
--text:            #111118
--text2:           #505070
--text3:           #8888a4
--accent:          #6655e8
--accent2:         #7c6af7
--accent-dim:      rgba(102,85,232,0.1)
--accent-glow:     rgba(102,85,232,0.22)
--green:           #059669
--green-dim:       rgba(5,150,105,0.1)
--yellow:          #d97706
--red:             #dc2626
--shadow-lg:       0 24px 64px rgba(0,0,0,0.14)
```

### 3.3 Theme System

- Toggle mechanism: `data-theme` attribute on `<html>` element
- Values: `"dark"` | `"light"` (system preference via JS `matchMedia`)
- Persistence: `localStorage.getItem('theme')`
- Default: `dark`

---

## 4. Typography

### 4.1 Font Families

```css
/* Primary (UI text) */
font-family: 'Space Grotesk', 'Plus Jakarta Sans', system-ui, sans-serif;

/* Monospace (data, code, technical values) */
font-family: 'JetBrains Mono', 'Cascadia Code', 'Consolas', monospace;
```

Google Fonts import:
```
Space Grotesk: 400, 500, 600, 700, 800
JetBrains Mono: 400, 500, 600, 700
```

### 4.2 Type Scale

| Role | Font | Size | Weight | Letter-spacing | Color | Transform |
|---|---|---|---|---|---|---|
| Logo brand name | Space Grotesk | 1.75rem | 800 | -0.04em | gradient(text→accent2) | none |
| Logo subtitle | Space Grotesk | 0.72rem | 500 | 0.08em | --text3 | uppercase |
| Section title (admin) | Space Grotesk | 0.72rem | 700 | 0.1em | --text3 | uppercase |
| Tab button | Space Grotesk | 0.82rem | 600 | none | --text3 / --accent2 | none |
| Start button | Space Grotesk | 0.9rem | 700 | none | #fff | none |
| Stop button | Space Grotesk | 0.85rem | 600 | none | --text2 | none |
| Stat label | Space Grotesk | 0.67rem | 600 | 0.1em | --text3 | uppercase |
| Stat value | JetBrains Mono | 1.05rem | 700 | -0.02em | --text | none |
| Stat value (small) | JetBrains Mono | 0.82rem | 700 | -0.02em | --text | none |
| Hash rate value | JetBrains Mono | 1.5rem | 800 | -0.04em | --text2 | none |
| Hash rate label | Space Grotesk | 0.62rem | 700 | 0.12em | --text3 | uppercase |
| Hash rate unit | Space Grotesk | 0.6rem | 700 | 0.1em | --text3 | uppercase |
| Log title | Space Grotesk | 0.72rem | 700 | 0.14em | --text3 | uppercase |
| Log text | JetBrains Mono | 0.7rem | 400 | none | --text2 | none |
| Log timestamp | JetBrains Mono | 0.62rem | 400 | none | --text3 | none |
| Info banner | Space Grotesk | 0.78rem | 400 | none | --text2 | none |
| Badge | inherit | 0.68rem | 700 | none | semantic color | none |
| Config label | JetBrains Mono | 0.75rem | 600 | none | --text2 | none |
| Config description | Space Grotesk | 0.68rem | 400 | none | --text3 | none |
| Table header | JetBrains Mono | 0.67rem | 700 | 0.1em | --text3 | uppercase |
| Table cell | JetBrains Mono | 0.78rem | 400 | none | --text2 | none |
| Toast | Space Grotesk | 0.78rem | 400 | none | --text | none |
| Win title | Space Grotesk | 0.95rem | 700 | none | --green | none |
| Win detail | Space Grotesk | 0.78rem | 400 | none | --text2 | none |

### 4.3 Gradient Text Pattern

Used for brand/logo text:
```css
background: linear-gradient(130deg, var(--text) 30%, var(--accent2));
-webkit-background-clip: text;
-webkit-text-fill-color: transparent;
background-clip: text;
```

---

## 5. Spacing & Sizing

### 5.1 Spacing Scale (commonly used values)

```
2px, 4px, 6px, 8px, 10px, 12px, 14px, 16px, 18px, 20px, 24px, 28px, 32px
```

### 5.2 Component Sizing

| Element | Padding | Height | Gap |
|---|---|---|---|
| Left panel | 28px 24px (desktop), 20px 16px (mobile) | auto | 20px (desktop), 16px (mobile) |
| Stat card | 14px | auto | 4px internal |
| Stats grid | n/a | n/a | 8px |
| Start button | 0 20px | 48px | n/a |
| Stop button | 0 18px | 48px | n/a |
| Button row | n/a | n/a | 8px |
| Input field | 0 10px | 36px | n/a |
| Hash cell | 18px 16px | auto | 4px |
| Log header | 14px 20px | auto | 8px |
| Log box | 12px 16px | flex:1 | n/a |
| Log entry | 2px 6px | auto | 8px |
| Info banner | 12px 14px | auto | n/a |
| Theme button | center | 30px x 30px | n/a |
| Theme row | 4px | auto | 4px |
| Tab button | 10px 16px | auto | n/a |
| Tab row | 4px | auto | 4px |
| Config section | 16px | auto | n/a |
| Small button | 6px 14px | auto | n/a |
| Admin wrapper | 28px 24px (desktop), 16px 12px (mobile) | min 100dvh | n/a |
| Login box | 32px | auto | n/a |
| Toast | 12px 20px | auto | n/a |

### 5.3 Border Radius Scale

```
5px   — small elements (log entries)
6px   — badges
7px   — theme buttons
8px   — inputs, inner buttons, small buttons
10px  — containers, info banner, server config, theme row, toast
12px  — cards, panels, main buttons, config sections, tab row, table wrap
16px  — login modal
9999px — progress bar, scrollbar thumb (pill shape)
```

---

## 6. Layout System

### 6.1 Main Page (home.html): Two-Panel Layout

```
Desktop (>1024px):
+---app-wrapper (grid: 380px 1fr, max-width: 1600px, height: 100dvh)---+
|  LEFT PANEL (380px, scrollable)  |  RIGHT PANEL (flex remaining)       |
|  - Logo                          |  - Hash Rate Bar (4-col grid)       |
|  - Theme Switcher                |  - Log Header                       |
|  - Info Banner                   |  - Log Box (flex:1, scrollable)     |
|  - Stats Grid (2-col)           |                                      |
|  - Control Buttons               |                                      |
|  - Withdraw / Win Panels         |                                      |
+----------------------------------+--------------------------------------+

Mobile (<=1024px):
+---app-wrapper (grid: 1fr, rows: auto 1fr)---+
|  LEFT PANEL (full width, no scroll lock)     |
|----------------------------------------------|
|  RIGHT PANEL (min-height: 320px)             |
+----------------------------------------------+
```

### 6.2 Admin Page: Single Column

```
+---admin-wrapper (max-width: 1200px, centered)---+
|  Header (logo + theme switcher, space-between)   |
|  Tab Row (flex, wrapping)                         |
|  Tab Content (switchable panels)                  |
+--------------------------------------------------+
```

### 6.3 Grid Templates

| Component | Desktop Columns | Mobile Columns |
|---|---|---|
| app-wrapper | `380px 1fr` | `1fr` |
| stats-grid | `1fr 1fr` | `1fr 1fr` |
| hash-bar | `repeat(4, 1fr)` | `repeat(2, 1fr)` (<=600px) |
| btn-row | `1fr auto` | `1fr auto` |
| rounds-grid | `repeat(auto-fill, minmax(320px, 1fr))` | `1fr` (<=600px) |
| track-config-grid | `repeat(auto-fill, minmax(280px, 1fr))` | `1fr` (<=600px) |

---

## 7. Component Catalog

### 7.1 Background Decorations

Two fixed layers behind content (z-index: 0, pointer-events: none):

**Grid Pattern** (`.bg-grid`):
```css
background-image:
  linear-gradient(var(--border) 1px, transparent 1px),
  linear-gradient(90deg, var(--border) 1px, transparent 1px);
background-size: 48px 48px;
mask-image: radial-gradient(ellipse 80% 60% at 50% 0%, black 30%, transparent 100%);
```

**Glow Effect** (`.bg-glow`):
```css
background:
  radial-gradient(ellipse 60% 40% at 20% 10%, rgba(124,106,247,0.08) 0%, transparent 70%),
  radial-gradient(ellipse 50% 35% at 80% 90%, rgba(52,211,153,0.05) 0%, transparent 70%);
```

### 7.2 Logo

Structure:
```html
<div class="logo-row">              <!-- flex, align-items:center, gap:12px -->
  <div class="logo-icon">           <!-- 40x40, rounded, accent-dim bg, accent-glow border -->
    <svg>...</svg>                   <!-- 20x20 lock icon, stroke: accent2 -->
  </div>
  <div>
    <div class="logo-name">PowLoot</div>  <!-- gradient text -->
  </div>
</div>
<div class="logo-sub">...</div>     <!-- uppercase subtitle -->
```

Icon: Padlock SVG (rect + path), `stroke="var(--accent2)"`, `stroke-width="2"`, rounded caps/joins.

### 7.3 Theme Switcher

Structure:
```html
<div class="theme-row">             <!-- flex, gap:4px, bg3, border, rounded -->
  <button class="theme-btn" data-theme="light">  <!-- sun icon -->
  <button class="theme-btn" data-theme="system">  <!-- monitor icon -->
  <button class="theme-btn active" data-theme="dark">  <!-- moon icon -->
</div>
```

States:
- Default: transparent bg, text3 color
- Hover: surface-hover bg, text2 color
- Active: accent-dim bg, accent2 color, accent-glow border

### 7.4 Stat Card

Structure:
```html
<div class="stat-card [full]">      <!-- bg3, border, rounded-12, padding:14px -->
  <div class="stat-label">LABEL</div>  <!-- tiny uppercase -->
  <div class="stat-value [accent|green|small]">VALUE</div>  <!-- monospace, large -->
</div>
```

Modifiers:
- `.full` — spans full grid width (`grid-column: 1 / -1`)
- `.stat-value.accent` — accent2 color
- `.stat-value.green` — green color
- `.stat-value.small` — 0.82rem size

Hover: bg4 background + border-bright border.

### 7.5 Buttons

**Primary (Start)**:
```css
.btn-start {
  background: var(--accent);  color: #fff;  height: 48px;  border-radius: 12px;
  /* Has a subtle shine overlay via ::before pseudo-element */
}
/* Hover: accent2 bg, translateY(-1px), box-shadow: 0 8px 24px accent-glow */
/* Disabled: opacity: 0.35, cursor: not-allowed */
```

**Secondary (Stop)**:
```css
.btn-stop {
  background: var(--surface);  color: var(--text2);  border: 1px solid var(--border);
  height: 48px;  border-radius: 12px;
}
/* Hover: surface-hover bg, border-bright, text color, translateY(-1px) */
```

**Success (Continue/Withdraw)**:
```css
.btn-win-continue {
  background: var(--green);  color: #fff;  width: 100%;  padding: 10px;  border-radius: 8px;
}
/* Hover: opacity 0.85 */
```

**Small Buttons** (Admin):
```css
.btn-sm { padding: 6px 14px; font-size: 0.75rem; border-radius: 8px; }
.btn-sm.accent { background: accent; color: #fff; }     /* Hover: accent2 + glow shadow */
.btn-sm.outline { background: surface; border: border; } /* Hover: surface-hover, border-bright */
.btn-sm.danger { background: red-dim; color: red; border: red translucent; }
```

### 7.6 Input Field

```css
.server-input {
  height: 36px;  padding: 0 10px;
  background: var(--bg);  border: 1px solid var(--border);  border-radius: 8px;
  font-family: 'JetBrains Mono', monospace;  font-size: 0.72rem;
  color: var(--text);
}
/* Focus: border-color → accent */
/* Placeholder: text3 color */
```

### 7.7 Info Banner

```css
.info-banner {
  padding: 12px 14px;
  background: var(--accent-dim);  border: 1px solid var(--accent-glow);
  border-radius: 10px;  font-size: 0.78rem;  color: var(--text2);  line-height: 1.6;
}
```

### 7.8 Progress Bar

```css
/* Native <progress> element, fully restyled */
height: 3px;  background: var(--bg3) (track);
/* Value bar: linear-gradient(90deg, accent → green), rounded pill, animated width */
```

### 7.9 Hash Rate Bar (Metrics)

4-column grid of metric cells, border-separated:
```html
<div class="hash-bar">              <!-- grid: 4 cols, bottom border -->
  <div class="hash-cell">           <!-- padding: 18px 16px, right border, hover bg -->
    <div class="hash-label">LABEL</div>
    <div class="hash-val">VALUE</div>
    <div class="hash-unit">UNIT</div>
    <div class="hash-extra">EXTRA</div>  <!-- optional -->
  </div>
</div>
```

### 7.10 Log Box

```html
<div class="log-header">            <!-- flex, bg2, bottom border -->
  <div class="log-dot"></div>        <!-- 6px circle, accent color, blink animation -->
  <div class="log-title">TITLE</div>
</div>
<div id="logBox">                    <!-- monospace, flex:1, scrollable -->
  <div class="log-entry [log-success|log-warn|log-error]">
    <div class="log-icon">SYMBOL</div>
    <div class="log-content">
      <div class="log-time">HH:MM:SS</div>
      <div class="log-message">TEXT</div>
    </div>
  </div>
</div>
```

Log entry color variants:
- Default: accent icon, text2 message
- `.log-success`: green icon + green message
- `.log-warn`: yellow icon + yellow message
- `.log-error`: red icon + red message

### 7.11 Win Panel

```css
.win-panel {
  display: none;  /* .show → display: block */
  padding: 16px;  background: var(--green-dim);
  border: 1px solid rgba(52,211,153,0.3);  border-radius: 12px;
  animation: slideUp 0.3s ease;
}
```

### 7.12 Tab Navigation (Admin)

```html
<div class="tab-row">               <!-- flex, gap:4px, bg3, border, rounded-12 -->
  <button class="tab-btn [active]" data-tab="name">Label</button>
</div>
<div class="tab-panel [active]">Content</div>
```

Shares identical styling pattern with theme-row.

### 7.13 Data Table (Admin)

```html
<div class="table-wrap">            <!-- overflow-x:auto, border, rounded-12 -->
  <table class="admin-table">       <!-- monospace, collapse, 0.78rem -->
    <thead><tr><th>COL</th></tr></thead>
    <tbody><tr><td>DATA</td></tr></tbody>
  </table>
</div>
```

Header: bg3, uppercase, 0.67rem. Rows: hover highlight with surface-hover.

### 7.14 Status Badges

```html
<span class="badge badge-green">Active</span>
<span class="badge badge-yellow">Pending</span>
<span class="badge badge-red">Offline</span>
```

Structure: inline-block, padding 2px 8px, rounded-6, semantic dim background + semantic color text.

### 7.15 Toast Notification

```css
.toast {
  position: fixed; bottom: 24px; right: 24px; z-index: 9999;
  padding: 12px 20px; bg4 background; border-bright border; rounded-10;
  /* Animated in via .show class: opacity 0→1, translateY 8px→0 */
}
.toast.success { green tinted border + green text }
.toast.error { red tinted border + red text }
```

### 7.16 Login Overlay (Admin)

```css
.login-overlay {
  position: fixed; inset: 0; z-index: 9998;
  background: var(--bg); flex center;
}
.login-box {
  width: 340px; padding: 32px; bg3; border; rounded-16; text-align: center;
  /* Contains: gradient h2, subtitle p, password input, accent submit button */
}
```

### 7.17 Config Section (Admin)

```html
<div class="config-section">        <!-- bg3, border, rounded-12, padding:16px -->
  <div class="config-section-title">TITLE</div>  <!-- uppercase label -->
  <div class="config-row">          <!-- flex, align center, gap:12px -->
    <label>KEY <span class="config-desc">description</span></label>
    <input type="number" class="server-input">
  </div>
</div>
```

### 7.18 Round Card (Admin)

```html
<div class="round-card">            <!-- bg3, border, rounded-12, padding:16px -->
  <div class="round-track">TRACK_NAME</div>  <!-- accent2, bold -->
  <div class="round-detail">
    key: <span class="val">value</span>      <!-- val = text color, bold -->
  </div>
</div>
```

### 7.19 Sync Section (Admin)

```html
<div class="sync-section">          <!-- bg3, border, rounded-12, padding:20px -->
  <div class="sync-section-title">TITLE</div>
  <div class="sync-section-desc">DESCRIPTION</div>
  <button class="btn-sm accent">ACTION</button>
  <div class="sync-info">STATUS</div>  <!-- bg, border, rounded-8, monospace -->
</div>
```

---

## 8. Animations

```css
/* Panel / card entry */
@keyframes slideUp {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* Indicator breathing */
@keyframes blink {
  0%, 100% { opacity: 1; }
  50%      { opacity: 0.3; }
}

/* Mining active pulse */
@keyframes pulse {
  0%, 100% { transform: scale(1);   opacity: 1; }
  50%      { transform: scale(1.4); opacity: 0.5; }
}
```

Transition defaults: `all 0.15s ease` or `all 0.2s ease`. Specific: `border-color 0.15s`, `background 0.15s`, `width 0.5s ease` (progress bar).

---

## 9. Icon System

All icons are **inline SVG** with the following conventions:

```
viewBox="0 0 24 24" or "0 0 16 16"
fill="none"
stroke="var(--accent2)" or "currentColor"
stroke-width="1.5" or "2"
stroke-linecap="round"
stroke-linejoin="round"
```

Icon sizes: 20x20 (logo), 13x13 (theme buttons), 12px (log icons via CSS width).

Icons used:
- **Lock** (logo): rect + path padlock
- **Sun** (light theme): circle + radiating lines
- **Monitor** (system theme): rect + horizontal line
- **Moon** (dark theme): crescent path

---

## 10. Scrollbar Customization

```css
/* Firefox */
scrollbar-width: thin;
scrollbar-color: var(--border) transparent;

/* WebKit */
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border-bright); border-radius: 9999px; }
```

Left panel hides scrollbar entirely (`scrollbar-width: none`, `::-webkit-scrollbar { display: none }`).

---

## 11. Responsive Breakpoints

| Breakpoint | Target | Key Changes |
|---|---|---|
| `<=1024px` | Tablet / mobile | app-wrapper → single column; left-panel border → bottom; reduced padding (20px 16px); right-panel min-height: 320px; log box max-height: 40vh |
| `<=600px` | Small phone | hash-bar → 2 columns; hash-val → 1.15rem; admin wrapper → 16px 12px; config-row / balance-setter → stack vertically; track-config-grid / rounds-grid → single column |

---

## 12. Selection & Misc

```css
::selection { background: var(--accent-dim); color: var(--text); }
a { color: inherit; }
*, *::before, *::after { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body { margin: 0; min-height: 100dvh; overflow-x: hidden; }
```

---

## 13. Design Principles Summary

1. **Dark-first**: Deep blue-black backgrounds with purple accent. Light theme inverts with equal care.
2. **Layered depth**: 4-level background system (bg→bg4) creates visual hierarchy without drop shadows.
3. **Translucent borders & surfaces**: Using `rgba()` instead of solid colors for a modern glassmorphism-lite feel.
4. **Monospace for data**: All numeric/technical values use JetBrains Mono; UI text uses Space Grotesk.
5. **Minimal decoration**: No gratuitous shadows, gradients, or rounded corners. Each decoration serves hierarchy.
6. **Compact density**: Small font sizes (0.62-0.95rem), tight spacing. Optimized for information density.
7. **Subtle interactions**: Hover states use background/border changes + slight translateY(-1px) lift, never dramatic transforms.
8. **Color semantics**: Purple = interactive/accent, Green = success/money, Yellow = warning, Red = error/danger.
9. **Grid-first layout**: CSS Grid for page structure and data layouts; Flexbox for component internals.
10. **Progressive disclosure**: Panels hidden by default (`.show`), animations on entry (`slideUp`).

---

## 14. How to Extend

When adding new components, follow these rules:

1. **Use existing CSS variables** — never hardcode colors, use `var(--token)`.
2. **Match the border pattern** — `1px solid var(--border)` default, `var(--border-bright)` on hover.
3. **Match the radius scale** — 8px for small/inline, 10-12px for cards/containers, 16px for modals.
4. **Match typography** — labels are 0.67-0.72rem uppercase with letter-spacing; values are monospace with weight 700.
5. **Match padding** — 14-16px for cards, 12-14px for compact elements, 24-32px for page containers.
6. **Add hover transitions** — always include `transition: all 0.15s ease` or `transition: background 0.15s, border-color 0.15s`.
7. **Use semantic color classes** — `.accent` for purple, `.green` for success, badge pattern for status.
8. **Keep inline SVG** — no icon fonts, no external icon files. SVGs use `currentColor` or `var(--accent2)`.
9. **Support both themes** — if using any color directly, ensure it works in both dark and light via CSS variables.
10. **Responsive** — add `@media (max-width: 1024px)` and `@media (max-width: 600px)` rules for any new grid layouts.
