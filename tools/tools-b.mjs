const error = (message) => `Input error: ${message}`;
const clean = (value) => String(value ?? '').trim();
const uint = (value) => (/^\d+$/.test(clean(value)) ? Number(clean(value)) : NaN);
const lines = (value) => String(value ?? '').replace(/^\uFEFF/, '').replace(/\r\n?/g, '\n');
const MAX_CUES = 2000;
const tcPattern = /^(\d{2,3}):([0-5]\d):([0-5]\d)[,.](\d{3})$/;

function timecode(value) {
  const m = clean(value).match(tcPattern);
  return m ? ((Number(m[1]) * 60 + Number(m[2])) * 60 + Number(m[3])) * 1000 + Number(m[4]) : NaN;
}

function asTimecode(t) {
  const p = (n, count = 2) => String(n).padStart(count, '0');
  return `${p(Math.floor(t / 3600000))}:${p(Math.floor(t / 60000) % 60)}:${p(Math.floor(t / 1000) % 60)},${p(t % 1000, 3)}`;
}

function parseSrt(value) {
  const source = lines(value).trim();
  if (!source || source.length > 1000000) throw new Error('Paste an SRT file from 1 to 1,000,000 characters.');
  const blocks = source.split(/\n[\t ]*\n+/);
  if (blocks.length > MAX_CUES) throw new Error(`Use at most ${MAX_CUES} cues.`);
  return blocks.map((block, i) => {
    const [index, timing, ...body] = block.split('\n');
    const match = clean(timing).match(/^([^\s]+)\s+-->\s+([^\s]+)$/);
    const start = match ? timecode(match[1]) : NaN;
    const end = match ? timecode(match[2]) : NaN;
    if (!/^\d+$/.test(clean(index)) || !Number.isFinite(start) || !Number.isFinite(end) || end <= start || !clean(body.join('\n'))) {
      throw new Error(`Check cue ${i + 1}: expected a numeric index, a valid time range, and caption text.`);
    }
    return { index: uint(index), start, end, body: body.join('\n'), order: i };
  });
}

const captions = {
  id: '05',
  title: 'Caption Cut & Rebase',
  tag: 'Video editing',
  problem: 'The captions from a full recording open several minutes late when you attach them to a short clip.',
  baseline: 'Trim captions by hand, subtract the clip start from every timestamp, and renumber the remaining cues.',
  prompt: 'Crop standard numbered SRT cues to [clip in, clip out). Clip any boundary-spanning cues, subtract clip in from both timestamps, sort by start and original order, renumber, and preserve multiline text. Accept HH:MM:SS,mmm or HH:MM:SS.mmm. Reject malformed input. Return exportable SRT. Nothing is uploaded.',
  fields: [
    { label: 'Clip in (HH:MM:SS,mmm)', value: '00:02:10,000' },
    { label: 'Clip out (HH:MM:SS,mmm)', value: '00:02:21,000' },
    { label: 'Original SRT', multiline: true, value: '1\n00:02:01,000 --> 00:02:05,000\nBefore the clip.\n\n2\n00:02:08,500 --> 00:02:13,000\nLet the screenshot\ndo the explaining.\n\n3\n00:02:15,000 --> 00:02:19,200\nThen say what changed.\n\n4\n00:02:20,000 --> 00:02:24,000\nNow show the result.' },
  ],
  run(values) {
    const [clipIn, clipOut, source] = values;
    const start = timecode(clipIn);
    const end = timecode(clipOut);
    if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return error('Enter valid clip times and make Clip out later than Clip in.');
    try {
      const selected = parseSrt(source).filter((c) => c.end > start && c.start < end);
      if (!selected.length) return 'No captions overlap the selected clip.';
      return selected
        .sort((a, b) => a.start - b.start || a.order - b.order)
        .map((c, i) => `${i + 1}\n${asTimecode(Math.max(c.start, start) - start)} --> ${asTimecode(Math.min(c.end, end) - start)}\n${c.body}`)
        .join('\n\n') + '\n';
    } catch (e) {
      return error(e.message);
    }
  },
  verify(result) {
    try {
      const cues = parseSrt(result);
      return cues.every((c, i) => c.index === i + 1 && (!i || cues[i - 1].start <= c.start) && c.start >= 0);
    } catch {
      return false;
    }
  },
};

function hexColor(input) {
  const h = clean(input).replace(/^#/, '').toLowerCase();
  if (!/^(?:[0-9a-f]{3}|[0-9a-f]{6})$/.test(h)) return null;
  return '#' + (h.length === 3 ? [...h].map((c) => c + c).join('') : h);
}

function luminance(hex) {
  const rgb = hex.slice(1).match(/../g).map((c) => parseInt(c, 16) / 255);
  const linear = rgb.map((c) => c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
}

function contrastOutput(fg, bg) {
  const colorL = luminance(fg);
  const backgroundL = luminance(bg);
  const r = (Math.max(colorL, backgroundL) + 0.05) / (Math.min(colorL, backgroundL) + 0.05);
  const status = (minimum) => r >= minimum ? 'Pass' : 'Fail';
  return [
    `Contrast: ${r.toFixed(4)}:1 (display ratio rounded; checks use the unrounded ratio)`,
    `WCAG AA: normal ${status(4.5)} (4.5:1); large ${status(3)} (3:1)`,
    `WCAG AAA: normal ${status(7)} (7:1); large ${status(4.5)} (4.5:1)`,
    'Large text means at least 18 pt regular or 14 pt bold.',
    'This checks a solid, opaque text/background pair only, not page accessibility.',
    '',
    '.contrast-pair {',
    `  color: ${fg};`,
    `  background-color: ${bg};`,
    '}',
  ].join('\n');
}

const contrast = {
  id: '06',
  title: 'Contrast Pair Check',
  tag: 'Accessible design',
  problem: 'Two colors can look distinct on your monitor and still miss the text contrast threshold.',
  baseline: 'Eyeball the pair, or calculate the relative luminance and compare thresholds by hand.',
  prompt: 'Take two opaque sRGB hex colors. Compute the WCAG contrast ratio from linearized RGB. Apply AA and AAA thresholds to the unrounded ratio for normal and large text. Output a labeled result and copyable CSS. Reject alpha and non-hex inputs. Do not treat one passing pair as page compliance.',
  fields: [
    { label: 'Text color (#RGB or #RRGGBB)', value: '#767676' },
    { label: 'Background color (#RGB or #RRGGBB)', value: '#FFFFFF' },
  ],
  run(values) {
    const [fg, bg] = values.map(hexColor);
    if (!fg || !bg) return error('Enter two opaque hex colors, for example #222 and #FFFFFF. Alpha, gradients and named colors are not supported.');
    return contrastOutput(fg, bg);
  },
  verify(result) {
    const match = String(result).match(/\n  color: (#[0-9a-f]{6});\n  background-color: (#[0-9a-f]{6});\n\}$/);
    return Boolean(match && contrastOutput(match[1], match[2]) === result);
  },
};

const slug = (value) => value.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
const safeBasename = (value) => Boolean(value && value.length <= 160 && !/[<>:"/\\|?*\u0000-\u001f]/u.test(value) && !/[ .]$/.test(value)
  && !/^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(value));

const rename = {
  id: '07',
  title: 'Asset Rename Preview',
  tag: 'Asset management',
  problem: 'A folder of footage, screenshots and exports has no predictable order, and bulk-renaming on sight can overwrite a file.',
  baseline: 'Rename each asset manually and check the folder for conflicting names.',
  prompt: 'Make a dry-run-only rename manifest from pasted file basenames. Add a slugged series prefix and stable padded sequence, normalize the extension case, and detect both case-insensitive original duplicates and target names already in the pasted list. Report conflicts before any rename. No file I/O; do not generate shell commands.',
  fields: [
    { label: 'Series prefix', value: 'Studio Pilot' },
    { label: 'Number to start at', value: '1' },
    { label: 'Original file names (one per line)', multiline: true, value: 'PowerPoint Draft A.PNG\nPowerPoint Draft B.PNG\nRoom tone take 1.WAV\nFine cut v02.MP4' },
  ],
  run(values) {
    const [prefixInput, startInput, listInput] = values;
    const originalPrefix = clean(prefixInput);
    if (originalPrefix.length > 60) return error('Keep the series prefix to 60 characters or fewer.');
    const prefix = slug(originalPrefix);
    const first = uint(startInput);
    if (!prefix || prefix.length > 35) return error('Choose a prefix that yields 1 to 35 letters, digits or hyphens.');
    if (!Number.isSafeInteger(first) || first < 1 || first > 9999) return error('Pick a starting number from 1 to 9999.');
    const originals = lines(listInput).split('\n').filter((s) => s.trim());
    if (!originals.length || originals.length > 100 || first + originals.length - 1 > 9999) return error('Use 1 to 100 file names and keep the last number under 10000.');
    const occupied = new Set();
    const manifest = [];
    for (const [i, name] of originals.entries()) {
      if (!safeBasename(name) || name !== name.trim() || !/\.[a-zA-Z0-9]{1,12}$/.test(name) || name[0] === '.') {
        return error(`Line ${i + 1} must be a simple file name with an extension, not a path.`);
      }
      const lower = name.toLowerCase();
      if (occupied.has(lower)) return error(`Duplicate original file name on line ${i + 1}.`);
      occupied.add(lower);
    }
    const width = Math.max(3, String(first + originals.length - 1).length);
    for (const [i, name] of originals.entries()) {
      const num = String(first + i).padStart(width, '0');
      const ext = name.slice(name.lastIndexOf('.')).toLowerCase();
      const target = `${prefix}-${num}${ext}`;
      if (occupied.has(target)) return error(`Target "${target}" already appears in the input list. Choose a new prefix or starting number.`);
      manifest.push({ original: name, proposed: target });
    }
    return JSON.stringify({ status: 'Preview only. No files renamed.', scope: 'Checked against pasted names only. Check the actual folder before applying.', files: manifest }, null, 2);
  },
  verify(result) {
    try {
      const { status, scope, files } = JSON.parse(result);
      if (status !== 'Preview only. No files renamed.' || !scope?.includes('pasted names only') || !Array.isArray(files) || files.length < 1) return false;
      const originals = new Set();
      const targets = new Set();
      let previous;
      let prefix;
      let width;
      const valid = files.every(({ original, proposed }) => {
        if (!safeBasename(original) || !safeBasename(proposed)) return false;
        const m = proposed.match(/^([a-z0-9-]+)-(\d{3,4})(\.[a-z0-9]{1,12})$/);
        if (!m || original.slice(original.lastIndexOf('.')).toLowerCase() !== m[3]) return false;
        if (originals.has(original.toLowerCase()) || targets.has(proposed) || (previous !== undefined && (previous + 1 !== +m[2] || prefix !== m[1] || width !== m[2].length))) return false;
        originals.add(original.toLowerCase());
        targets.add(proposed);
        previous = +m[2];
        prefix = m[1];
        width = m[2].length;
        return true;
      });
      return valid && [...targets].every((t) => !originals.has(t));
    } catch {
      return false;
    }
  },
};

export const toolsB = [captions, contrast, rename];
