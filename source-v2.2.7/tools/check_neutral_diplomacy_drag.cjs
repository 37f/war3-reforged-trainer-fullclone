// Three-layout neutral and inactive slot drag UI regression. RPC fixtures only, no game access.
const { createRequire } = require('node:module')
const { resolve, extname, sep } = require('node:path')
const fs = require('node:fs/promises'), http = require('node:http'), assert = require('node:assert/strict')
const { chromium } = createRequire(resolve('frontend/package.json'))('playwright-core')
const root = resolve('frontend/dist'), out = resolve(process.argv[2]), input = resolve(process.argv[3])
const server = http.createServer(async (req,res) => {
  try {
    const path=resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname).replace(/\/$/,'/index.html'))
    if(!path.startsWith(root+sep)){res.writeHead(403);return res.end()}
    res.setHeader('Content-Type',{'.html':'text/html','.js':'application/javascript','.css':'text/css','.woff2':'font/woff2'}[extname(path)]||'application/octet-stream')
    res.end(await fs.readFile(path))
  }catch{res.writeHead(404);res.end()}
})
;(async()=>{
  const fixtures=JSON.parse(await fs.readFile(input,'utf8'))
  await fs.mkdir(out,{recursive:true});await new Promise(r=>server.listen(0,'127.0.0.1',r))
  const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true})
  try{
    const page=await browser.newPage({viewport:{width:1450,height:900}}),errors=[]
    page.on('pageerror',e=>errors.push(e.message))
    await page.goto(`http://127.0.0.1:${server.address().port}/?mock=connected`)
    await page.getByTestId('interface-switch').waitFor()
    await page.evaluate(fixtures=>{
      const original=window.pywebview.api
      window.__directory=structuredClone(fixtures.initial);window.__neutralMoves=[]
      window.pywebview.api=new Proxy({
        fullclone_player_directory:()=>window.__directory,
        fullclone_page_context:()=>({success:true,context:window.__directory.context}),
        fullclone_move_player_team:(player,target,context)=>{
          if(![4,5,6,7,24,27].includes(player)||![0,1,12,13].includes(target)||context!==window.__directory.context)throw new Error('Unexpected move '+JSON.stringify([player,target,context,window.__directory.context]))
          if(player===7)return{success:true,applied:false,player,target,context,message:'无法确认玩家 8 的槽位，未修改外交模板。请重新读取玩家信息'}
          const data=structuredClone(window.__directory)
          for(const group of data.diplomacy_groups)group.members=group.members.filter(p=>p!==player)
          data.diplomacy_groups.find(g=>g.template===target).members.push(player)
          const row=data.rows.find(p=>p.id===player);row.diplomacy=target
          row.diplomacy_label=target===0?'森林巡逻队（队伍 1）':target===12?'中立敌对':'中立被动'
          window.__directory=data;window.__neutralMoves.push([player,target])
          return{success:true,player,target,context,message:'外交模板已修改'}
        },
      },{get:(target,key)=>target[key]||original[key]})
    },fixtures)
    await page.getByTestId('chapter-battle').click();await page.getByTestId('page-players').click()
    await page.getByRole('button',{name:'读取／刷新玩家信息',exact:true}).click()
    await page.getByLabel('分组方式',{exact:true}).selectOption('diplomacy')
    const panel=page.getByTestId('player-directory')
    const preview=page.getByTestId('player-drag-preview')
    async function beginCard(source){
      await source.scrollIntoViewIfNeeded()
      const chip=await source.boundingBox()
      assert(chip)
      const x=chip.x+chip.width/2,y=chip.y+chip.height/2
      await page.mouse.move(x,y)
      await page.mouse.down()
      await page.mouse.move(x+12,y,{steps:3})
      await preview.waitFor()
    }
    async function wheelWhileHeld(delta){
      const before=await panel.evaluate(el=>el.scrollTop)
      await page.mouse.wheel(0,delta)
      await page.waitForFunction(({before,delta})=>{
        const el=document.querySelector('[data-testid="player-directory"]')
        return Math.sign(delta)*(el.scrollTop-before)>0
      },{before,delta},{timeout:4000})
      assert(await preview.isVisible())
    }
    async function dragAcrossList(source,target){
      await beginCard(source)
      try{
        const rail=await panel.boundingBox()
        assert(rail)
        let box=await target.boundingBox()
        assert(box)
        let center=box.y+box.height/2
        if(center<=rail.y || center>=rail.y+rail.height){
          await wheelWhileHeld(Math.round(center-rail.y-rail.height/2))
          box=await target.boundingBox()
          center=box.y+box.height/2
        }
        assert(center>rail.y && center<rail.y+rail.height,'wheel brought team into the page viewport')
        await page.mouse.move(box.x+Math.min(100,box.width/2),center)
      }finally{
        await page.mouse.up()
      }
      await preview.waitFor({state:'hidden'})
    }
    for(const [step,mode] of ['modern','classic','legacy19'].entries()){
      if(mode==='classic')await page.getByTestId('interface-switch').click()
      if(mode==='legacy19')await page.getByTestId('interface-legacy19').click()
      assert(await panel.evaluate(el=>el.scrollHeight>el.clientHeight &&
        getComputedStyle(el.querySelector('nav')).overflowY==='visible'))
      // A stationary held card must survive wheel input in both directions.
      await panel.evaluate(el=>el.scrollTop=0)
      const previousMoves=await page.evaluate(()=>window.__neutralMoves.length)
      const first=page.locator('nav [data-player="0"]')
      await first.click()
      assert.equal(await first.getAttribute('aria-current'),'true')
      await beginCard(first)
      await wheelWhileHeld(340)
      await wheelWhileHeld(-340)
      await page.keyboard.press('Escape')
      await page.mouse.up()
      await preview.waitFor({state:'hidden'})
      assert.equal(await page.evaluate(()=>window.__neutralMoves.length),previousMoves)
      for(const [player,neutral] of [[24,12],[27,13]]){
        const chip=page.locator(`nav [data-player="${player}"]`)
        await dragAcrossList(chip,page.locator('nav details[data-team="0"] summary'))
        await page.locator(`nav details[data-team="0"] [data-player="${player}"]`).waitFor()
        await dragAcrossList(chip,page.locator(`nav details[data-team="${neutral}"] summary`))
        await page.locator(`nav details[data-team="${neutral}"] [data-player="${player}"]`).waitFor()
      }
      const target=step%2
      for(const player of [4,5,6]){
        const chip=page.locator(`nav [data-player="${player}"]`)
        await dragAcrossList(chip,page.locator(`nav details[data-team="${target}"] summary`))
        await page.locator(`nav details[data-team="${target}"] [data-player="${player}"]`).waitFor({timeout:2000}).catch(async e=>{
          console.error(await page.evaluate(()=>({moves:window.__neutralMoves,status:document.querySelector('[data-testid="player-directory"] [role=status]').textContent})))
          throw e
        })
      }
      await dragAcrossList(page.locator('nav [data-player="7"]'),page.locator('nav details[data-team="0"] summary'))
      await page.getByText('无法确认玩家 8 的槽位，未修改外交模板。请重新读取玩家信息',{exact:true}).waitFor()
      assert.equal(await page.locator('nav details[data-team="0"] [data-player="7"]').count(),0)
      await page.screenshot({path:resolve(out,`${mode}-neutral.png`)})
    }
    const moves=await page.evaluate(()=>window.__neutralMoves)
    assert.equal(moves.length,21);assert.equal(errors.length,0,errors.join('\n'))
    const report={ok:true,wheel_while_held_both_directions:true,whole_page_scroll:true,modes:['modern','classic','legacy19'],neutral_slots:[24,27],round_trips:6,inactive_moves:9,unavailable_inline:true,moves,backend:'mock RPC only',gameplay_mutations:false}
    await fs.writeFile(resolve(out,'neutral-drag-check.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report))
  }finally{await browser.close();await new Promise(r=>server.close(r))}
})().catch(e=>{console.error(e);process.exitCode=1;server.close()})
