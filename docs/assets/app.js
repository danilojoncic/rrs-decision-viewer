(() => {
'use strict';

const themeToggle = document.getElementById('theme-toggle');
const systemTheme = matchMedia('(prefers-color-scheme: dark)');
let manualTheme = false;
try { manualTheme = ['light','dark'].includes(localStorage.getItem('decision-viewer.theme')); } catch {}
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const dark = theme === 'dark';
  themeToggle.setAttribute('aria-pressed', String(dark));
  themeToggle.textContent = dark ? 'Light mode' : 'Dark mode';
  document.querySelector('meta[name="theme-color"]').content = dark ? '#141c24' : '#ffffff';
}
applyTheme(document.documentElement.dataset.theme || 'light');
themeToggle.addEventListener('click', () => {
  const theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  manualTheme = true;
  applyTheme(theme);
  try { localStorage.setItem('decision-viewer.theme', theme); } catch {}
});
systemTheme.addEventListener('change', event => { if (!manualTheme) applyTheme(event.matches ? 'dark' : 'light'); });

const DATA = window.DECISION_VIEWER_DATA;
const $ = id => document.getElementById(id);
const infoDialog = $('info-dialog');
$('info-toggle').addEventListener('click', () => infoDialog.showModal());
$('info-close').addEventListener('click', () => infoDialog.close());
infoDialog.addEventListener('click', event => {
  const box = infoDialog.getBoundingClientRect();
  if (event.target === infoDialog && (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom)) infoDialog.close();
});
const builtAt = new Date(DATA?.generated_at);
if (!Number.isNaN(builtAt.getTime())) {
  $('updated-at').dateTime = builtAt.toISOString();
  $('updated-at').textContent = new Intl.DateTimeFormat('en-GB', {day:'numeric', month:'short', year:'numeric', timeZone:'UTC'}).format(builtAt);
  $('updated-at').title = `Version built ${builtAt.toISOString()} (UTC)`;
} else $('updated-at').textContent = 'unavailable';

const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const normalize = value => String(value ?? '').toLowerCase().replaceAll('ß', 'ss').replaceAll('ł', 'l').replaceAll('ø', 'o').replaceAll('đ', 'd').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]+/g, ' ').trim();
const compact = value => normalize(value).replaceAll(' ', '');
const asText = value => String(value ?? '').replace(/\s+/g, ' ').trim();
const asList = value => Array.isArray(value) ? value.map(asText).filter(Boolean) : (asText(value) ? [asText(value)] : []);
const deepCopy = value => JSON.parse(JSON.stringify(value));
const collator = new Intl.Collator(undefined, {numeric:true, sensitivity:'base'});
const PAGE_SIZE = 24;
const SEARCH_FIELDS = new Set(['event','rule','party','type','race','fact','decision','conclusion','procedure','source','date']);

if (!DATA?.decisions?.length) {
  $('result-count').textContent = 'The decisions could not be loaded.';
  $('reader').innerHTML = '<div class="empty-state"><h2>Decisions unavailable</h2><p>Please reload the page and try again.</p></div>';
  return;
}

let records = [];
let byId = new Map();
let facets = {events:[], types:[], rules:[], years:[]};
let results = [];
let readerId = null;
let toastTimer;
let searchTimer;
let activeQuery = [];
const sectionState = new Map();
const state = {q:'', event:'', type:'', year:'', rules:new Set(), ruleMode:'any',  sort:'relevance', page:1, id:'', focus:false};

function ruleKey(value) {
  return compact(value).replace(/^rrs/, '');
}

function parseDate(value, year) {
  const text = String(value || '');
  const iso = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (iso) return `${iso[1]}${iso[2]}${iso[3]}`;
  const named = text.match(/^(\d{1,2})\s+([a-z]{3})[a-z]*\s*(\d{4})?/i);
  if (named) {
    const month = ['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'].indexOf(named[2].toLowerCase()) + 1;
    const knownYear = named[3] || year;
    if (knownYear && month) return `${knownYear}${String(month).padStart(2,'0')}${named[1].padStart(2,'0')}`;
  }
  // Never let Date.parse invent a year for incomplete source dates.
  return year ? `${year}0000` : '';
}

function prepareRecord(record) {
  for (const key of ['origin_system','event','type','filename','hearing_datetime','race_number']) record[key] = asText(record[key]);
  for (const key of ['parties','procedural_matters','facts','rules','conclusions','decision','review_flags']) record[key] = asList(record[key]);
  record.type ||= 'Decision';
  record.rule_keys = record.rules.map(ruleKey);
  record.year = (record.hearing_datetime || '').match(/\b(?:19|20)\d{2}\b/)?.[0] || (`${record.event} ${record.filename}`).match(/\b(?:19|20)\d{2}\b/)?.[0] || '';
  record.dateKey = parseDate(record.hearing_datetime, record.year);
  record.fields = {
    event: normalize(record.event),
    type: normalize(record.type),
    party: normalize(record.parties.join(' ')),
    procedure: normalize(record.procedural_matters.join(' ')),
    fact: normalize(record.facts.join(' ')),
    rule: normalize(record.rules.join(' ')),
    conclusion: normalize(record.conclusions.join(' ')),
    decision: normalize(record.decision.join(' ')),
    race: normalize(record.race_number),
    date: normalize(`${record.hearing_datetime} ${record.year}`),
    source: normalize([record.filename, record.origin_system].join(' ')),
  };
  record.fields.all = Object.values(record.fields).join(' ');
  return record;
}

function rebuildRecords() {
  records = DATA.decisions.map(raw => prepareRecord(deepCopy(raw)));
  byId = new Map(records.map(record => [record.id, record]));
  rebuildFacets();
}

function buildFacetRows(kind, keyFunction) {
  const rows = new Map();
  for (const record of records) {
    const values = record.rules;
    const seen = new Set();
    for (const label of values) {
      const key = keyFunction(label);
      if (!key || seen.has(key)) continue;
      seen.add(key);
      const row = rows.get(key) || {key, label, count:0};
      row.count += 1;
      if (label.length < row.label.length) row.label = label;
      rows.set(key, row);
    }
  }
  return [...rows.values()].sort((a,b) => collator.compare(a.label,b.label));
}

function countedValues(field) {
  const counts = new Map();
  for (const record of records) {
    const value = record[field];
    if (value) counts.set(value, (counts.get(value) || 0) + 1);
  }
  return [...counts].map(([label,count]) => ({label,key:label,count})).sort((a,b) => collator.compare(a.label,b.label));
}

function rebuildFacets() {
  facets = {
    events: countedValues('event'),
    types: countedValues('type'),
    years: countedValues('year').sort((a,b) => collator.compare(b.label,a.label)),
    rules: buildFacetRows('rules', ruleKey),
  };
  renderFacetOptions();
}

function renderFacetOptions() {
  for (const [kind, rows] of [['rule',facets.rules]]) {
    $(kind+'-options').innerHTML = rows.map(row => `<label data-facet-label="${esc(normalize(row.label))}"><input type="checkbox" data-facet="${kind}" value="${esc(row.key)}"><span>${esc(row.label)}</span><small>${row.count}</small></label>`).join('');
  }
}

function parseQuery(value) {
  const query = String(value || '').replace(/[“”]/g, '"');
  const clauses = [];
  const pattern = /(^|\s)(-)?(?:([a-z]+):)?(?:"([^"]+)"|(\S+))/gi;
  let match;
  while ((match = pattern.exec(query))) {
    const aliases = {rules:'rule', parties:'party', facts:'fact', conclusions:'conclusion', procedures:'procedure', year:'date', case:'source'};
    const enteredField = (match[3] || '').toLowerCase();
    const candidateField = aliases[enteredField] || enteredField;
    const field = SEARCH_FIELDS.has(candidateField) ? candidateField : 'all';
    const raw = candidateField && field === 'all' ? `${candidateField}:${match[4] || match[5]}` : (match[4] || match[5]);
    const value = normalize(raw);
    if (value) clauses.push({exclude:Boolean(match[2]), field, value, phrase:Boolean(match[4]) || value.includes(' ')});
  }
  return clauses;
}

function textMatches(haystack, clause) {
  if (!haystack) return false;
  if (clause.phrase) return (` ${haystack} `).includes(` ${clause.value} `);
  const words = haystack.split(' ');
  if (/^\d/.test(clause.value) || clause.value.length <= 2) return words.includes(clause.value);
  return words.some(word => word.startsWith(clause.value));
}

function clauseMatches(record, clause) {
  if (clause.field === 'rule') return record.rule_keys.includes(ruleKey(clause.value));
  return textMatches(record.fields[clause.field] || record.fields.all, clause);
}

function queryMatches(record) {
  return activeQuery.every(clause => {
    const matches = clauseMatches(record, clause);
    return clause.exclude ? !matches : matches;
  });
}

function queryScore(record) {
  if (!activeQuery.length) return 0;
  const weights = {event:10,rule:9,party:7,type:6,decision:6,conclusion:5,fact:4,procedure:3,race:3,date:2,source:1};
  let score = 0;
  for (const clause of activeQuery.filter(item => !item.exclude)) {
    if (clause.field !== 'all') {
      if (clauseMatches(record, clause)) score += (weights[clause.field] || 1) * (clause.phrase ? 2 : 1);
      continue;
    }
    for (const [field,weight] of Object.entries(weights)) if (textMatches(record.fields[field], clause)) score += weight * (clause.phrase ? 2 : 1);
  }
  return score;
}

function selectionMatches(keys, selected, mode) {
  if (!selected.size) return true;
  return mode === 'all' ? [...selected].every(key => keys.includes(key)) : keys.some(key => selected.has(key));
}

function filterRecord(record, skip='') {
  if (skip !== 'event' && state.event && state.event !== record.event) return false;
  if (skip !== 'type' && state.type && state.type !== record.type) return false;
  if (skip !== 'year' && state.year && state.year !== record.year) return false;
  if (skip !== 'rules' && !selectionMatches(record.rule_keys, state.rules, state.ruleMode)) return false;
  return queryMatches(record);
}

function getResults() {
  const rows = records.filter(record => filterRecord(record));
  const sort = state.sort === 'relevance' && !activeQuery.length ? 'event' : state.sort;
  return rows.sort((a,b) => {
    if (sort === 'relevance') {
      const difference = queryScore(b) - queryScore(a);
      if (difference) return difference;
    }
    if (sort === 'newest') {
      const difference = b.dateKey.localeCompare(a.dateKey);
      if (difference) return difference;
    }
    if (sort === 'rules' && a.rules.length !== b.rules.length) return b.rules.length - a.rules.length;
    return collator.compare(a.event,b.event) || collator.compare(a.filename,b.filename) || a.id.localeCompare(b.id);
  });
}

function highlightTerms() {
  return activeQuery.filter(clause => !clause.exclude).map(clause => clause.value).sort((a,b) => b.length-a.length);
}

function highlight(value) {
  const text = String(value || '');
  const needles = highlightTerms();
  if (!needles.length) return esc(text);
  let normalized = '';
  const offsets = [];
  for (let index=0; index<text.length; index++) {
    const part = text[index].toLowerCase().replaceAll('ß','ss').replaceAll('ł','l').replaceAll('ø','o').replaceAll('đ','d').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]/g,' ');
    for (const char of part) {
      if (char === ' ' && normalized.endsWith(' ')) continue;
      normalized += char;
      offsets.push(index);
    }
  }
  const spans = [];
  for (const needle of needles) {
    let position = 0;
    while ((position = normalized.indexOf(needle, position)) !== -1) {
      spans.push([offsets[position], offsets[position+needle.length-1]+1]);
      position += Math.max(1, needle.length);
    }
  }
  spans.sort((a,b) => a[0]-b[0]);
  const merged = [];
  for (const span of spans) {
    const last = merged.at(-1);
    if (last && span[0] <= last[1]) last[1] = Math.max(last[1], span[1]);
    else merged.push(span);
  }
  let end = 0;
  let html = '';
  for (const [start,stop] of merged) {
    html += esc(text.slice(end,start)) + '<mark>' + esc(text.slice(start,stop)) + '</mark>';
    end = stop;
  }
  return html + esc(text.slice(end));
}

function toast(message) {
  clearTimeout(toastTimer);
  $('toast').textContent = message;
  $('toast').hidden = false;
  toastTimer = setTimeout(() => $('toast').hidden = true, 4200);
}

function readLocation() {
  let hash = location.hash.slice(1);
  let params;
  if (hash.startsWith('case/')) {
    params = new URLSearchParams(location.search);
    try { params.set('case', decodeURIComponent(hash.slice(5))); } catch { /* malformed old links simply open the archive */ }
  } else params = new URLSearchParams(hash || location.search);
  for (const key of ['q','event','type','year']) state[key] = params.get(key) || '';
  state.rules = new Set(params.getAll('rule').filter(key => facets.rules.some(row => row.key === key)));
  state.ruleMode = params.get('rule_mode') === 'all' ? 'all' : 'any';
  state.sort = ['event','newest','rules'].includes(params.get('sort')) ? params.get('sort') : 'relevance';
  state.focus = params.get('focus') === '1';
  state.page = Math.max(1, parseInt(params.get('page'),10) || 1);
  state.id = byId.has(params.get('case')) ? params.get('case') : '';
}

function writeLocation(push=false) {
  const params = new URLSearchParams();
  for (const key of ['q','event','type','year']) if (state[key]) params.set(key,state[key]);
  state.rules.forEach(key => params.append('rule',key));
  if (state.ruleMode !== 'any') params.set('rule_mode',state.ruleMode);
  if (state.sort !== 'relevance') params.set('sort',state.sort);
  if (state.page > 1) params.set('page',state.page);
  if (state.id) params.set('case',state.id);
  if (state.focus) params.set('focus','1');
  const next = '#' + params.toString();
  if (location.hash === next) return;
  try { history[push ? 'pushState' : 'replaceState'](null,'',next); } catch { /* Some file viewers disable history. */ }
}

function activeFilterCount() {
  return ['q','event','type','year'].filter(key => state[key]).length + state.rules.size;
}

function updateStats() {
  $('total-count').textContent = records.length.toLocaleString();
  $('event-count').textContent = facets.events.length.toLocaleString();
  const count = activeFilterCount();
  $('filter-badge').hidden = !count;
  $('filter-badge').textContent = count;
  $('workspace-summary').textContent = count ? `${count} active ${count === 1 ? 'filter' : 'filters'}` : 'Browse every case';
}

function setSelectOptions(id, rows, placeholder, counts) {
  const select = $(id);
  const current = select.value;
  select.innerHTML = `<option value="">${placeholder}</option>` + rows.map(row => {
    const count = counts.get(row.key) || 0;
    const selected = current === row.key;
    return `<option value="${esc(row.key)}" ${!count && !selected ? 'disabled' : ''}>${esc(row.label)} (${count})</option>`;
  }).join('');
  select.value = current;
}

function countsFor(field, values) {
  const counts = new Map(values.map(row => [row.key,0]));
  for (const record of records.filter(item => filterRecord(item,field))) {
    const key = field === 'event' ? record.event : field === 'type' ? record.type : record.year;
    if (key) counts.set(key,(counts.get(key)||0)+1);
  }
  return counts;
}

function controls() {
  $('search').value = state.q;
  $('sort').value = state.sort;
  $('rule-mode').value = state.ruleMode;
  setSelectOptions('event-filter',facets.events,'All events',countsFor('event',facets.events));
  setSelectOptions('type-filter',facets.types,'All types',countsFor('type',facets.types));
  setSelectOptions('year-filter',facets.years,'All years',countsFor('year',facets.years));
  $('event-filter').value = state.event;
  $('type-filter').value = state.type;
  $('year-filter').value = state.year;
}

function updateFacets() {
  for (const kind of ['rule']) {
    const group = 'rules';
    const counts = new Map();
    for (const record of records.filter(item => filterRecord(item,group) && (state[kind+'Mode'] !== 'all' || selectionMatches(item[kind+'_keys'], state[group], 'all')))) {
      for (const key of new Set(record[kind+'_keys'])) counts.set(key,(counts.get(key)||0)+1);
    }
    $(kind+'-options').querySelectorAll('input').forEach(input => {
      const count = counts.get(input.value) || 0;
      const selected = state[group].has(input.value);
      input.checked = selected;
      input.disabled = !count && !selected;
      input.parentElement.classList.toggle('unavailable', !count && !selected);
      input.parentElement.querySelector('small').textContent = count;
    });
    $(group+'-count').textContent = state[group].size ? state[group].size : '';
    filterFacet(kind);
  }
}

function filterFacet(kind) {
  const query = normalize($(kind+'-search').value);
  let count = 0;
  $(kind+'-options').querySelectorAll('label').forEach(label => {
    label.hidden = !query.split(' ').every(term => label.dataset.facetLabel.includes(term));
    if (!label.hidden) count++;
  });
  let empty = $(kind+'-options').querySelector('.facet-empty');
  if (!empty) {
    empty = document.createElement('p');
    empty.className = 'facet-empty';
    empty.textContent = 'No matching options.';
    $(kind+'-options').append(empty);
  }
  empty.hidden = count > 0;
}

function chips() {
  const rows = [];
  for (const key of ['q','event','type','year']) if (state[key]) rows.push([key,'',key === 'q' ? `Search: ${state[key]}` : state[key]]);
  for (const group of ['rules']) {
    for (const key of state[group]) rows.push([group,key,facets[group].find(row => row.key === key)?.label || key]);
  }
  $('selected-filters').hidden = !rows.length;
  $('selected-filters').innerHTML = rows.map(([key,value,label]) => `<button type="button" data-remove="${key}" data-value="${esc(value)}" aria-label="Remove ${esc(label)} filter"><span>${esc(label)}</span><b aria-hidden="true">×</b></button>`).join('') + (rows.length > 1 ? '<button type="button" data-action="reset" class="clear-chip">Clear all</button>' : '');
}

function caseNumber(record) {
  return record.filename.replace(/\.json$/i,'').match(/(?:decision[ _]|case[ _]|protest[ _])(\d+)/i)?.[1] || '';
}

function matchSnippet(record) {
  const candidates = [
    ['Decision',record.decision],['Conclusion',record.conclusions],['Fact',record.facts],['Party',record.parties],['Procedure',record.procedural_matters]
  ];
  if (activeQuery.some(clause => !clause.exclude)) {
    for (const [label,items] of candidates) {
      const item = items.find(value => activeQuery.filter(clause => !clause.exclude).some(clause => textMatches(normalize(value), {...clause,field:'all'})));
      if (item) return {label,text:item};
    }
  }
  return {label:record.parties.length ? 'Parties' : 'Fact', text:record.parties.join(' · ') || record.facts[0] || 'Open the full decision record.'};
}

function renderList() {
  const pages = Math.max(1,Math.ceil(results.length/PAGE_SIZE));
  state.page = Math.min(state.page,pages);
  const start = (state.page-1)*PAGE_SIZE;
  $('result-count').textContent = `${results.length.toLocaleString()} decision${results.length === 1 ? '' : 's'}`;
  $('result-context').textContent = activeQuery.length ? ' matching your search' : (activeFilterCount() ? ' after filters' : ' in the archive');
  $('results').innerHTML = results.slice(start,start+PAGE_SIZE).map(record => {
    const number = caseNumber(record);
    const snippet = matchSnippet(record);
    return `<button class="decision-card${record.id === state.id ? ' active' : ''}" type="button" data-open="${esc(record.id)}" ${record.id === state.id ? 'aria-current="true"' : ''} aria-label="Open ${esc(record.event)}, ${esc(record.filename)}">
      <span class="card-top"><span class="eyebrow">${highlight(record.type)}</span><span class="card-markers"><span class="case-number">${number ? '#'+esc(number) : esc(record.year)}</span></span></span>
      <span class="card-title">${highlight(record.event || record.filename)}</span>
      <span class="card-snippet"><b>${esc(snippet.label)}</b>${highlight(snippet.text)}</span>
      <span class="card-bottom">${record.rules.slice(0,4).map(rule => `<span class="chip">${highlight(rule)}</span>`).join('')}${record.rules.length>4 ? `<span class="chip">+${record.rules.length-4}</span>` : ''}${record.needs_review ? '<span class="source-mark">Source flagged</span>' : ''}</span>
    </button>`;
  }).join('') || `<div class="empty-state"><span class="empty-icon" aria-hidden="true">⌕</span><h2>No decisions found</h2><p>Try removing a filter, shortening a phrase, or checking a field prefix.</p><button type="button" data-action="reset">Clear search & filters</button></div>`;
  $('pagination').innerHTML = results.length ? `<button type="button" data-page="${state.page-1}" ${state.page===1?'disabled':''} aria-label="Previous results page">← Previous</button><span>${start+1}–${Math.min(start+PAGE_SIZE,results.length)} <i>·</i> Page ${state.page} of ${pages}</span><button type="button" data-page="${state.page+1}" ${state.page===pages?'disabled':''} aria-label="Next results page">Next →</button>` : '';
}

function section(key,number,title,items,open=false) {
  const content = items.length ? key === 'facts' ? `<ol>${items.map(item => `<li>${highlight(item)}</li>`).join('')}</ol>` : items.map(item => `<p>${highlight(item)}</p>`).join('') : '<p class="missing-text">No text was provided in the source record.</p>';
  return `<details class="decision-section" data-section="${key}" ${open?'open':''}><summary><span class="section-number">${number}</span><span>${title}<small>${items.length || ''}</small></span></summary><div class="section-items">${content}</div></details>`;
}

function rememberSections() {
  if (!readerId) return;
  sectionState.set(readerId,Object.fromEntries([...$('reader').querySelectorAll('.decision-section')].map(element => [element.dataset.section,element.open])));
}

function renderReader(force=false) {
  const record = byId.get(state.id);
  document.body.classList.toggle('focus-mode',Boolean(record && state.focus));
  if (!force && readerId === state.id) return;
  rememberSections();
  readerId = state.id;
  if (!record) {
    $('reader').innerHTML = `<div class="reader-placeholder"><span aria-hidden="true">≋</span><h2>Choose a decision to read</h2><p>Search by incident, filter by rule, or select a case from the result list.</p><div><kbd>/</kbd><small>Focus search</small></div></div>`;
    return;
  }
  const index = results.findIndex(item => item.id === record.id);
  $('reader').innerHTML = `
    <div class="reader-toolbar"><div><span class="eyebrow">CASE DETAILS</span></div><div class="reader-tools"><button type="button" data-action="focus" aria-pressed="${state.focus}">${state.focus?'Exit expanded':'Expand'}</button><button type="button" data-action="print">Print</button><button type="button" data-action="close" aria-label="Close reader">×</button></div></div>
    <header class="case-header"><p class="eyebrow">${highlight(record.type)}${caseNumber(record)?' · CASE '+esc(caseNumber(record)):''}</p><h2>${highlight(record.event || record.filename)}</h2><div class="case-meta"><span>${esc(record.hearing_datetime || record.year || 'Date not recorded')}</span>${record.race_number ? `<span>Race ${esc(record.race_number)}</span>` : ''}<span>${record.facts.length} facts</span><span>${record.rules.length} rules</span></div><div class="parties">${record.parties.map(item => `<span class="party">${highlight(item)}</span>`).join('')}</div></header>
    <div class="reader-content">${record.review_flags.length ? `<div class="review-flags"><strong>Check the source record</strong><span>${record.review_flags.map(esc).join(' · ')}</span></div>` : ''}
      ${section('procedure','01','Procedural matters',record.procedural_matters,true)}
      ${section('facts','02','Facts found',record.facts,true)}
      <details class="decision-section" data-section="rules" open><summary><span class="section-number">03</span><span>Rules that apply<small>${record.rules.length || ''}</small></span></summary><div class="section-items"><div class="rule-links">${record.rules.map((rule,index) => `<button type="button" data-rule-link="${esc(record.rule_keys[index] || ruleKey(rule))}" title="Find decisions with this rule">${highlight(rule)} <span aria-hidden="true">↗</span></button>`).join('') || '<p class="missing-text">No rules recorded.</p>'}</div></div></details>
      ${section('conclusions','04','Conclusions',record.conclusions,true)}
      ${section('decision','05','Decision',record.decision,true)}
      <div class="reader-end"><div class="navigation"><button type="button" data-action="previous" ${index<=0?'disabled':''}>← Previous</button><button type="button" data-action="next" ${index>=results.length-1?'disabled':''}>Next case →</button></div></div>
      <details class="source-info"><summary>Record details</summary><dl><div><dt>Source</dt><dd>${esc(record.filename)}</dd></div>${record.origin_system ? `<div><dt>System</dt><dd>${esc(record.origin_system)}</dd></div>` : ''}</dl></details>
    </div>`;
  const remembered = sectionState.get(record.id);
  if (remembered) $('reader').querySelectorAll('.decision-section').forEach(element => { if (element.dataset.section in remembered) element.open = remembered[element.dataset.section]; });
}

function render({push=false,forceReader=false}={}) {
  activeQuery = parseQuery(state.q);
  results = getResults();
  if (state.id && !results.some(record => record.id === state.id)) { state.id=''; state.focus=false; }
  controls();
  chips();
  updateFacets();
  renderList();
  renderReader(forceReader);
  updateStats();
  writeLocation(push);
}

function refresh() {
  clearTimeout(searchTimer);
  state.page = 1;
  render({forceReader:true});
  $('results').scrollTop = 0;
}

function openCase(id) {
  state.id = id;
  const index = results.findIndex(record => record.id === id);
  if (index >= 0) state.page = Math.floor(index/PAGE_SIZE)+1;
  render({push:true,forceReader:true});
  if (matchMedia('(max-width:720px)').matches) $('reader').scrollIntoView({block:'start'});
  $('reader').focus({preventScroll:true});
}

function reset() {
  clearTimeout(searchTimer);
  Object.assign(state,{q:'',event:'',type:'',year:'',page:1,focus:false,sort:'relevance',ruleMode:'any'});
  state.rules.clear();
  $('rule-search').value = '';
  refresh();
}

let printSections = [];
window.addEventListener('beforeprint',() => {
  printSections = [...$('reader').querySelectorAll('details')].map(element => [element,element.open]);
  printSections.forEach(([element]) => { element.open = true; });
});
window.addEventListener('afterprint',() => printSections.forEach(([element,open]) => { element.open = open; }));

const actions = {
  reset,
  close:() => { state.id=''; state.focus=false; render({push:true}); document.querySelector('.decision-card')?.focus({preventScroll:true}); },
  focus:() => { state.focus=!state.focus; renderReader(true); writeLocation(); },
  previous:() => navigate(-1),
  next:() => navigate(1),
  print:() => window.print(),
};

function navigate(delta) {
  const index = results.findIndex(record => record.id === state.id);
  if (results[index+delta]) openCase(results[index+delta].id);
}

document.addEventListener('click',event => {
  const button = event.target.closest('button');
  if (!button || button.disabled) return;
  if (button.dataset.action) { actions[button.dataset.action]?.(); return; }
  if (button.dataset.open) { openCase(button.dataset.open); return; }
  if (button.dataset.page) { state.page=Number(button.dataset.page); render({push:true}); $('results').scrollTop=0; return; }
  if (button.dataset.remove) {
    const key = button.dataset.remove;
    if (state[key] instanceof Set) state[key].delete(button.dataset.value);
    else state[key] = '';
    refresh();
    return;
  }
  if (button.dataset.ruleLink) {
    state.rules = new Set([button.dataset.ruleLink]);
    state.ruleMode = 'any';
    state.focus = false;
    refresh();
    toast('Filtered to decisions applying this rule.');
    return;
  }
  if (button.dataset.query !== undefined) {
    state.q = button.dataset.query;
    refresh();
    $('search').focus();
  }
});

$('search-form').addEventListener('submit',event => { event.preventDefault(); clearTimeout(searchTimer); state.q=$('search').value.trim(); refresh(); });
$('search').addEventListener('input',() => { clearTimeout(searchTimer); searchTimer=setTimeout(() => { state.q=$('search').value.trim(); refresh(); },170); });
for (const key of ['event','type','year']) $(key+'-filter').addEventListener('change',event => { state[key]=event.target.value; refresh(); });
$('sort').addEventListener('change',event => { state.sort=event.target.value; refresh(); });
$('rule-mode').addEventListener('change',event => { state.ruleMode=event.target.value; refresh(); });
for (const kind of ['rule']) {
  $(kind+'-search').addEventListener('input',() => filterFacet(kind));
  $(kind+'-options').addEventListener('change',event => {
    const input = event.target;
    if (!input.dataset.facet) return;
    const group = 'rules';
    input.checked ? state[group].add(input.value) : state[group].delete(input.value);
    refresh();
  });
}
$('filter-toggle').addEventListener('click',() => { const open=document.body.classList.toggle('filters-open'); $('filter-toggle').setAttribute('aria-expanded',String(open)); });
$('search-tips-toggle').addEventListener('click',() => { const hidden=!$('search-tips').hidden; $('search-tips').hidden=hidden; $('search-tips-toggle').setAttribute('aria-expanded',String(!hidden)); });
document.addEventListener('keydown',event => {
  const typing = event.target.matches('input,textarea,select,[contenteditable=true]');
  if (event.key === '/' && !typing && !event.metaKey && !event.ctrlKey && !event.altKey) { event.preventDefault(); $('search').focus(); }
  if (event.key === 'Escape' && !typing && state.focus) { state.focus=false; renderReader(true); writeLocation(); }
});
window.addEventListener('popstate',() => { readLocation(); render({forceReader:true}); });
window.addEventListener('hashchange',() => { readLocation(); render({forceReader:true}); });

rebuildRecords();
readLocation();
render();
})();
