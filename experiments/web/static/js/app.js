/* ============================================================================
   avalpdf web — frontend logic
   Upload → POST /api/analyze → render report + pdf.js preview with bbox overlays
   ========================================================================== */
import * as pdfjsLib from 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.0.379/pdf.min.mjs';
pdfjsLib.GlobalWorkerOptions.workerSrc =
  'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.0.379/pdf.worker.min.mjs';

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const SCALE = 1.3;                    // base pdf.js render scale (= zoom 100%)

// avalpdf finding category -> element "group" used to locate it on the document
// and to propagate a finding's severity to that group of tags.
const CAT_TO_GROUP = {
  alt_text: 'figure', figures: 'figure', empty_elements: 'empty',
  links: 'linkable', headings: 'heading', tables: 'table',
  lists: 'list', consecutive_lists: 'list',
};
// Groups whose severity we can only know at category level (we can't pinpoint
// which individual table/list/heading from the report text), so the finding's
// severity is applied to ALL elements of that group. figure/empty/linkable are
// instead detectable per element, so they use intrinsic flags only.
const GROUP_LEVEL = new Set(['heading', 'table', 'list']);

const SEV_COLOR = { issue: '#d9364f', warning: '#d99117', none: '#9fb0c0' };
const SEV_RANK = { none: 0, warning: 1, issue: 2 };
const TYPE_COLOR = {
  heading: '#7048e8', para: '#5c6f82', figure: '#1a8a3f', table: '#0f8b9e',
  list: '#e8590c', link: '#0066cc', span: '#b5179e', other: '#94a3b8',
};
const LEGEND = {
  severity: [['#d9364f', 'Errore'], ['#d99117', 'Avviso'], ['#9fb0c0', 'Nessun problema']],
  type: [['#7048e8', 'Titoli'], ['#5c6f82', 'Paragrafi'], ['#1a8a3f', 'Immagini'],
         ['#0f8b9e', 'Tabelle'], ['#e8590c', 'Elenchi'], ['#0066cc', 'Link'], ['#b5179e', 'Span']],
};
const TAG_LABEL = {
  P: 'Paragrafo', H1: 'Titolo H1', H2: 'Titolo H2', H3: 'Titolo H3', H4: 'Titolo H4',
  H5: 'Titolo H5', H6: 'Titolo H6', Figure: 'Immagine', Table: 'Tabella', L: 'Elenco',
  LI: 'Voce elenco', Span: 'Span', Link: 'Collegamento', TD: 'Cella', TH: 'Intestazione',
};

const state = {
  buffer: null, file: null, data: null,
  pages: [], overlays: [], allBoxes: [],
  colorMode: 'severity', groupSeverity: {},
  sevFilter: 'all', zoom: 1,
  // hierarchy navigation
  flatEls: [], idxToPos: {}, boxesByIdx: {}, minDepth: 0, selected: null,
};

/* -------------------------------------------------------------- view switch */
function show(view) {
  ['uploadView', 'loadingView', 'errorView', 'resultsView'].forEach(id =>
    $('#' + id).classList.toggle('is-hidden', id !== view));
  $('#newAnalysisBtn').classList.toggle('is-hidden', view !== 'resultsView');
  window.scrollTo({ top: 0, behavior: 'auto' });
}
function toast(msg) {
  const t = $('#toast');
  t.textContent = msg; t.classList.remove('is-hidden');
  requestAnimationFrame(() => t.classList.add('is-show'));
  clearTimeout(toast._t);
  toast._t = setTimeout(() => {
    t.classList.remove('is-show');
    setTimeout(() => t.classList.add('is-hidden'), 250);
  }, 2600);
}

/* ----------------------------------------------------------------- upload */
function setFile(file) {
  if (!file) return;
  if (file.type && file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
    toast('Seleziona un file PDF valido.'); return;
  }
  state.file = file;
  const chosen = $('#fileChosen');
  chosen.textContent = '✓ ' + file.name + '  ·  ' + fmtBytes(file.size);
  chosen.classList.remove('is-hidden');
  // Linear flow: as soon as a valid file is chosen, analyse it — no extra click.
  analyze();
}
function fmtBytes(n) {
  if (n < 1024) return n + ' B';
  if (n < 1048576) return (n / 1024).toFixed(0) + ' KB';
  return (n / 1048576).toFixed(1) + ' MB';
}

function initUpload() {
  const dz = $('#dropzone'), input = $('#fileInput');
  dz.addEventListener('click', () => input.click());
  dz.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); }
  });
  input.addEventListener('change', () => setFile(input.files[0]));
  ['dragenter', 'dragover'].forEach(ev => dz.addEventListener(ev, e => {
    e.preventDefault(); dz.classList.add('is-drag');
  }));
  ['dragleave', 'drop'].forEach(ev => dz.addEventListener(ev, e => {
    e.preventDefault();
    if (ev === 'dragleave' && dz.contains(e.relatedTarget)) return;
    dz.classList.remove('is-drag');
  }));
  dz.addEventListener('drop', e => {
    const f = e.dataTransfer.files[0]; if (f) setFile(f);
  });
  $('#uploadForm').addEventListener('submit', e => e.preventDefault());
  $('#newAnalysisBtn').addEventListener('click', reset);
  $$('[data-action="reset"]').forEach(b => b.addEventListener('click', reset));
}

function reset() {
  state.file = null; state.buffer = null; state.data = null;
  $('#fileInput').value = '';
  $('#fileChosen').classList.add('is-hidden');
  show('uploadView');
}

/* ---------------------------------------------------------------- analyze */
async function analyze() {
  if (!state.file) return;
  $('#loadingFile').textContent = state.file.name;
  show('loadingView');
  try {
    state.buffer = await state.file.arrayBuffer();
    const lang = $('#langSelect').value;
    const url = '/api/analyze' + (lang ? '?lang=' + encodeURIComponent(lang) : '');
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/pdf' },
      body: state.buffer.slice(0),
    });
    if (!res.ok) {
      let msg = 'Errore del server (' + res.status + ').';
      try { msg = (await res.json()).error || msg; } catch (_) {}
      throw new Error(msg);
    }
    state.data = await res.json();
    await renderResults();
    show('resultsView');
  } catch (err) {
    $('#errorMsg').textContent = err.message || String(err);
    show('errorView');
  }
}

/* ------------------------------------------------------------ render report */
async function renderResults() {
  const d = state.data;
  renderScore(d);
  renderMeta(d.metadata);
  renderCategories(d.categories);
  computeGroupSeverity(d);
  // Build the viewer first so state.allBoxes is populated before we decide
  // which findings are locatable on the document.
  await renderViewer(d.structure);
  renderFindings(d);
}

function ratingOf(score) {
  if (score >= 90) return ['Ottimo', 'excellent'];
  if (score >= 70) return ['Buono', 'good'];
  if (score >= 50) return ['Sufficiente', 'fair'];
  return ['Insufficiente', 'poor'];
}

function renderScore(d) {
  const score = Math.round(d.score);
  const [label, cls] = ratingOf(d.score);
  const num = $('#scoreNumber');
  const fill = $('#gaugeFill');
  const C = 2 * Math.PI * 52;
  const colorVar = { excellent: 'var(--success)', good: 'var(--blu)', fair: 'var(--warning)', poor: 'var(--issue)' }[cls];
  fill.style.stroke = colorVar;
  fill.style.strokeDashoffset = C;
  // animate count + arc
  let cur = 0;
  const step = () => {
    cur += Math.max(1, Math.round(score / 28));
    if (cur >= score) cur = score;
    num.textContent = cur;
    fill.style.strokeDashoffset = C - (C * cur / 100);
    if (cur < score) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);

  const rating = $('#scoreRating');
  rating.textContent = label;
  rating.className = 'score-card__rating rating--' + cls;
  $('#scoreFile').textContent = state.file ? state.file.name : '';
  $('#cntIssues').textContent = d.counts.issues;
  $('#cntWarnings').textContent = d.counts.warnings;
  $('#cntSuccesses').textContent = d.counts.successes;
}

function yn(ok, yes, no) {
  return ok ? `<span class="ok">${yes}</span>` : `<span class="no">${no}</span>`;
}
function renderMeta(m) {
  m = m || {};
  const rows = [];
  rows.push(['Titolo', m.title ? esc(m.title) : yn(false, '', 'assente')]);
  rows.push(['Lingua', m.lang ? `<span class="ok">${esc(m.lang)}</span>` : yn(false, '', 'non dichiarata')]);
  rows.push(['Taggato', yn(m.tagged === 'true', 'sì', 'no')]);
  rows.push(['Pagine', esc(m.num_pages || '–')]);
  if (m.standard) rows.push(['Standard', esc(m.standard)]);
  if (m.author) rows.push(['Autore', esc(m.author)]);
  const sw = m.producer || m.creator;
  if (sw) rows.push(['Software', esc(sw)]);
  $('#metaList').innerHTML = rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('');
}

function renderCategories(cats) {
  const order = [...cats].sort((a, b) => b.weight - a.weight);
  const color = s => s >= 90 ? 'var(--success)' : s >= 50 ? 'var(--warning)' : 'var(--issue)';
  $('#catList').innerHTML = order.map(c => `
    <div class="cat-row">
      <span class="cat-row__label">${esc(c.label)} <span class="cat-row__w">· peso ${c.weight}</span></span>
      <span class="cat-row__val" style="color:${color(c.score)}">${Math.round(c.score)}%</span>
      <div class="cat-row__bar"><div class="cat-row__fill" style="width:${c.score}%;background:${color(c.score)}"></div></div>
    </div>`).join('');
}

function findingGroup(f) {
  return CAT_TO_GROUP[f.category] || null;
}
function groupHasElements(group) {
  return state.allBoxes.some(b => elementGroups(b.el).includes(group));
}

function renderFindings(d) {
  const all = [...d.issues, ...d.warnings, ...d.successes];
  const list = $('#findingsList');
  list.innerHTML = '';
  all.forEach((f, i) => {
    const group = findingGroup(f);
    const locatable = group && groupHasElements(group);
    const li = document.createElement('li');
    li.className = 'finding finding--' + f.severity + (locatable ? ' is-locatable' : '');
    li.dataset.sev = f.severity;
    const sevLabel = { issue: 'Problema', warning: 'Warning', success: 'OK' }[f.severity];
    li.innerHTML = `
      <div class="finding__head">
        <span class="finding__sev sev--${f.severity}">${sevLabel}</span>
        <span class="finding__cat">${esc(f.categoryLabel)}</span>
        ${locatable ? '<span class="finding__locate">↳ mostra nel documento</span>' : ''}
      </div>
      <p class="finding__text">${esc(f.text)}</p>`;
    if (locatable) {
      li.tabIndex = 0;
      li.setAttribute('role', 'button');
      const act = () => locate(group);
      li.addEventListener('click', act);
      li.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); act(); } });
    }
    list.appendChild(li);
  });
  applySevFilter();
}

function applySevFilter() {
  const sev = state.sevFilter;
  let shown = 0;
  $$('#findingsList .finding').forEach(li => {
    const ok = sev === 'all' || li.dataset.sev === sev;
    li.style.display = ok ? '' : 'none';
    if (ok) shown++;
  });
  $('#findingsEmpty').classList.toggle('is-hidden', shown > 0);
}

function initFilters() {
  $$('.chip--filter').forEach(ch => ch.addEventListener('click', () => {
    state.sevFilter = ch.dataset.sev;
    $$('.chip--filter').forEach(c => c.classList.toggle('is-active', c === ch));
    $$('.count').forEach(c => c.classList.toggle('is-active',
      c.dataset.filterSev === state.sevFilter && state.sevFilter !== 'all'));
    applySevFilter();
  }));
  $$('.count').forEach(c => c.addEventListener('click', () => {
    const sev = c.dataset.filterSev;
    state.sevFilter = (state.sevFilter === sev) ? 'all' : sev;
    $$('.count').forEach(x => x.classList.toggle('is-active',
      x.dataset.filterSev === state.sevFilter && state.sevFilter !== 'all'));
    $$('.chip--filter').forEach(x => x.classList.toggle('is-active', x.dataset.sev === state.sevFilter));
    applySevFilter();
  }));
}

/* ----------------------------------------------------------- pdf + overlays */
// Problem-related groups an element belongs to (used for locate + severity).
function elementGroups(e) {
  const g = [];
  if (e.figure) g.push('figure');
  if (e.empty) g.push('empty');
  if (e.linkable) g.push('linkable');
  if (e.heading) g.push('heading');
  if (e.table) g.push('table');
  if (e.list) g.push('list');
  return g;
}

// Tag family used to colour "per tipologia".
function typeOf(e) {
  const t = e.eff || e.tag;
  if (/^H[1-6]$/.test(t)) return 'heading';
  if (t === 'P') return 'para';
  if (t === 'Figure') return 'figure';
  if (['Table', 'TR', 'TH', 'TD', 'THead', 'TBody', 'TFoot'].includes(t)) return 'table';
  if (['L', 'LI', 'Lbl', 'LBody'].includes(t)) return 'list';
  if (t === 'Link') return 'link';
  if (t === 'Span') return 'span';
  return 'other';
}

const worse = (a, b) => (SEV_RANK[b] > SEV_RANK[a] ? b : a);

// Severity of a single element = worst of its intrinsic problems and the
// category-level findings that apply to its group.
function elementSeverity(e) {
  let s = 'none';
  if (e.figure && !e.hasAlt) s = worse(s, 'issue');
  if (e.empty) s = worse(s, e.heading ? 'issue' : 'warning');
  if (e.linkable) s = worse(s, 'warning');
  elementGroups(e).forEach(g => {
    if (GROUP_LEVEL.has(g) && state.groupSeverity[g]) s = worse(s, state.groupSeverity[g]);
  });
  return s;
}

// Pre-compute, from the avalpdf findings, the worst severity seen per group.
function computeGroupSeverity(d) {
  const gs = {};
  [...d.issues, ...d.warnings].forEach(f => {
    const g = findingGroup(f);
    if (!g) return;
    gs[g] = worse(gs[g] || 'none', f.severity);
  });
  state.groupSeverity = gs;
}

async function renderViewer(structure) {
  const wrap = $('#pdfPages');
  wrap.innerHTML = '';
  state.pages = []; state.overlays = []; state.allBoxes = [];
  $('#untaggedBadge').classList.toggle('is-hidden', structure.tagged !== false);

  const buf = new Uint8Array(state.buffer.slice(0));
  const pdf = await pdfjsLib.getDocument({ data: buf }).promise;
  const dpr = window.devicePixelRatio || 1;

  for (let p = 1; p <= pdf.numPages; p++) {
    const page = await pdf.getPage(p);
    const vp = page.getViewport({ scale: SCALE });
    const pageEl = document.createElement('div');
    pageEl.className = 'pdf-page';
    pageEl.style.width = vp.width + 'px';
    pageEl.style.height = vp.height + 'px';

    const canvas = document.createElement('canvas');
    canvas.width = Math.floor(vp.width * dpr);
    canvas.height = Math.floor(vp.height * dpr);
    canvas.style.width = vp.width + 'px';
    canvas.style.height = vp.height + 'px';
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    pageEl.appendChild(canvas);

    const ov = document.createElement('div');
    ov.className = 'pdf-overlay';
    pageEl.appendChild(ov);
    wrap.appendChild(pageEl);

    state.overlays[p - 1] = { vp, ov };
    page.render({ canvasContext: ctx, viewport: vp });

    // Untagged document: no structure to outline, so flag the WHOLE page as an
    // error with a full-page red box (same fill opacity used for errors).
    if (structure.tagged === false) {
      const u = document.createElement('div');
      u.className = 'pbox pbox--untagged';
      u.style.cssText = `left:0;top:0;width:${vp.width}px;height:${vp.height}px;color:${SEV_COLOR.issue}`;
      u.title = 'Pagina non taggata — il documento non ha una struttura di accessibilità';
      ov.appendChild(u);
    }
  }

  // Build a box for EVERY tagged element that has a bounding box, so the whole
  // structure is visible (like the manual-tagging tool).
  (structure.elements || []).forEach(e => {
    (e.boxes || []).forEach(([pg, bb]) => {
      const o = state.overlays[pg];
      if (!o) return;
      const r = o.vp.convertToViewportRectangle(bb);
      const x = Math.min(r[0], r[2]), y = Math.min(r[1], r[3]);
      const w = Math.abs(r[2] - r[0]), h = Math.abs(r[3] - r[1]);
      if (w < 1 || h < 1) return;
      const box = document.createElement('div');
      box.className = 'pbox';
      box.style.cssText = `left:${x}px;top:${y}px;width:${w}px;height:${h}px`;
      box.addEventListener('mouseenter', ev => showTip(ev, e));
      box.addEventListener('mousemove', moveTip);
      box.addEventListener('mouseleave', hideTip);
      box.addEventListener('click', ev => { ev.stopPropagation(); selectElement(e.idx, false); });
      o.ov.appendChild(box);
      state.allBoxes.push({ el: e, dom: box, page: pg });
    });
  });

  applyZoom();
  // Larger containers go to the BACK and smaller (more specific) tags to the
  // FRONT via z-index, so hover/click always hits the innermost tag — you then
  // drill in/out through the hierarchy with the navigator.
  state.allBoxes.sort((a, b) => area(b.dom) - area(a.dom));
  state.allBoxes.forEach((b, i) => { b.baseZ = i + 1; b.dom.style.zIndex = b.baseZ; });

  // index the structure for hierarchy navigation (parent/children/siblings)
  state.flatEls = structure.elements || [];
  state.idxToPos = {};
  state.boxesByIdx = {};
  state.flatEls.forEach((e, i) => { state.idxToPos[e.idx] = i; });
  state.allBoxes.forEach(b => {
    (state.boxesByIdx[b.el.idx] = state.boxesByIdx[b.el.idx] || []).push(b.dom);
  });
  state.minDepth = state.flatEls.reduce((m, e) => Math.min(m, e.depth), Infinity);
  clearSelection();

  paintBoxes();
}

/* --------------------------------------------------- hierarchy navigation --- */
function elPos(el) { return state.idxToPos[el.idx]; }

function ancestorsOf(el) {            // outermost → immediate parent
  const arr = []; let d = el.depth; const i = elPos(el);
  for (let j = i - 1; j >= 0 && d > state.minDepth; j--) {
    if (state.flatEls[j].depth === d - 1) { arr.unshift(state.flatEls[j]); d--; }
  }
  return arr;
}
function childrenOf(el) {
  const i = elPos(el), res = [];
  for (let j = i + 1; j < state.flatEls.length; j++) {
    const e = state.flatEls[j];
    if (e.depth <= el.depth) break;
    if (e.depth === el.depth + 1) res.push(e);
  }
  return res;
}
function siblingsOf(el) {
  const anc = ancestorsOf(el), parent = anc[anc.length - 1];
  if (parent) return childrenOf(parent);
  return state.flatEls.filter(e => e.depth === state.minDepth);
}

function navLabel(e) { return e.eff || e.tag; }

function selectElement(idx, scroll) {
  const el = state.flatEls[state.idxToPos[idx]];
  if (!el) return;
  state.selected = idx;
  document.querySelectorAll('.pbox--selected').forEach(d => {
    d.classList.remove('pbox--selected');
    if (d._bz != null) { d.style.zIndex = d._bz; d._bz = null; }
  });
  const doms = state.boxesByIdx[idx] || [];
  doms.forEach(d => { d._bz = d.style.zIndex; d.classList.add('pbox--selected'); d.style.zIndex = 2000; });
  if (scroll && doms[0]) doms[0].scrollIntoView({ block: 'center', behavior: 'smooth' });
  renderNavigator(el);
}

function clearSelection() {
  state.selected = null;
  document.querySelectorAll('.pbox--selected').forEach(d => {
    d.classList.remove('pbox--selected');
    if (d._bz != null) { d.style.zIndex = d._bz; d._bz = null; }
  });
  const bar = $('#selBar'); if (bar) bar.classList.add('is-hidden');
}

function renderNavigator(el) {
  const path = [...ancestorsOf(el), el];
  $('#selCrumbs').innerHTML = path.map((e, i) => {
    const cur = i === path.length - 1;
    return `<button type="button" class="crumb${cur ? ' is-current' : ''}" data-idx="${e.idx}">${esc(navLabel(e))}</button>` +
           (cur ? '' : '<span class="crumb-sep">›</span>');
  }).join('');
  $$('#selCrumbs .crumb').forEach(c => c.addEventListener('click', () => selectElement(+c.dataset.idx, true)));

  const anc = ancestorsOf(el), kids = childrenOf(el), sibs = siblingsOf(el);
  const pos = sibs.findIndex(s => s.idx === el.idx);
  const wire = (id, ok, target) => {
    const b = $('#' + id);
    b.disabled = !ok;
    b.onclick = ok ? () => selectElement(target, true) : null;
  };
  wire('selParent', anc.length > 0, anc.length ? anc[anc.length - 1].idx : 0);
  wire('selChild', kids.length > 0, kids.length ? kids[0].idx : 0);
  wire('selPrev', pos > 0, pos > 0 ? sibs[pos - 1].idx : 0);
  wire('selNext', pos >= 0 && pos < sibs.length - 1, (pos >= 0 && pos < sibs.length - 1) ? sibs[pos + 1].idx : 0);
  $('#selBar').classList.remove('is-hidden');
}

function initSelection() {
  $('#selClose').addEventListener('click', clearSelection);
  document.addEventListener('keydown', e => { if (e.key === 'Escape') clearSelection(); });
  $('#pdfScroll').addEventListener('click', e => {
    const t = e.target;
    if (t.id === 'pdfScroll' || t.id === 'pdfPages' || t.classList.contains('pdf-page') ||
        t.classList.contains('pdf-overlay') || t.tagName === 'CANVAS') clearSelection();
  });
}

function area(dom) {
  return parseFloat(dom.style.width) * parseFloat(dom.style.height);
}

// Recolour every box according to the active colour mode (severity / type).
function paintBoxes() {
  const mode = state.colorMode;
  state.allBoxes.forEach(b => {
    const sev = elementSeverity(b.el);
    const color = mode === 'severity' ? SEV_COLOR[sev] : TYPE_COLOR[typeOf(b.el)];
    b.dom.style.color = color;
    // In severity mode, fade the problem-free tags so errors/warnings pop.
    b.dom.classList.toggle('pbox--faint', mode === 'severity' && sev === 'none');
  });
  renderLegend();
}

function renderLegend() {
  const items = LEGEND[state.colorMode] || [];
  $('#viewerLegend').innerHTML = items.map(([c, label]) =>
    `<span class="legend-item"><span class="swatch" style="color:${c}"></span>${esc(label)}</span>`).join('');
}

function initColorMode() {
  $$('.seg[data-mode]').forEach(seg => seg.addEventListener('click', () => {
    state.colorMode = seg.dataset.mode;
    $$('.seg[data-mode]').forEach(s => {
      const on = s === seg;
      s.classList.toggle('is-active', on);
      s.setAttribute('aria-pressed', on);
    });
    paintBoxes();
  }));
}

function locate(group) {
  const matches = state.allBoxes.filter(b => elementGroups(b.el).includes(group));
  if (!matches.length) { toast('Nessun elemento da evidenziare.'); return; }
  matches[0].dom.scrollIntoView({ block: 'center', behavior: 'smooth' });
  matches.forEach(b => {
    const bz = b.dom.style.zIndex;
    b.dom.classList.add('flash');
    b.dom.style.zIndex = 1500;
    setTimeout(() => { b.dom.classList.remove('flash'); b.dom.style.zIndex = bz; }, 1500);
  });
  toast(`${matches.length} element${matches.length === 1 ? 'o' : 'i'} evidenziat${matches.length === 1 ? 'o' : 'i'}.`);
}

/* tooltips */
function showTip(ev, e) {
  const tip = $('#boxTip');
  const tag = TAG_LABEL[e.eff] || e.eff || e.tag;
  let extra = '';
  if (e.figure && !e.hasAlt) extra = ' · <strong>manca alt</strong>';
  else if (e.empty) extra = ' · <strong>vuoto</strong>';
  else if (e.linkable) extra = ' · <strong>link sospetto</strong>';
  else if (e.hasAlt) extra = ' · alt: ' + esc(e.alt.slice(0, 60));
  const txt = e.text ? esc(e.text.slice(0, 90)) : '<em>—</em>';
  const path = [...ancestorsOf(e), e].map(x => esc(navLabel(x)));
  const crumb = path.length > 1 ? `<div class="tip-path">${path.join(' › ')}</div>` : '';
  tip.innerHTML = `<strong>${esc(tag)}</strong>${extra}<br>${txt}${crumb}`;
  tip.classList.remove('is-hidden');
  moveTip(ev);
}
function moveTip(ev) {
  const tip = $('#boxTip');
  let x = ev.clientX + 14, y = ev.clientY + 14;
  const r = tip.getBoundingClientRect();
  if (x + r.width > window.innerWidth - 10) x = ev.clientX - r.width - 14;
  if (y + r.height > window.innerHeight - 10) y = ev.clientY - r.height - 14;
  tip.style.left = x + 'px'; tip.style.top = y + 'px';
}
function hideTip() { $('#boxTip').classList.add('is-hidden'); }

/* zoom */
function applyZoom() {
  $$('#pdfPages .pdf-page').forEach(p => { p.style.zoom = state.zoom; });
  $('#zoomLabel').textContent = Math.round(state.zoom * 100) + '%';
}
function initZoom() {
  $('#zoomIn').addEventListener('click', () => { state.zoom = Math.min(2.5, state.zoom + 0.15); applyZoom(); });
  $('#zoomOut').addEventListener('click', () => { state.zoom = Math.max(0.5, state.zoom - 0.15); applyZoom(); });
}

/* ---------------------------------------------------------------- helpers */
function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

/* ------------------------------------------------------------------- init */
initUpload();
initFilters();
initColorMode();
initZoom();
initSelection();
