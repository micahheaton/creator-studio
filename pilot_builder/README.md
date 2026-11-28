# R11 editable infographic starter

This is a small build candidate for **The editable slide test**. One structured layout generates a true SVG and a one-slide PPTX containing live text and independent native shapes. It does not convert arbitrary raster images into editable slides.

The generated files belong in `../pilot_assets`. The source layout, builder and structural verifier live here. The project has no tenant, employer or customer data. It does not upload or publish anything.

## What the example changes

The builder exports the original PPTX, imports that saved file, and edits its existing objects. It changes `Launch plan` to `Launch brief`, recolors the native circle from blue to orange, and moves only that circle 32 pixels right and 20 pixels down. It saves an edited PPTX, imports it again, and checks that the new live text survived.

`verify_native.py` separately reads the saved files as Open XML. It checks the live text, native ellipse fill and position, absence of pictures, and unchanged content and geometry of every other native object. It checks that SVG uses actual text and vector objects and contains no image element.

These checks support a native editability claim about the saved structure. They do not replace application UI testing.

## Runtime

This version uses `@oai/artifact-tool` **2.8.194** in the supplied ChatGPT runtime and the Presentations skill finalizer. It is not a standalone public npm installation recipe. A compatible runtime and the documented skill helpers are required to rerun the PPTX builder. SVG, JSON and PPTX outputs can be opened independently.

The chosen font is **Liberation Sans**. It was available in the build environment. Install it for the closest appearance in another editor, or deliberately change `fontFamily` and regenerate both outputs. Application font substitution remains untested.

## Reproduce

Use a fresh build tag on each run. The finalizer intentionally refuses to overwrite a prior finalized PPTX.

```bash
export RUNTIME_NODE="$CODEX_PRIMARY_RUNTIME_NODE"
export RUNTIME_NODE_MODULES="$CODEX_PRIMARY_RUNTIME_NODE_MODULES"
export RUNTIME_BIN_DIR="$CODEX_PRIMARY_RUNTIME_ROOT/dependencies/bin/override"
export RUNTIME_PYTHON="$CODEX_PRIMARY_RUNTIME_PYTHON"
ln -s "$RUNTIME_NODE_MODULES" node_modules
"$RUNTIME_NODE" build.mjs r11_v2
"$RUNTIME_PYTHON" verify_native.py --tag r11_v2
```

Skip the `ln` command if the correct link already exists. Set `PRESENTATIONS_SKILL_DIR` if the installed Presentations skill uses a different location.

The finalizer checks one-slide package structure, geometry, declared fonts and Artifact Tool import. Inspect the actual rendered images after any content or layout change.

## Required PowerPoint proof

Full R11 proof acceptance stays **BLOCKED** until someone records the following uninterrupted action in actual PowerPoint:

1. Open the original PPTX and click into `Launch plan` as live text.
2. Change it to `Launch brief`.
3. Select only the blue circle, recolor it, and move it independently.
4. Save, close, reopen, and inspect the edited slide.

Name the actual operating system, PowerPoint version and font availability in that record. A browser recreation, generated animation, XML diff or headless LibreOffice render does not satisfy this gate. If another application is tested, name that application accurately.

## Sources for format claims

- [Microsoft SVG editing guidance](https://support.microsoft.com/en-us/office/graphics-visuals/edit-svg-images-in-microsoft-365)
- [W3C SVG embedded content](https://www.w3.org/TR/SVG/embedded.html)

No video or platform publication package is produced by this starter.
