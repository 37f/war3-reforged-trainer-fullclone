// Browser presentation check with the author's demo bridge. No game access.
const { createRequire } = require('node:module')
const { resolve, extname, sep } = require('node:path')
const fs = require('node:fs/promises')
const http = require('node:http')
const assert = require('node:assert/strict')
const { chromium } = createRequire(resolve('frontend/package.json'))('playwright-core')
const root = resolve('frontend/dist')
const out = resolve(process.argv[2] || '../interface-preview')
const server = http.createServer(async (req, res) => {
  try {
    const path = resolve(root, '.' + decodeURIComponent(new URL(req.url, 'http://localhost').pathname).replace(/\/$/, '/index.html'))
    if (!path.startsWith(root + sep)) { res.writeHead(403); return res.end() }
    const mime = { '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.svg': 'image/svg+xml', '.png': 'image/png' }
    res.setHeader('Content-Type', mime[extname(path)] || 'application/octet-stream')
    res.end(await fs.readFile(path))
  } catch { res.writeHead(404); res.end() }
})
;(async () => {
  await fs.mkdir(out, { recursive: true })
  await new Promise(r => server.listen(0, '127.0.0.1', r))
  const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 1 })
    const errors = []; page.on('pageerror', e => errors.push(e.message))
    await page.goto(`http://127.0.0.1:${server.address().port}/?mock=connected`)
    await page.locator('[data-testid="interface-switch"]').waitFor()
    await page.evaluate(() => {
      let options = { owner_enabled: false, owner_mode: 'self', owner_player: 0, target_player: 1, team: 0, replace_id: 'zhyd', color: 0, hero_custom: false, attributes_custom: false, mine_amount: '100000' }
      window.__legacyCalls = []
      const original = window.pywebview.api
      const extra = {
        fullclone_action: (action) => { window.__legacyCalls.push({ extension: action }); return { success: true, message: '界面测试成功' } },
        execute_elephant_action: (action, params) => { window.__legacyCalls.push({ native: action, params }); return { success: true } },
        fullclone_settings: () => ({ success: true, options }),
        fullclone_set_option: (key, value) => { options = { ...options, [key]: value }; return { success: true, options } },
        fullclone_owner_status: () => ({ success: true, message: '玩家 1（界面演示）：原生队伍 1', owner: 1 }),
        fullclone_quest_status: () => ({ success: true, status: 'idle', started: false, rows: [] }),
      }
      window.pywebview.api = new Proxy(extra, { get: (target, key) => target[key] || original[key] })
    })
    await page.locator('[data-testid="chapter-elephant"]').click()
    await page.locator('[data-testid="page-elephant"]').click()
    const input = page.getByLabel('替换单位ID', { exact: true })
    await input.fill('hfoo')
    const monitor = page.getByLabel('每秒监视玩家名字和队伍', { exact: true })
    await page.getByText('每秒监视玩家名字和队伍', { exact: true }).click()
    await page.evaluate(() => { window.__interfaceSentinel = document.querySelector('input[aria-label="替换单位ID"]') })
    await page.screenshot({ path: resolve(out, 'modern-elephant.png') })
    await page.locator('[data-testid="interface-switch"]').click()
    await page.waitForFunction(() => document.documentElement.dataset.interface === 'classic')
    await page.locator('[data-testid="classic-tabs"]').waitFor()
    assert.equal(await page.evaluate(() => window.__interfaceSentinel === document.querySelector('input[aria-label="替换单位ID"]')), true)
    assert.equal(await input.inputValue(), 'hfoo'); assert.equal(await monitor.isChecked(), true)
    assert.equal(await page.locator('[data-classic-page]').count(), 18)
    await page.screenshot({ path: resolve(out, 'classic-elephant.png') })
    const ids = await page.locator('[data-classic-page]').evaluateAll(xs => xs.map(x => x.dataset.classicPage))
    for (const id of ids) {
      await page.locator(`[data-classic-page="${id}"]`).click()
      await page.locator(`[data-page-view="${id}"] button, [data-page-view="${id}"] input`).first().waitFor()
      assert.equal(await page.evaluate(() => document.body.scrollWidth <= innerWidth), true, id)
    }
    await page.locator('[data-classic-page="elephant"]').click()
    // Page navigation follows the existing lifecycle; layout switching itself
    // must preserve the active monitor in that mounted page.
    await page.getByText('每秒监视玩家名字和队伍', { exact: true }).click()
    await page.locator('[data-testid="interface-legacy19"]').click()
    await page.locator('[data-testid="legacy19-groups"]').waitFor()
    assert.equal(await monitor.isChecked(), true)
    assert.equal(await input.inputValue(), 'hfoo')
    const groups = page.locator('[data-testid="legacy19-groups"]')
    assert.equal(await groups.locator(':scope > section').count(), 6)
    const groupGeometry = await groups.locator(':scope > section').evaluateAll(xs => xs.map(el => ({ x: el.offsetLeft, y: el.offsetTop, width: el.clientWidth })))
    assert.equal(new Set(groupGeometry.slice(0, 3).map(g => g.x)).size, 3)
    assert.equal(new Set(groupGeometry.slice(0, 3).map(g => g.y)).size, 1)
    await page.screenshot({ path: resolve(out, 'legacy19-elephant.png') })
    await page.getByRole('button', { name: '复制选中单位（Ctrl+B）', exact: true }).click()
    await page.getByRole('button', { name: '无敌', exact: true }).click()
    const dispatch = await page.evaluate(() => window.__legacyCalls)
    assert.ok(dispatch.some(c => c.extension === 'clone'))
    assert.ok(dispatch.some(c => c.native === 'invulnerable'))
    const legacyIds = await page.locator('[data-legacy19-page]').evaluateAll(xs => xs.map(el => ({ id: el.dataset.legacy19Page, kind: el.dataset.catalogKind })))
    for (const entry of legacyIds) {
      const tab = page.locator(`[data-legacy19-page="${entry.id}"]${entry.kind ? `[data-catalog-kind="${entry.kind}"]` : ''}`)
      await tab.click()
      await page.locator(`[data-page-view="${entry.id}"] button, [data-page-view="${entry.id}"] input`).first().waitFor()
      assert.equal(await page.evaluate(() => document.body.scrollWidth <= innerWidth), true, `legacy19:${entry.id}`)
      if (entry.kind) assert.equal(await page.evaluate(() => localStorage.getItem('war3-catalog-kind')), entry.kind)
    }
    await page.locator('[data-legacy19-page="elephant"]').click()
    await page.getByRole('button', { name: '快捷键功能', exact: true }).click()
    await page.locator('[data-page-view="hotkeys"]').waitFor()
    await page.getByRole('button', { name: '功能面板', exact: true }).click()
    for (const width of [800, 1024, 1280, 1920]) {
      await page.setViewportSize({ width, height: 900 })
      assert.equal(await page.evaluate(() => document.body.scrollWidth <= innerWidth), true, `legacy19:${width}`)
      assert.equal(await groups.evaluate(el => el.scrollWidth <= el.clientWidth + 1), true, `legacy19 groups:${width}`)
    }
    await page.setViewportSize({ width: 1280, height: 900 })
    await page.locator('[data-testid="interface-legacy19"]').click() // back to the existing white tabs
    // Long map-like results: exercise real wheel input over both columns.
    await page.evaluate(() => {
      const old = window.pywebview.api
      const rows = Array.from({ length: 22 }, (_, i) => ({
        key: `quest-${i}`, title: `滚轮测试任务 ${i + 1}`, kind: i < 12 ? '主线任务' : '支线任务',
        description: '滚轮验证数据', text: Array.from({ length: 140 }, (_, n) => `条件 ${n + 1}：任务说明与完成要求。`).join('\n') + '\n滚轮正文末尾',
        entries: [], conditions: [], state: '进行中', stateReason: '仅界面测试',
      }))
      window.pywebview.api = new Proxy({}, { get: (_, key) => key === 'fullclone_quest_status' ? () => ({ success: true, status: 'ready', started: true, rows, notice: 'Lua 静态解析：实时状态尚未绑定；文字可能为基础字符串表候选。', source: '界面滚轮验证数据' }) : old[key] })
    })
    await page.locator('[data-classic-page="quests"]').click()
    await page.getByText('主线任务 · 滚轮测试任务 1', { exact: true }).waitFor()
    assert.ok((await page.getByRole('note').textContent()).includes('基础字符串表候选'))
    const scrollResults = []
    for (const mode of ['classic', 'legacy19', 'modern']) {
      if (mode === 'legacy19') {
        await page.locator('[data-testid="interface-legacy19"]').click()
        await page.waitForFunction(() => document.documentElement.dataset.interface === 'legacy19')
      }
      if (mode === 'modern') {
        await page.locator('[data-testid="interface-switch"]').click()
        await page.waitForFunction(() => document.documentElement.dataset.interface === 'modern')
      }
      const region = page.locator('[data-page-view="quests"] > div').first()
      const before = await region.evaluate(el => ({ height: el.clientHeight, content: el.scrollHeight, overflow: getComputedStyle(el).overflowY }))
      assert.ok(before.content > before.height, `${mode}: long task results need a scroll container`)
      for (const column of ['article', 'nav']) {
        await region.evaluate(el => { el.scrollTop = 0 })
        const box = await region.locator(column).boundingBox()
        const frame = await region.boundingBox()
        await page.mouse.move(box.x + box.width / 2, Math.min(frame.y + frame.height / 2, box.y + 60))
        await page.mouse.wheel(0, 800)
        await page.waitForFunction(() => document.querySelector('[data-page-view="quests"] > div').scrollTop > 0)
      }
      await page.mouse.wheel(0, 100000)
      await page.waitForFunction(() => { const el = document.querySelector('[data-page-view="quests"] > div'); return el.scrollTop + el.clientHeight >= el.scrollHeight - 2 })
      assert.equal(await region.getByText('滚轮正文末尾', { exact: false }).isVisible(), true)
      const top = await region.evaluate(el => el.scrollTop)
      await page.waitForTimeout(1100) // Polling a task state must not reset the reading position.
      assert.equal(await region.evaluate(el => el.scrollTop), top)
      scrollResults.push({ mode, left_wheel: true, right_wheel: true, reached_bottom: true, poll_preserved_position: true })
    }
    await page.locator('[data-testid="interface-switch"]').click()
    await page.locator('[data-testid="classic-tabs"]').waitFor()
    await page.locator('[data-classic-page="unit"]').click()
    await page.screenshot({ path: resolve(out, 'classic-unit.png') })
    await page.reload()
    await page.locator('[data-testid="classic-header"]').waitFor()
    assert.equal(await page.evaluate(() => localStorage.getItem('war3-interface-mode')), 'classic')
    await page.locator('[data-testid="interface-switch"]').click()
    await page.locator('[data-testid="chapter-battle"]').waitFor()
    assert.equal(await page.locator('[data-testid="stage"]').getAttribute('data-page'), 'unit')
    await page.locator('[data-testid="interface-legacy19"]').click()
    await page.reload()
    await page.locator('[data-testid="legacy19-tabs"]').waitFor()
    assert.equal(await page.evaluate(() => document.documentElement.dataset.interface), 'legacy19')
    await page.locator('[data-testid="interface-switch"]').click()
    await page.locator('[data-testid="chapter-battle"]').waitFor()
    assert.deepEqual(errors, [])
    const result = { ok: true, demo_only: true, classic_pages: ids, legacy19_tabs: legacyIds, legacy19_six_groups: groupGeometry, shared_dispatch_checked: true, quest_scroll: scrollResults, settings_preserved: true, page_not_remounted: true, preference_survived_reload: true, returned_to_modern: true }
    await fs.writeFile(resolve(out, 'interface-check.json'), JSON.stringify(result, null, 2))
    console.log(JSON.stringify(result))
  } finally { await browser.close(); server.close() }
})().catch(e => { console.error(e); server.close(); process.exitCode = 1 })
