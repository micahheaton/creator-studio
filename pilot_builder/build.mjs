import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
import { Presentation, PresentationFile, FileBlob } from '@oai/artifact-tool';

// Requires the documented Artifact Tool runtime and presentation skill helpers.
// The source layout is data. Both SVG and PPTX use the same positioned elements.
const builderDir = path.dirname(fileURLToPath(import.meta.url));
const workspaceDir = path.dirname(builderDir);
const assetsDir = path.join(workspaceDir, 'pilot_assets');
const buildTag = process.argv[2] ?? 'r11_v1';
if (!/^[A-Za-z0-9_-]+$/.test(buildTag)) throw new Error('Invalid build tag');
const workDir = path.join(builderDir, '.work', buildTag);
const skillDir = process.env.PRESENTATIONS_SKILL_DIR ?? '/home/agent/.codex/skills/builtins/presentations';
const pythonExecutable = process.env.CODEX_PRIMARY_RUNTIME_PYTHON;
if (!pythonExecutable || !path.isAbsolute(pythonExecutable)) {
  throw new Error('CODEX_PRIMARY_RUNTIME_PYTHON must name the documented runtime');
}
const { finalizePresentation } = await import(pathToFileURL(
  path.join(skillDir, 'container_tools', 'artifact_tool_utils.mjs'),
).href);
await fs.mkdir(workDir, { recursive: true });
await fs.mkdir(assetsDir, { recursive: true });
const sourceBytes = await fs.readFile(path.join(builderDir, 'layout.json'));
const layout = JSON.parse(sourceBytes);
const sourceHash = createHash('sha256').update(sourceBytes).digest('hex');

const noLine = { style: 'solid', fill: 'none', width: 0 };
const xml = value => String(value).replace(/[&<>"']/g, c => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;',
}[c]));

function toSvg(data) {
  const { width, height, background } = data.canvas;
  const rows = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="svg-title svg-desc">`,
    `<title id="svg-title">${xml(data.title)}</title>`,
    '<desc id="svg-desc">An original infographic with editable SVG text and vector shapes. Shared structured layout also generates a native PPTX.</desc>',
    `<rect width="${width}" height="${height}" fill="${background}"/>`,
  ];
  for (const el of data.elements) {
    if (el.kind === 'text') {
      rows.push(`<text id="${xml(el.id)}" x="${el.x}" y="${el.y + el.fontSize * 0.9}" font-family="${xml(el.fontFamily)}" font-size="${el.fontSize}" font-weight="${el.weight}" fill="${el.color}">${xml(el.text)}</text>`);
    } else if (el.kind === 'rect') {
      rows.push(`<rect id="${xml(el.id)}" x="${el.x}" y="${el.y}" width="${el.width}" height="${el.height}" fill="${el.fill}"/>`);
    } else if (el.kind === 'ellipse') {
      rows.push(`<ellipse id="${xml(el.id)}" cx="${el.x + el.width / 2}" cy="${el.y + el.height / 2}" rx="${el.width / 2}" ry="${el.height / 2}" fill="${el.fill}"/>`);
    } else {
      throw new Error(`Unsupported native element: ${el.kind}`);
    }
  }
  rows.push('</svg>');
  return rows.join('\n') + '\n';
}

function makePresentation(data) {
  const deck = Presentation.create({ slideSize: {
    width: data.canvas.width, height: data.canvas.height,
  }});
  const slide = deck.slides.add();
  slide.background.fill = data.canvas.background;
  for (const el of data.elements) {
    const shape = slide.shapes.add({
      name: el.id,
      geometry: el.kind === 'text' ? 'textbox' : el.kind,
      position: { left: el.x, top: el.y, width: el.width, height: el.height },
      fill: el.kind === 'text' ? 'none' : el.fill,
      line: noLine,
    });
    if (el.kind === 'text') {
      shape.text = el.text;
      shape.text.style = {
        fontSize: el.fontSize, typeface: el.fontFamily, bold: el.weight >= 700,
        color: el.color, alignment: 'left', verticalAlignment: 'top',
        wrap: 'none', autoFit: 'none', insets: 0,
      };
    }
  }
  slide.speakerNotes.text = data.notes.join('\n\n');
  return deck;
}

async function finalize(deck, stage) {
  const candidatePath = path.join(workDir, `${stage}.candidate.pptx`);
  const finalPath = path.join(assetsDir, `${buildTag}_${stage}.pptx`);
  await (await PresentationFile.exportPptx(deck)).save(candidatePath);
  const result = await finalizePresentation({
    workspaceDir, candidatePath, finalPath, pythonExecutable,
    explicitTotalSlideCount: 1,
    requiredNativeTableOwnerSlides: [],
    requiredNativeChartOwnerSlides: [],
    integrityValidatorPath: path.join(skillDir, 'container_tools', 'inspect_presentation_package_integrity.py'),
    layoutValidatorPath: path.join(skillDir, 'container_tools', 'inspect_presentation_layout_geometry.py'),
    layoutArgs: [
      '--expected-slide-size-emu', `${layout.canvas.width * 9525},${layout.canvas.height * 9525}`,
      '--validate-bullet-geometry', '--validate-heading-fit',
    ],
    fontPolicy: layout.font_policy,
    verifyArtifactToolImport: true,
    receiptPath: path.join(workDir, `${stage}.validation.json`),
  });
  return { path: finalPath, result };
}

async function preview(deck, stage) {
  const png = await deck.export({ slide: deck.slides.items[0], format: 'png', scale: 1 });
  const pngPath = path.join(assetsDir, `${buildTag}_${stage}.png`);
  await fs.writeFile(pngPath, new Uint8Array(await png.arrayBuffer()));
  const result = await deck.inspect({
    select: '$.slides[0].elements[*]',
    include: ['id', 'name', 'kind', 'text', 'position'],
  });
  await fs.writeFile(path.join(workDir, `${stage}.inspect.json`), JSON.stringify(result.records, null, 2) + '\n');
  return pngPath;
}

function namedShape(deck, name) {
  const matches = deck.slides.items[0].shapes.items.filter(s => s.name === name);
  if (matches.length !== 1) throw new Error(`Expected exactly one native shape named ${name}, found ${matches.length}`);
  return matches[0];
}

const beforeDeck = makePresentation(layout);
await fs.writeFile(path.join(assetsDir, `${buildTag}_before.svg`), toSvg(layout));
const before = await finalize(beforeDeck, 'before');
console.log('Exported and validated native before PPTX');

// Import the exported file, then edit its existing native objects.
const imported = await PresentationFile.importPptx(await FileBlob.load(before.path));
await preview(imported, 'before');
const edit = layout.programmatic_edit;
const textTarget = namedShape(imported, edit.text.id);
const originalInspection = await imported.inspect({
  select: '$.slides[0].elements[*]', include: ['name', 'text'],
});
if (!originalInspection.records.some(r => r.name === edit.text.id && r.text === edit.text.before)) {
  throw new Error('Imported live text does not match the specified original');
}
textTarget.text.replace(edit.text.before, edit.text.after);
const shapeTarget = namedShape(imported, edit.shape.id);
shapeTarget.fill = edit.shape.fill_after;
shapeTarget.position = {
  left: edit.shape.x_after, top: edit.shape.y_after,
  width: shapeTarget.position.width, height: shapeTarget.position.height,
};
const editedLayout = structuredClone(layout);
editedLayout.elements.find(e => e.id === edit.text.id).text = edit.text.after;
Object.assign(editedLayout.elements.find(e => e.id === edit.shape.id), {
  fill: edit.shape.fill_after, x: edit.shape.x_after, y: edit.shape.y_after,
});
await fs.writeFile(path.join(assetsDir, `${buildTag}_after.svg`), toSvg(editedLayout));
await fs.writeFile(path.join(workDir, 'edited_layout.json'), JSON.stringify(editedLayout, null, 2) + '\n');
const after = await finalize(imported, 'after');
console.log('Edited actual imported text, fill and position; saved after PPTX');

const reopened = await PresentationFile.importPptx(await FileBlob.load(after.path));
const reopenedRecords = await reopened.inspect({
  select: '$.slides[0].elements[*]', include: ['name', 'text', 'position'],
});
if (!reopenedRecords.records.some(r => r.name === edit.text.id && r.text === edit.text.after)) {
  throw new Error('Reopened PPTX did not preserve changed live text');
}
await preview(reopened, 'after');
const report = {
  build_tag: buildTag,
  status: 'BUILD_CANDIDATE',
  source_sha256: sourceHash,
  artifact_tool_import_and_edit: 'PASS',
  artifact_tool_reopen: 'PASS',
  powerpoint_application_ui: 'BLOCKED_NOT_AVAILABLE',
  video: 'NOT_CREATED',
  limitations: [
    'Programmatic import/edit/reopen is not a PowerPoint UI test.',
    'This shared layout generates both formats. It does not recover editable objects from an arbitrary raster image.',
    'Fonts may substitute in applications without Liberation Sans.',
  ],
  edit,
  outputs: { before_pptx: before.path, after_pptx: after.path },
};
await fs.writeFile(path.join(assetsDir, `${buildTag}_build_report.json`), JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify(report, null, 2));
