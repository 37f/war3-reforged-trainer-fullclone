// Real browser, deterministic RPC. No connection to Warcraft III.
const { createRequire } = require('node:module')
const { resolve, extname, sep } = require('node:path')
const fs = require('node:fs/promises'), http = require('node:http'), assert = require('node:assert/strict')
const { chromium } = createRequire(resolve('frontend/package.json'))('playwright-core')
const root = resolve('frontend/dist'), out = resolve(process.argv[2] || '../r34-feature-ui')
const server = http.createServer(async (req, res) => {
  try {
    const path = resolve(root, '.' + decodeURIComponent(new URL(req.url, 'http://localhost').pathname).replace(/\/$/, '/index.html'))
    if (!path.startsWith(root + sep)) { res.writeHead(403); return res.end() }
    res.setHeader('Content-Type', { '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css', '.woff2': 'font/woff2' }[extname(path)] || 'application/octet-stream')
    res.end(await fs.readFile(path))
  } catch { res.writeHead(404); res.end() }
})
;(async () => {
  await fs.mkdir(out, { recursive: true }); await new Promise(r => server.listen(0, '127.0.0.1', r))
  const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true })
  const results = []
  try {
    for (const mode of ['modern', 'classic', 'legacy19']) {
      const page = await browser.newPage({ viewport: { width: 1450, height: 1000 } }), errors = []
      page.on('pageerror', e => errors.push(e.message))
      await page.addInitScript(mode => { localStorage.setItem('war3-interface-mode', mode); localStorage.setItem('war3-page', 'unit') }, mode)
      await page.goto(`http://127.0.0.1:${server.address().port}/?mock=connected`)
      await page.getByTestId('interface-switch').waitFor()
      await page.evaluate(() => {
        const original = window.pywebview.api
        window.__r34options = { army_scope: 'all', item_filter_mode: 'all', item_filter_ids: '' }
        window.__r34calls = []
        window.pywebview.api = new Proxy({
          fullclone_settings: () => ({ success: true, options: window.__r34options }),
          fullclone_set_option: (key, value) => { window.__r34options = { ...window.__r34options, [key]: value }; return { success: true, options: window.__r34options } },
          fullclone_action: action => { window.__r34calls.push({ action, ...window.__r34options }); return { success: true, message: '界面验证' } },
        }, { get: (target, key) => target[key] || original[key] })
      })
      async function elephant() {
        if (mode === 'modern') { await page.getByTestId('chapter-elephant').click(); await page.getByTestId('page-elephant').click() }
        else await page.locator(`[data-${mode === 'classic' ? 'classic' : 'legacy19'}-page="elephant"]`).first().click()
        await page.getByLabel('全军补满范围', { exact: true }).waitFor()
      }
      await elephant()
      const scope = page.getByLabel('全军补满范围', { exact: true })
      const filter = page.getByLabel('物品聚集筛选', { exact: true }), ids = page.getByLabel('物品ID列表', { exact: true })
      assert.equal(await scope.inputValue(), 'all'); assert(await ids.isDisabled())
      for (const value of ['all', 'heroes', 'nonheroes']) {
        await scope.selectOption(value)
        await page.getByRole('button', { name: '选中玩家全军生命魔法全满', exact: true }).click()
        await page.waitForFunction(value => window.__r34calls.at(-1)?.army_scope === value, value)
      }
      await filter.selectOption('include'); await ids.fill('I000 ratf')
      await page.getByRole('button', { name: '聚集全图地面物品（Alt+F2）', exact: true }).click()
      await filter.selectOption('exclude')
      assert.equal(await ids.inputValue(), 'I000 ratf')
      await page.getByRole('button', { name: '聚集全图地面物品（Alt+F2）', exact: true }).click()
      await filter.selectOption('all'); assert(await ids.isDisabled()); assert.equal(await ids.inputValue(), 'I000 ratf')
      // Page navigation must retain both new settings and the inactive draft.
      if (mode === 'modern') { await page.getByTestId('chapter-battle').click(); await page.getByTestId('page-unit').click() }
      else await page.locator(`[data-${mode === 'classic' ? 'classic' : 'legacy19'}-page="unit"]`).first().click()
      await elephant(); assert.equal(await scope.inputValue(), 'nonheroes'); assert.equal(await ids.inputValue(), 'I000 ratf')
      await filter.selectOption('exclude')
      const calls = await page.evaluate(() => window.__r34calls)
      assert.deepEqual(calls.map(c => c.action), ['fill_owner_life_mana','fill_owner_life_mana','fill_owner_life_mana','gather_ground_items','gather_ground_items'])
      assert.equal(calls[3].item_filter_mode, 'include'); assert.equal(calls[4].item_filter_mode, 'exclude'); assert.equal(calls[4].item_filter_ids, 'I000 ratf')
      await ids.scrollIntoViewIfNeeded(); await page.screenshot({ path: resolve(out, `${mode}-r34-items.png`) })
      await scope.scrollIntoViewIfNeeded(); await page.screenshot({ path: resolve(out, `${mode}-r34-army.png`) })
      for (const width of [800,1024,1450]) {
        await page.setViewportSize({ width, height: 1000 })
        assert(await page.evaluate(() => document.body.scrollWidth <= innerWidth), `${mode}:${width}`)
      }
      assert.deepEqual(errors, []); results.push({ mode, scopes: 3, filters: 3, navigation_memory: true, calls, errors })
      await page.close()
    }
    await fs.writeFile(resolve(out, 'results.json'), JSON.stringify({ ok: true, game_access: false, results }, null, 2))
    console.log(JSON.stringify({ ok: true, layouts: results.length, game_access: false }))
  } finally { await browser.close(); server.close() }
})().catch(e => { console.error(e); process.exitCode = 1; server.close() })
