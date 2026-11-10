// Real browser drag/drop against deterministic RPC fixtures; never the game.
const { createRequire } = require('node:module')
const { resolve, extname, sep } = require('node:path')
const fs = require('node:fs/promises'), http = require('node:http'), assert = require('node:assert/strict')
const { chromium } = createRequire(resolve('frontend/package.json'))('playwright-core')
const root = resolve('frontend/dist'), out = resolve(process.argv[2]), input = resolve(process.argv[3])
const server = http.createServer(async (req, res) => {
  try {
    const path = resolve(root, '.' + decodeURIComponent(new URL(req.url, 'http://localhost').pathname).replace(/\/$/, '/index.html'))
    if (!path.startsWith(root + sep)) { res.writeHead(403); return res.end() }
    res.setHeader('Content-Type', { '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css', '.woff2': 'font/woff2' }[extname(path)] || 'application/octet-stream')
    res.end(await fs.readFile(path))
  } catch { res.writeHead(404); res.end() }
})
;(async () => {
  const fixtures = JSON.parse(await fs.readFile(input, 'utf8'))
  await fs.mkdir(out, { recursive: true }); await new Promise(r => server.listen(0, '127.0.0.1', r))
  const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1450, height: 1000 } }), errors = []
    page.on('pageerror', e => errors.push(e.message))
    await page.goto(`http://127.0.0.1:${server.address().port}/?mock=connected`)
    await page.getByTestId('interface-switch').waitFor()
    await page.evaluate(fixtures => {
      const original = window.pywebview.api
      window.__moves = []; window.__directory = fixtures.initial; window.__fixtures = fixtures
      window.pywebview.api = new Proxy({
        fullclone_player_directory: () => window.__directory,
        fullclone_settings: () => ({ success: true, options: {} }),
        fullclone_move_player_team: async (player, target, context) => {
          window.__moves.push([player, target, context])
          if (window.__failMove) throw new Error('模拟地图已经变化，请重新读取')
          if (player !== 1 || ![0, 1].includes(target) || context !== fixtures.initial.context) throw new Error('Wrong drag identity')
          await new Promise(r => setTimeout(r, 120))
          window.__directory = target === 1 ? fixtures.moved : fixtures.initial
          return { success: true, message: '外交模板已修改，控制权限保持不变' }
        },
      }, { get: (target, key) => target[key] || original[key] })
    }, fixtures)
    await page.getByTestId('chapter-elephant').click(); await page.getByTestId('page-elephant').click()
    await page.getByRole('button', { name: '查看队伍与全部玩家', exact: true }).click()
    await page.getByRole('button', { name: '读取／刷新玩家信息', exact: true }).click()
    const grouping = page.getByLabel('分组方式', { exact: true })
    await grouping.selectOption('diplomacy')
    assert((await grouping.locator('option').allTextContents()).includes('查看或修改外交模板'))
    const own = page.locator('nav [data-player="1"]')
    const destination = n => page.locator(`nav details[data-team="${n}"]`)
    assert((await own.innerText()).includes('自己'))
    assert((await destination(0).locator('summary').innerText()).includes('森林巡逻队（队伍 1）（4 个玩家）'))
    assert.equal(await page.getByText('未套用外交模板', { exact: true }).count(), 0)
    const modes = []
    for (const mode of ['modern', 'classic', 'legacy19']) {
      if (mode === 'classic') await page.getByTestId('interface-switch').click()
      if (mode === 'legacy19') await page.getByTestId('interface-legacy19').click()
      await page.waitForFunction(mode => document.documentElement.dataset.interface === mode, mode)
      await own.dragTo(destination(1).locator('summary'))
      await page.waitForFunction(() => window.__directory === window.__fixtures.moved)
      await destination(1).locator('[data-player="1"]').waitFor()
      assert((await destination(1).locator('summary').innerText()).includes('（5 个玩家）'))
      await page.screenshot({ path: resolve(out, `${mode}-diplomacy.png`) })
      await own.dragTo(destination(0).locator('summary'))
      await destination(0).locator('[data-player="1"]').waitFor()
      modes.push(mode)
    }
    assert.equal((await page.evaluate(() => window.__moves)).length, 6)
    await own.dragTo(destination(0).locator('summary')) // Same group is a no-op.
    assert.equal((await page.evaluate(() => window.__moves)).length, 6)
    await page.evaluate(() => window.__failMove = true)
    await own.dragTo(destination(1).locator('summary'))
    await page.waitForFunction(() => !document.querySelector('[aria-label="玩家信息表"]'))
    assert.equal(errors.length, 0, errors.join('\n'))
    const result = { ok: true, modes, real_browser_drag_drop: true, named_original_teams: true, local_player_included: true, counts_refreshed: true, same_group_noop: true, failure_clears_old_data: true, rpc_calls: await page.evaluate(() => window.__moves), gameplay_mutations: false, backend: 'mock RPC only' }
    await fs.writeFile(resolve(out, 'diplomacy-drag-check.json'), JSON.stringify(result, null, 2)); console.log(JSON.stringify(result))
  } finally { await browser.close(); await new Promise(r => server.close(r)) }
})().catch(e => { console.error(e); process.exitCode = 1; server.close() })
