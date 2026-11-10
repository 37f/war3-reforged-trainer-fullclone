// Real Edge, deterministic RPC only. Never attaches to a game process.
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
  const results = []
  try {
    for (const mode of ['modern', 'classic', 'legacy19']) {
      const page = await browser.newPage({ viewport: { width: 1450, height: 1000 } }), errors = []
      page.on('pageerror', e => errors.push(e.message))
      await page.addInitScript(mode => { localStorage.setItem('war3-interface-mode', mode); localStorage.setItem('war3-page', 'unit') }, mode)
      await page.goto(`http://127.0.0.1:${server.address().port}/?mock=connected`)
      await page.getByTestId('interface-switch').waitFor()
      await page.evaluate(fixtures => {
        const original = window.pywebview.api
        window.__calls = { directory: 0, context: 0, scan: 0, quests: 0, unit: 0, owner: 0, actions: [] }
        window.__context = fixtures.initial.context; window.__directory = fixtures.initial
        window.__quest = { success: true, status: 'ready', started: true, chapters: [], source: '测试地图', rows: [0,1,2,3].map(i => ({
          key: `q${i}`, title: `任务${i}`, kind: i % 2 ? '支线任务' : '主线任务', text: ('原有任务说明\n').repeat(40), state: '进行中', stateReason: '',
          entries: [{ index: i, label: '脚本初始位置，非实时', enabled: true }], conditions: [],
        })) }
        window.pywebview.api = new Proxy({
          fullclone_player_directory: () => { window.__calls.directory++; return window.__directory },
          fullclone_page_context: () => { window.__calls.context++; return { success: true, context: window.__context } },
          fullclone_quest_status: () => { window.__calls.quests++; return window.__quest },
          fullclone_quest_scan: () => { window.__calls.scan++; return { success: true } },
          fullclone_settings: () => ({ success: true, options: {} }),
          fullclone_owner_status: () => { window.__calls.owner++; return { success: true, message: '玩家1：队伍1' } },
          fullclone_action: name => { window.__calls.actions.push(name); return { success: true, message: '恢复完成' } },
          read_all_selected_units: async () => {
            window.__calls.unit++
            if (window.__slowUnit) await new Promise(r => window.__finishRead = r)
            if (window.__failUnit) return { success: false, error: '模拟读取失败' }
            if (window.__noSelection) return { unit: null, candidates: [] }
            const result = await original.get_selected_unit_snapshot()
            result.hp.current = String(100 + window.__calls.unit); result.identity = '监视中的选中单位'
            return { unit: result, candidates: [] }
          },
        }, { get: (target, key) => target[key] || original[key] })
      }, fixtures)
      async function nav(id) {
        if (mode !== 'modern') await page.locator(`[data-${mode === 'classic' ? 'classic' : 'legacy19'}-page="${id}"]`).first().click()
        else {
          const chapter = ['players','unit','resources'].includes(id) ? 'battle' : id === 'quests' ? 'codex' : 'elephant'
          await page.getByTestId(`chapter-${chapter}`).click()
          await page.getByTestId(`page-${id}`).click()
        }
        await page.locator(`[data-page-view="${id}"]:not([hidden])`).waitFor()
      }
      const players = page.getByTestId('player-directory'), quest = page.getByTestId('quest-page')
      await nav('players')
      assert(await players.getByLabel('记忆模式', { exact: true }).isChecked())
      await players.getByRole('button', { name: '读取／刷新玩家信息', exact: true }).click()
      await players.getByLabel('分组方式', { exact: true }).selectOption('diplomacy')
      await players.locator('nav [data-player="1"]').click()
      await players.getByLabel('搜索玩家信息').fill('玩家')
      await players.getByText('隐藏空槽和已离开玩家', { exact: true }).click()
      await players.getByText('每5秒监视', { exact: true }).click()
      await page.evaluate(() => { window.__playersNode = document.querySelector('[data-testid="player-directory"]') })
      await nav('quests')
      const before = await page.evaluate(() => window.__calls.directory)
      await quest.getByRole('button', { name: /支线任务 · 任务1/ }).click()
      await quest.getByText('触发位置', { exact: true }).click()
      await quest.locator('details > summary').first().click()
      await quest.getByLabel('战役或地图路径').fill('E:\\测试地图.w3x')
      await quest.evaluate(el => { el.scrollTop = 275; window.__questNode = el })
      await page.screenshot({ path: resolve(out, `${mode}-quest-memory.png`) })
      await nav('resources'); await nav('quests')
      assert(await quest.getByLabel('触发位置', { exact: true }).isChecked())
      assert.equal(await quest.locator('article h2').innerText(), '任务1')
      assert.equal(await quest.getByLabel('战役或地图路径').inputValue(), 'E:\\测试地图.w3x')
      assert(await quest.evaluate(el => el === window.__questNode && el.scrollTop > 0))
      assert.equal(await page.evaluate(() => window.__calls.scan), 0)
      if (mode === 'modern') {
        await nav('resources')
        const hidden = await page.evaluate(() => ({ ...window.__calls }))
        await page.waitForTimeout(5200)
        const after = await page.evaluate(() => window.__calls)
        assert.equal(after.quests, hidden.quests); assert.equal(after.directory, hidden.directory)
      }
      await nav('players')
      await page.waitForFunction(() => window.__calls.context > 0)
      assert.equal(await page.evaluate(() => window.__calls.directory), before)
      assert(await players.evaluate(el => el === window.__playersNode))
      assert.equal(await players.getByLabel('分组方式').inputValue(), 'diplomacy')
      assert.equal(await players.getByLabel('搜索玩家信息').inputValue(), '玩家')
      assert(await players.getByLabel('每5秒监视', { exact: true }).isChecked())
      await players.getByText('每5秒监视', { exact: true }).click()
      await players.getByRole('button', { name: '恢复所有玩家真正原队伍', exact: true }).click()
      await nav('elephant')
      await page.getByRole('button', { name: '恢复所有玩家真正原队伍', exact: true }).click()
      await page.getByText('每秒监视玩家名字和队伍', { exact: true }).click()
      await nav('unit')
      const unitMonitor = page.getByLabel('每5秒监视单位状态', { exact: true })
      assert.equal(await unitMonitor.isChecked(), false)
      await page.getByText('每5秒监视单位状态', { exact: true }).click()
      if (mode === 'modern') {
        await page.waitForFunction(() => window.__calls.unit === 1, { timeout: 8000 })
        assert((await page.getByTestId('unit-page').innerText()).includes('101'))
        await page.screenshot({ path: resolve(out, 'modern-unit-monitor.png') })
        await page.getByLabel('搜索字段', { exact: true }).fill('正在编辑')
        await page.waitForTimeout(5200)
        assert.equal(await page.evaluate(() => window.__calls.unit), 1)
        await page.getByLabel('搜索字段', { exact: true }).fill('')
        await nav('resources'); const count = await page.evaluate(() => window.__calls.unit)
        await page.waitForTimeout(5200); assert.equal(await page.evaluate(() => window.__calls.unit), count)
        await nav('unit'); assert(await unitMonitor.isChecked())
        await page.evaluate(() => window.__slowUnit = true)
        await page.waitForFunction(count => window.__calls.unit > count, count)
        const slow = await page.evaluate(() => window.__calls.unit)
        await page.waitForTimeout(5200); assert.equal(await page.evaluate(() => window.__calls.unit), slow)
        await page.evaluate(() => { window.__slowUnit = false; window.__noSelection = true; window.__finishRead() })
        await page.getByRole('heading', { name: '未读取单位', exact: true }).waitFor()
        await page.evaluate(() => window.__failUnit = true)
        await page.waitForFunction(() => !document.querySelector('[data-testid="unit-page"] input[type=checkbox]').checked)
        const failed = await page.evaluate(() => window.__calls.unit)
        if (await page.getByTestId('notice-ok').isVisible()) await page.getByTestId('notice-ok').click()
        await page.waitForTimeout(5200); assert.equal(await page.evaluate(() => window.__calls.unit), failed)
      }
      await nav('elephant')
      assert(await page.getByLabel('每秒监视玩家名字和队伍', { exact: true }).isChecked())
      await page.getByText('每秒监视玩家名字和队伍', { exact: true }).click()
      await nav('resources'); await page.evaluate(() => window.__context = 'different-map')
      await nav('players'); await players.getByText('地图已变化，请重新读取玩家信息', { exact: false }).waitFor()
      assert.equal(await players.locator('nav [data-player]').count(), 0)
      await players.getByRole('button', { name: '读取／刷新玩家信息', exact: true }).click()
      await players.getByText('记忆模式', { exact: true }).click()
      await nav('resources'); await nav('players')
      assert.equal(await players.getByLabel('记忆模式', { exact: true }).isChecked(), false)
      assert.equal(await players.locator('nav [data-player]').count(), 0)
      assert.equal(await page.evaluate(() => window.__calls.actions.join(',')), 'restore_all_teams,restore_all_teams')
      await nav('quests')
      await page.evaluate(() => window.__quest = { status: 'stale', started: true, rows: [], chapters: [], error: '地图已变化，请重新检测' })
      await nav('resources'); await nav('quests')
      await quest.getByText('地图已变化，请重新检测', { exact: true }).waitFor()
      assert.equal(await quest.locator('nav button').count(), 0)
      assert.equal(await page.evaluate(() => window.__calls.scan), 0)
      await quest.getByText('记忆模式', { exact: true }).click()
      await nav('resources'); await nav('quests')
      assert.equal(await quest.getByLabel('触发位置', { exact: true }).isChecked(), false)
      assert.equal(await quest.getByLabel('记忆模式', { exact: true }).isChecked(), false)
      await nav('players')
      assert.equal(errors.length, 0, errors.join('\n'))
      await page.screenshot({ path: resolve(out, `${mode}-players.png`) })
      results.push({ mode, memory_preserved: true, stale_map_cleared: true, bulk_buttons_shared: true, calls: await page.evaluate(() => window.__calls) })
      await page.close()
    }
    const report = { ok: true, gameplay_mutations: false, backend: 'mock RPC only', modes: results, unit_timer_overlap_error_and_hidden_tested: true }
    await fs.writeFile(resolve(out, 'restore-memory-monitor-check.json'), JSON.stringify(report, null, 2)); console.log(JSON.stringify(report))
  } finally { await browser.close(); await new Promise(r => server.close(r)) }
})().catch(e => { console.error(e); process.exitCode = 1; server.close() })
