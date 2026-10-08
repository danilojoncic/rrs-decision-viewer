// Run with Node and Playwright available; uses the installed Chrome browser.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1050 }, offline: true });
  const page = await context.newPage();
  const errors = [], remote = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('request', r => { if (/^https?:/.test(r.url())) remote.push(r.url()); });
  const url = pathToFileURL(path.resolve(__dirname, '../Decision Viewer.html')).href;
  const check = async (name, fn) => { await fn(); console.log('PASS', name); };
  const count = async () => parseInt(await page.locator('#result-count').innerText(), 10);
  const search = async text => { await page.locator('#search').fill(text); await page.locator('#search-form').evaluate(el => el.requestSubmit()); await page.waitForTimeout(200); };
  await page.goto(url);
  const data = await page.evaluate(() => window.DECISION_VIEWER_DATA);
  await check('Build date and accessible information dialog', async () => {
    assert.equal(await page.locator('#updated-at').getAttribute('datetime'),new Date(data.generated_at).toISOString());
    assert(!(await page.locator('#updated-at').innerText()).includes('—'));
    await page.locator('#info-toggle').click();
    assert(await page.locator('#info-dialog').isVisible());
    assert(await page.locator('#info-close').evaluate(el=>el===document.activeElement));
    await page.keyboard.press('Escape');
    assert(!(await page.locator('#info-dialog').isVisible()));
    assert(await page.locator('#info-toggle').evaluate(el=>el===document.activeElement));
    await page.locator('#info-toggle').click();
    await page.locator('#info-close').click();
    assert(!(await page.locator('#info-dialog').isVisible()));
  });
  await check('Theme follows system, persists selection, and works on Pages assets', async () => {
    await page.emulateMedia({colorScheme:'dark'});
    await page.waitForFunction(()=>document.documentElement.dataset.theme==='dark');
    assert.equal(await page.locator('html').getAttribute('data-theme'),'dark');
    await page.locator('#theme-toggle').click();
    assert.equal(await page.locator('html').getAttribute('data-theme'),'light');
    await page.reload();
    assert.equal(await page.locator('html').getAttribute('data-theme'),'light');
    await page.locator('#theme-toggle').click();
    await page.locator('.decision-card').first().click();
    assert.equal(await page.locator('.decision-card:not(.active)').first().evaluate(el=>getComputedStyle(el).backgroundColor),'rgb(25, 35, 45)');
    await page.screenshot({path:'/private/tmp/decision-dark.png',fullPage:true});
    assert(!/read.only|library/i.test(await page.locator('body').innerText()));
    await page.locator('#theme-toggle').click();
    const hosted=await context.newPage();
    await hosted.goto(pathToFileURL(path.resolve(__dirname,'../docs/index.html')).href);
    assert.equal(await hosted.locator('.decision-card').count(),24);
    const policy=await hosted.locator('meta[http-equiv="Content-Security-Policy"]').getAttribute('content');
    assert(policy.includes("default-src 'none'"));
    assert(policy.includes("connect-src 'none'"));
    assert.equal(await hosted.locator('script:not([src])').count(),0);
    await hosted.locator('#theme-toggle').click();
    await hosted.close();
  });
  await check('All decisions load directly from file:// with networking disabled', async () => {
    assert.equal(await count(), data.total); assert.equal(await page.locator('.decision-card').count(), 24);
    assert.equal(await page.locator('script[src],link[rel=stylesheet]').count(), 0);
  });
  await check('Jury fields and filters are absent from the viewer and bundle', async () => {
    assert.equal(await page.locator('#judge-search,#judge-options,#judge-mode').count(),0);
    for (const record of data.decisions) {
      for (const key of ['jury','jury_type','jury_chair','jury_members','judges','judge_keys','review_flags','needs_review','search_text']) assert(!(key in record));
    }
    assert(!('judges' in data.facets));
  });
  await page.screenshot({path:'/private/tmp/decision-desktop.png',fullPage:true});
  await check('Full-text, phrase, accents, and empty search', async () => {
    await search('"wind conditions"'); assert((await count())>0); assert((await count())<data.total);
    await search('rule:11'); assert.equal(await count(),data.decisions.filter(d=>d.rule_keys.includes('11')).length);
    const exactRuleCount=await count();await search('rule:11 -contact');assert(await count()<exactRuleCount);
    await search('event:"Kieler Woche"');assert(await count()>0);assert(await count()<data.total);
    await search('zzzzunmatchablezzzz'); assert.equal(await count(),0); assert(await page.getByRole('heading',{name:'No decisions found'}).isVisible());
    await search('Pawłowski'); const accented=await count();await search('Pawlowski');assert.equal(await count(),accented);
    await search(''); assert.equal(await count(),data.total);
  });
  await check('Combined event, type, rule and year filters', async () => {
    const d=data.decisions.find(d=>d.rule_keys.length);
    await page.locator('#event-filter').selectOption(d.event);
    await page.locator('#type-filter').selectOption(d.type);
    await page.locator('[data-facet="rule"]').evaluateAll((els,key)=>{const el=els.find(e=>e.value===key);el.checked=true;el.dispatchEvent(new Event('change',{bubbles:true}));},d.rule_keys[0]);
    assert.equal(await count(),data.decisions.filter(x=>x.event===d.event&&x.type===d.type&&x.rule_keys.includes(d.rule_keys[0])).length);
    assert(await count()>0); await page.locator('[data-action="reset"]').first().click();
    const pair=data.decisions.find(x=>x.rule_keys.includes('11')&&x.rule_keys.includes('14a'));
    assert(pair);await page.locator('[data-facet="rule"][value="11"]').check();await page.locator('[data-facet="rule"][value="14a"]').check();
    const anyCount=await count();await page.locator('#rule-mode').selectOption('all');assert(await count()<anyCount);assert(await count()>0);
    await page.locator('[data-action="reset"]').first().click();
    const years=await page.locator('#year-filter option').evaluateAll(els=>els.map(e=>e.value).filter(Boolean));
    assert(years.length>0); await page.locator('#year-filter').selectOption(years[0]);assert(await count()>0);assert(await count()<data.total);
    await page.locator('[data-action="reset"]').first().click();
  });
  await check('Facet search, removable filters and pagination', async () => {
    await page.locator('#rule-search').fill('zzzz');assert.equal(await page.locator('#rule-options label:visible').count(),0);
    await page.locator('[data-action="reset"]').first().click();assert(await page.locator('#rule-options label:visible').count()>0);
    await search('contact');await page.locator('[data-remove="q"]').click();assert.equal(await count(),data.total);
    const id=await page.locator('.decision-card').first().getAttribute('data-open');
    await page.getByRole('button',{name:'Next results page'}).click();assert.notEqual(await page.locator('.decision-card').first().getAttribute('data-open'),id);
    await page.getByRole('button',{name:'Previous results page'}).click();assert.equal(await page.locator('.decision-card').first().getAttribute('data-open'),id);
  });
  await check('Full case opens immediately and stays accessible after reload', async () => {
    await page.locator('.decision-card').first().click();
    const id=await page.locator('.decision-card.active').getAttribute('data-open');
    for(const key of ['procedure','facts','rules','conclusions','decision']) {
      assert(await page.locator(`[data-section="${key}"] .section-items`).isVisible());
    }
    assert.equal(await page.locator('#study-mode,#case-note,[data-action="reveal"],[data-action="export"],[data-collection]').count(),0);
    await page.reload();assert.equal(await page.locator('.decision-card.active').getAttribute('data-open'),id);
    assert(await page.locator('[data-section="decision"] .section-items').isVisible());
    await page.screenshot({path:'/private/tmp/decision-reader.png',fullPage:true});
  });
  await check('Read-only viewer ignores legacy edits without erasing them', async () => {
    const original=await page.locator('.case-header h2').innerText();
    const id=await page.locator('.decision-card.active').getAttribute('data-open');
    await page.evaluate(id=>localStorage.setItem('decision-viewer.edits.v1',JSON.stringify({edits:{[id]:{data:{event:'Legacy edited title'}}}})),id);
    await page.reload();
    assert.equal(await page.locator('.case-header h2').innerText(),original);
    assert.equal(await page.locator('[data-action="edit"],#edit-dialog,#manage-edits,input[type=file]').count(),0);
    assert((await page.evaluate(()=>localStorage.getItem('decision-viewer.edits.v1'))).includes('Legacy edited title'));
  });
  await check('Search aliases and exact phrases', async () => {
    await search('rules:11'); const n=await count(); await search('rule:11'); assert.equal(await count(),n);
    await search('"ontact"'); assert.equal(await count(),0);
    await search('');await page.locator('.decision-card').first().click();
  });
  await check('Expanded view, navigation, rule links and back navigation', async () => {
    await page.locator('[data-action="focus"]').click();assert(await page.locator('body').evaluate(el=>el.classList.contains('focus-mode')));
    await page.keyboard.press('Escape');assert(!(await page.locator('body').evaluate(el=>el.classList.contains('focus-mode'))));
    const first=await page.locator('.decision-card.active').getAttribute('data-open');
    await page.locator('[data-action="next"]').click();assert.notEqual(await page.locator('.decision-card.active').getAttribute('data-open'),first);
    await page.goBack();assert.equal(await page.locator('.decision-card.active').getAttribute('data-open'),first);
    await page.locator('[data-rule-link]').first().click();assert(await count()>0);assert(await count()<data.total);
    await page.locator('[data-action="reset"]').first().click();
  });
  await check('Sorting, section state, and printing the full record', async () => {
    await page.locator('#sort').selectOption('rules');
    const first=await page.locator('.decision-card').first().getAttribute('data-open');
    assert.equal(data.decisions.find(d=>d.id===first).rules.length,Math.max(...data.decisions.map(d=>d.rules.length)));
    await page.locator('#sort').selectOption('newest');await page.locator('.decision-card').first().click();
    await page.locator('[data-section="procedure"] summary').click();
    const wasOpen=await page.locator('[data-section="procedure"]').getAttribute('open');
    await page.locator('[data-action="focus"]').click();assert.equal(await page.locator('[data-section="procedure"]').getAttribute('open'),wasOpen);
    await page.locator('[data-action="focus"]').click();
    await page.evaluate(()=>window.dispatchEvent(new Event('beforeprint')));
    await page.emulateMedia({media:'print'});
    assert(await page.locator('[data-section="procedure"] .section-items').isVisible());
    assert(!(await page.locator('.results-pane').isVisible()));
    await page.emulateMedia({media:'screen'});await page.evaluate(()=>window.dispatchEvent(new Event('afterprint')));
    assert.equal(await page.locator('[data-section="procedure"]').getAttribute('open'),wasOpen);
    await page.locator('#sort').selectOption('event');
  });
  await check('Mobile layout and filter drawer have no horizontal overflow', async () => {
    await page.setViewportSize({width:390,height:844});await page.locator('[data-action="reset"]').first().evaluate(el=>el.click());
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await page.locator('#filter-toggle').click();assert(await page.locator('#filters').isVisible());
    await page.locator('#filter-toggle').click();assert(!(await page.locator('#filters').isVisible()));
    await page.locator('.decision-card').first().click();
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await page.screenshot({path:'/private/tmp/decision-mobile.png',fullPage:true});
  });
  await check('Storage denied and malformed URL remain usable', async () => {
    const denied=await context.newPage();await denied.addInitScript(()=>{Object.defineProperty(window,'localStorage',{get(){throw new Error('denied');}});});
    await denied.goto(url+'#case/%E0%A4%A');assert.equal(parseInt(await denied.locator('#result-count').innerText()),data.total);
    await denied.locator('.decision-card').first().click();assert(await denied.locator('[data-section="decision"] .section-items').isVisible());
    await denied.close();
  });
  assert.deepEqual(errors,[]);assert.deepEqual(remote,[]);
  console.log('PASS No JavaScript errors or network requests');
  await browser.close();
})().catch(e=>{console.error(e);process.exit(1);});
