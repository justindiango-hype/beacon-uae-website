# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Marketing site for BEACON UAE (business setup, visas, PRO, tax in Dubai). It is a **single static file, `index.html` (~9k lines, ~900 KB)**, plus images and 3D models in `assets/`. There is no build step, no package.json, no tests and no linter.

## Running locally

Serve the folder over HTTP; opening the file directly via `file://` will break the GLB model fetch:

```
python3 -m http.server 8000   # then open http://localhost:8000
```

Every library loads from a CDN at runtime, so you need a network connection: React 18 + ReactDOM (UMD), Babel Standalone, GSAP 3.12.5 + ScrollTrigger, Three.js r128 + GLTFLoader, and the Inter font from Google Fonts.

## Architecture of index.html

The file has these parts, in order:

1. **`<head>`**: CDN scripts, then the main `<style>` block (lines ~29–1548), then a long series of **id-tagged override `<style>` blocks** (e.g. `#beacon-service-card-final-polish`, `#beacon-train-roadmap`, `#beacon-magic-bento-services`). Each block is a later patch that overrides earlier rules. More of these blocks also appear near the end of `<body>`.
2. **Markup**: `#react-bg-container` (the background canvas mount), the floating `.slide-nav` dots, `#nav`, then `<main id="content-wrapper">`. Inside `main`, each page section is a `.snap-section`, in this order: `#hero`, `#calc`, `#about`, `#why`, `#services`, `#packages`, `#how`, `#team`, `#gallery`, `#location`, `#contact`.
3. **Vanilla JS block** (`<script>` at ~3673): defines the `$`/`$$` helpers, fills in DOM content from data arrays (`IC`, `SERV` = service cards, `TOWERS`), runs the tax calculator (uses a fixed `EUR` rate), and sets up the GSAP animations.
4. **`<script type="text/babel">`** (~4334–7722): React components compiled in the browser by Babel. `GhostFibers` is a WebGL2 shader background mounted into `#react-bg-container`. `Folder` and `DocumentCard` render the packages folder UI. `DepthCarousel` and `StackGallery` power the gallery and reviews. Each component mounts itself with its own `ReactDOM.createRoot` call into a specific mount node. The GLSL shaders are template-string constants (`VERTEX`, `PAINT`, `GLASS`, …).
5. **Late feature scripts with ids**:
   - `#beacon-train-roadmap-script`: the "How it works" roadmap. Its train image is a large inline base64 PNG on line ~3378, which is a very long line; avoid printing it.
   - `#beacon-faq-chat-js`: the location/FAQ chat widget. It holds the `FAQ` data, the WhatsApp link and the Zoho booking link.
   - `#beacon-holo-card-js`: the tilt effect on cards.
   - `#beacon-bg3d-js`: the Three.js Burj Khalifa background. It loads `assets/burj_khalifa_web.glb` and keeps one camera "shot" per section in `SHOTS` (look for the `EDIT HERE` comment). It only runs when `<html data-bg3d="1">` is set, which the inline script in the `<head>` does once `THREE` has loaded.

## Conventions and gotchas

- **Editing styles:** find the *last* rule that applies to the element. Later id-tagged `<style>` blocks override earlier ones, often with `!important`. Some ids are reused: `beacon-service-cards-refresh` appears twice. Changing an early rule often has no visible effect.
- When adding a style or script patch, follow the existing pattern: one id-tagged `<style>`/`<script>` block, named after the feature.
- Animations check `prefers-reduced-motion`, in CSS and in the bg3d script. Keep that behavior when you add motion.
- Contact CTAs point to WhatsApp `https://wa.me/971547775023`. There are several copies (nav, mobile menu, FAQ chat, contact section), so update all of them together.
- Image paths are relative: `assets/team/*.webp`, `assets/kingahero.webp`, `assets/gallery/photoN.jpg` (built in code as `photo${n}.jpg`, so filenames must be lowercase `.jpg`), `assets/landmark/{1,2,3,5}.webp`, and `assets/landmark/Nbnw.png` black-and-white tiles (used only when the 3D scene is off), `assets/logos/N.png` (256 px, shown at about 60 px).
- Images were sized to about 2× their largest rendered size. Original full-resolution files are in the baseline commit `e3fde59`.
- Only `assets/burj_khalifa_web.glb` is loaded by the 3D scene.
- The file is large. Search with grep and read line ranges instead of the whole file.
