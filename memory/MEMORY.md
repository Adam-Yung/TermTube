# TermTube AI Memory

## Critical Textual 8.x CSS Facts
- ListView highlighted item class: **`.-highlight`** (single dash) — NOT `--highlight`
  - Set via `item.set_class(value, "-highlight")` in ListItem source
  - Default rule: `ListView:focus > ListItem.-highlight { background: $block-cursor-background; }`
- ListView hover class: **`.-hovered`** (single dash component class)
- Footer key component classes: **`footer-key--key`** and **`footer-key--description`**
  - CSS selector: `FooterKey .footer-key--key { color: ...; background: ...; }`
  - Old (wrong) selector was `Footer > .footer--key`
- Design tokens for footer: `$footer-key-foreground`, `$footer-key-background`, `$footer-item-background`
- Scrollbar theming: use `scrollbar-color`, `scrollbar-background`, `scrollbar-color-hover` CSS properties on the container widget (e.g. `#list-view`)
- Textual version in use: **8.2.4**

## Theme System
- Themes: crimson (default), amber, ocean, midnight
- Applied as CSS class on App root: `app.add_class("theme-{theme}")`
- Theme selectors in TCSS: `App.theme-amber #list-view > VideoListItem.-highlight { ... }`
- All ListItem highlight selectors use `.-highlight` (single dash)
- All modal lists (playlist, quality, vaction, settings) also use `.-highlight`

## Architecture
- `VideoListPanel` → contains `#list-view` (ListView) with `VideoListItem` (extends ListItem)
- `DetailPanel` → thumbnail + metadata + ActionBar
- `AppHeader` → custom header with clock, title, spinner status
- Spinner: `set_status_loading()` must immediately render first frame (not wait for 0.1s interval)

## Known Bugs Fixed
- Broken JPEG crash: PIL `OSError: broken data stream` in thumbnail render pipeline
  - Fix: validate with `PIL.Image.open(path).load()` before assigning to textual-image widget
- `--highlight` → `.-highlight` global CSS rename (Textual 8.x breaking change)
- Footer key CSS class rename: `footer--key` → `footer-key--key` on `FooterKey` widget
