// Presentation verification against a captured read-only reply, never the game.
const { createRequire } = require('node:module')
const { resolve, extname, sep } = require('node:path')
const fs = require('node:fs/promises')
const http = require('node:http')
const assert = require('node:assert/strict')
const { chromium } = createRequire(resolve('frontend/package.json'))('playwright-core')
const root = resolve('frontend/dist'), out = resolve(process.argv[2]), sample = resolve(process.argv[3])
const server = http.createServer(async (req, res) => {
  try {
    const path = resolve(root, '.' + decodeURIComponent(new URL(req.url, 'http://localhost').pathname).replace(/\/$/, '/index.html'))
    if (!path.startsWith(root + sep)) { res.writeHead(403); return res.end() }
    res.setHeader('Content-Type', { '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.svg': 'image/svg+xml', '.png': 'image/png' }[extname(path)] || 'application/octet-stream')
    res.end(await fs.readFile(path))
  } catch { res.writeHead(404); res.end() }
})
;(async () => {
  const data = JSON.parse(await fs.readFile(sample, 'utf8'))
  await fs.mkdir(out, { recursive: true }); await new Promise(r => server.listen(0, '127.0.0.1', r))
  const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1400, height: 1000 }, deviceScaleFactor: 1 })
    const errors = []; page.on('pageerror', e => errors.push(e.message))
    await page.goto(`http://127.0.0.1:${server.address().port}/?mock=connected`)
    await page.locator('[data-testid="interface-switch"]').waitFor()
    await page.evaluate(data => {
      const original = window.pywebview.api; window.__playerCalls = []
      window.pywebview.api = new Proxy({
        fullclone_player_directory: refresh => { window.__playerCalls.push(refresh); if (window.__failPlayers) throw new Error('模拟换图：本次没有可确认的玩家数据'); return data },
        fullclone_settings: () => ({ success: true, options: {} }),
      }, { get: (target, key) => target[key] || original[key] })
    }, data)
    await page.locator('[data-testid="chapter-elephant"]').click()
    await page.locator('[data-testid="page-elephant"]').click()
    await page.getByRole('button', { name: '查看队伍与全部玩家', exact: true }).click()
    const rootPage = page.getByTestId('player-directory')
    const read = page.getByRole('button', { name: '读取／刷新玩家信息', exact: true })
    await read.click()
    const table = page.getByRole('table')
    await table.locator('tbody tr').last().waitFor()
    assert.equal(await table.locator('tbody tr').count(), data.rows.length)
    const first = data.rows.find(p => p.config)
    await table.getByRole('button', { name: first.name, exact: true }).click()
    await page.getByRole('heading', { name: `玩家 ${first.slot} · ${first.name}`, exact: true }).waitFor()
    const group = data.initial_groups.find(g => g.members.length && g.key.startsWith('force:'))
    await page.getByRole('button', { name: `${group.name}（${group.members.length} 个玩家）`, exact: true }).click()
    assert.equal(await table.locator('tbody tr').count(), group.members.length)
    await page.getByRole('button', { name: '查看全部玩家', exact: true }).click()
    const search = page.getByLabel('搜索玩家信息', { exact: true })
    await search.fill(first.name)
    assert.equal(await table.locator('tbody tr').count(), 1)
    await search.fill('')
    const grouping = page.getByLabel('分组方式', { exact: true })
    await grouping.selectOption('current')
    const team = data.current_groups.find(g => g.key.startsWith('team:'))
    if (team) {
      await page.getByRole('button', { name: `${team.name}（${team.members.length} 个玩家）`, exact: true }).click()
      assert.equal(await table.locator('tbody tr').count(), team.members.length)
      assert(team.members.every(id => id < 24))
    }
    await page.getByRole('button', { name: '查看全部玩家', exact: true }).click()
    const modeLabels = await grouping.locator('option').allTextContents()
    assert.ok(modeLabels.includes('查看或修改外交模板'))
    await grouping.selectOption('diplomacy')
    const applied = (data.diplomacy_groups || []).find(g => g.key && String(g.key).startsWith('diplomacy:') && g.members && g.members.length)
    if (applied) {
      await page.getByRole('button', { name: `${applied.name}（${applied.members.length} 个玩家）`, exact: true }).click()
      assert.equal(await table.locator('tbody tr').count(), applied.members.length)
      await page.getByRole('button', { name: '查看全部玩家', exact: true }).click()
    }
    await grouping.selectOption('initial')
    const geometry = []
    for (const mode of ['modern', 'classic', 'legacy19']) {
      if (mode === 'classic') await page.getByTestId('interface-switch').click()
      if (mode === 'legacy19') await page.getByTestId('interface-legacy19').click()
      await page.waitForFunction(mode => document.documentElement.dataset.interface === mode, mode)
      assert.equal(await page.getByRole('heading', { name: `玩家 ${first.slot} · ${first.name}`, exact: true }).count(), 1)
      const scroller = page.getByLabel('玩家信息表', { exact: true })
      await scroller.evaluate(el => el.scrollTop = 0)
      await scroller.hover(); await page.mouse.wheel(0, 500); await page.waitForTimeout(180)
      assert(await scroller.evaluate(el => el.scrollTop > 0), `${mode} table wheel`)
      await rootPage.evaluate(el => el.scrollTop = 0)
      await scroller.evaluate(el => el.scrollTop = 0)
      await page.screenshot({ path: resolve(out, `${mode}-players.png`) })
      await page.getByRole('note').count() // ensure rendering has settled without app actions
      const dims = await page.evaluate(() => ({ width: innerWidth, body: document.body.scrollWidth }))
      assert(dims.body <= dims.width, `${mode} overflow`); geometry.push({ mode, ...dims })
    }
    await page.setViewportSize({ width: 800, height: 800 })
    assert(await page.evaluate(() => document.body.scrollWidth <= innerWidth))
    await rootPage.evaluate(el => el.scrollTop = 0)
    await page.getByRole('button', { name: '重新读取地图配置', exact: true }).click()
    assert.deepEqual(await page.evaluate(() => window.__playerCalls), [false, true])
    await page.evaluate(() => window.__failPlayers = true)
    await read.click()
    await page.waitForFunction(() => !document.querySelector('[aria-label="玩家信息表"]'))
    assert.equal(errors.length, 0, errors.join('\n'))
    const result = { ok: true, captured_readonly_reply: true, rows: data.rows.length, initial_group_filter: true, current_group_filter: true, diplomacy_group_option: true, diplomacy_group_filter: Boolean(applied), search: true, details: true, all_three_layouts: geometry, wheel_scroll: true, failure_clears_old_rows: true, manual_reads_only: true, gameplay_mutations: false }
    await fs.writeFile(resolve(out, 'player-directory-check.json'), JSON.stringify(result, null, 2))
    console.log(JSON.stringify(result))
  } finally { await browser.close(); await new Promise(r => server.close(r)) }
})().catch(e => { console.error(e); process.exitCode = 1; server.close() })
