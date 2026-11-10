// Three-layout neutral drag UI regression. RPC fixtures only, no game access.
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
    const page=await browser.newPage({viewport:{width:1450,height:1200}}),errors=[]
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
          if(![24,27].includes(player)||![0,12,13].includes(target)||context!==window.__directory.context)throw new Error('Wrong neutral drag identity')
          const data=structuredClone(window.__directory)
          for(const group of data.diplomacy_groups)group.members=group.members.filter(p=>p!==player)
          data.diplomacy_groups.find(g=>g.template===target).members.push(player)
          const row=data.rows.find(p=>p.id===player);row.diplomacy=target
          row.diplomacy_label=target===0?'森林巡逻队（队伍 1）':target===12?'中立敌对':'中立被动'
          window.__directory=data;window.__neutralMoves.push([player,target])
          return{success:true,message:'外交模板已修改'}
        },
      },{get:(target,key)=>target[key]||original[key]})
    },fixtures)
    await page.getByTestId('chapter-battle').click();await page.getByTestId('page-players').click()
    await page.getByRole('button',{name:'读取／刷新玩家信息',exact:true}).click()
    await page.getByLabel('分组方式',{exact:true}).selectOption('diplomacy')
    for(const mode of ['modern','classic','legacy19']){
      if(mode==='classic')await page.getByTestId('interface-switch').click()
      if(mode==='legacy19')await page.getByTestId('interface-legacy19').click()
      for(const [player,neutral] of [[24,12],[27,13]]){
        const chip=page.locator(`nav [data-player="${player}"]`)
        await chip.dragTo(page.locator('nav details[data-team="0"] summary'))
        await page.locator(`nav details[data-team="0"] [data-player="${player}"]`).waitFor()
        await chip.dragTo(page.locator(`nav details[data-team="${neutral}"] summary`))
        await page.locator(`nav details[data-team="${neutral}"] [data-player="${player}"]`).waitFor()
      }
      await page.screenshot({path:resolve(out,`${mode}-neutral.png`)})
    }
    const moves=await page.evaluate(()=>window.__neutralMoves)
    assert.equal(moves.length,12);assert.equal(errors.length,0,errors.join('\n'))
    const report={ok:true,modes:['modern','classic','legacy19'],neutral_slots:[24,27],round_trips:6,moves,backend:'mock RPC only',gameplay_mutations:false}
    await fs.writeFile(resolve(out,'neutral-drag-check.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report))
  }finally{await browser.close();await new Promise(r=>server.close(r))}
})().catch(e=>{console.error(e);process.exitCode=1;server.close()})
