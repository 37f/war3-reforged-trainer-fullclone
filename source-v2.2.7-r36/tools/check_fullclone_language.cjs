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
  const { initial } = JSON.parse(await fs.readFile(input, 'utf8'))
  const local = initial.rows.find(p => p.id === 1)
  local.name = 'MyNickname#1001'
  local.name_source = '游戏读取值'
  local.config.name = '地图守卫'
  await fs.mkdir(out, { recursive: true })
  await new Promise(r => server.listen(0, '127.0.0.1', r))
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  const modes = []
  try {
    for (const mode of ['modern', 'classic', 'legacy19']) {
      const page = await browser.newPage({ viewport: { width: 1500, height: 950 } })
      const errors = []
      page.on('pageerror', error => errors.push(error.message))
      await page.goto('http://127.0.0.1:' + server.address().port + '/?mock=connected')
      await page.getByTestId('interface-switch').waitFor()
      await page.evaluate(fixture => {
        const original = window.pywebview.api
        window.directoryReads = 0
        window.questScans = 0
        window.pywebview.api = new Proxy({
          fullclone_player_directory: () => { window.directoryReads++; return fixture },
          fullclone_settings: () => ({ success: true, options: { point_spell: 'AUin' } }),
          fullclone_quest_scan: () => { window.questScans++; return { success: true } },
          fullclone_quest_status: () => ({
            success: true, status: 'ready', started: true, canLocate: true, chapters: [], issues: [],
            rows: [{ key: 'main', kind: '主线任务', title: '守卫古城', description: '任务原文',
              text: '完成条件\n任务原文', textEn: 'Completion conditions\n任务原文',
              state: '进行中', stateReason: '当前地图唯一任务变量的原生状态',
              entries: [{ index: 1, label: '东门区域', labelEn: 'East Gate region', enabled: true }], conditions: [] }]
          }),
          get_all_hotkeys: async () => [...await original.get_all_hotkeys(),
            { name: 'fill_owner_life_mana', label: '选中玩家全军生命魔法全满', key: 'Ctrl+空格', category: 'combat', enabled: true }]
        }, { get: (target, key) => target[key] ?? original[key] })
      }, initial)
      if (mode === 'classic') await page.getByTestId('interface-switch').click()
      if (mode === 'legacy19') await page.getByTestId('interface-legacy19').click()
      await page.waitForFunction(expected => document.documentElement.dataset.interface === expected, mode)
      async function nav(id, chapter) {
        if (mode === 'modern') {
          await page.getByTestId('chapter-' + chapter).click()
          await page.getByTestId('page-' + id).click()
        } else if (mode === 'legacy19' && id === 'hotkeys') {
          await page.getByTestId('legacy19-subtabs').getByRole('button', { name: 'Hotkeys' }).click()
        } else {
          const attribute = mode === 'classic' ? 'data-classic-page' : 'data-legacy19-page'
          await page.locator('[' + attribute + '="' + id + '"]').first().click()
        }
        await page.locator('[data-page-view="' + id + '"]:not([hidden])').waitFor()
      }
      async function language(name, code) {
        await page.getByTestId('system-menu').click()
        await page.getByRole('radio', { name, exact: true }).click()
        await page.waitForFunction(expected => document.documentElement.lang === expected, code)
        await page.keyboard.press('Escape')
      }

      await nav('players', 'battle')
      const players = page.getByTestId('player-directory')
      assert.equal(await players.getByLabel('记忆模式', { exact: true }).count(), 0)
      await players.getByRole('button', { name: '读取／刷新玩家信息', exact: true }).click()
      const card = players.locator('nav [data-player="1"]')
      await card.click()
      assert((await card.innerText()).includes('MyNickname#1001'))
      const nameMode = players.getByLabel('玩家名显示', { exact: true })
      await nameMode.selectOption('map')
      assert((await card.innerText()).includes('地图守卫'))
      assert((await players.locator('article h2').innerText()).includes('地图守卫'))
      await players.getByRole('button', { name: '地图守卫', exact: true }).waitFor()
      assert.equal(await page.evaluate(() => window.directoryReads), 1)

      await language('English', 'en')
      const enSwitcher = players.getByLabel('Player name display', { exact: true })
      assert.equal(await enSwitcher.inputValue(), 'map')
      await players.getByRole('columnheader', { name: 'Player name', exact: true }).waitFor()
      await enSwitcher.selectOption('game')
      await players.getByRole('button', { name: 'MyNickname#1001', exact: true }).waitFor()
      assert((await players.locator('article h2').innerText()).includes('MyNickname#1001'))

      await nav('quests', 'codex')
      const quest = page.getByTestId('quest-page')
      await quest.getByText('守卫古城', { exact: true }).waitFor()
      await quest.getByText('Completion conditions', { exact: false }).waitFor()
      await quest.getByText('Trigger locations', { exact: true }).click()
      await quest.getByRole('button', { name: 'East Gate region', exact: true }).waitFor()
      assert.equal(await page.evaluate(() => window.questScans), 0)

      await nav('players', 'battle')
      assert.equal(await players.locator('nav [data-player]').count(), 0)
      assert.equal(await enSwitcher.inputValue(), 'game')
      assert.equal(await page.evaluate(() => window.directoryReads), 1)

      await nav('elephant', 'elephant')
      await page.getByRole('button', { name: 'Cast at cursor (Ctrl+F2)', exact: true }).waitFor()
      await page.getByRole('button', { name: 'Refill selected player\'s army (Ctrl+Space)', exact: true }).waitFor()
      await page.getByLabel('Cursor-targeted spells', { exact: true }).waitFor()
      if (mode === 'modern') {
        await nav('hotkeys', 'elephant')
        await page.getByText("Refill selected player's army", { exact: true }).waitFor()
        await page.getByLabel('Ctrl+Space', { exact: true }).waitFor()
        await nav('elephant', 'elephant')
      }
      await language('中文', 'zh-CN')
      await page.getByRole('button', { name: '释放到鼠标位置（Ctrl+F2）', exact: true }).waitFor()
      assert.deepEqual(errors, [])
      modes.push(mode)
      await page.close()
    }
    const report = { ok: true, modes, nicknameAndMapNames: true, sameReadForBothNames: true, playersResetOnReturn: true, languageSwitchBothDirections: true, originalQuestTextPreserved: true, noGameAccess: true }
    await fs.writeFile(resolve(out, 'fullclone-language-check.json'), JSON.stringify(report, null, 2))
    console.log(JSON.stringify(report))
  } finally {
    await browser.close()
    await new Promise(r => server.close(r))
  }
})().catch(e => { console.error(e); process.exitCode = 1; server.close() })
