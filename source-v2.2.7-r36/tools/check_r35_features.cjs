// Presentation and cancellation checks only: real Edge, mock RPC, no game.
const { createRequire } = require('node:module'), { resolve, extname, sep } = require('node:path')
const fs = require('node:fs/promises'), http = require('node:http'), assert = require('node:assert/strict')
const { chromium } = createRequire(resolve('frontend/package.json'))('playwright-core')
const root = resolve('frontend/dist'), out = resolve(process.argv[2] || '../r35-feature-ui')
const server = http.createServer(async (req,res) => {
  try {
    const path=resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname).replace(/\/$/,'/index.html'))
    if(!path.startsWith(root+sep)){res.writeHead(403);return res.end()}
    res.setHeader('Content-Type',{'.html':'text/html','.js':'application/javascript','.css':'text/css','.woff2':'font/woff2'}[extname(path)]||'application/octet-stream')
    res.end(await fs.readFile(path))
  }catch{res.writeHead(404);res.end()}
})
;(async()=>{
  await fs.mkdir(out,{recursive:true});await new Promise(r=>server.listen(0,'127.0.0.1',r))
  const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true}),results=[]
  try {
    for(const mode of ['modern','classic','legacy19']){
      const page=await browser.newPage({viewport:{width:1450,height:1000}}),errors=[]
      page.on('pageerror',e=>errors.push(e.message))
      await page.addInitScript(mode=>{localStorage.setItem('war3-interface-mode',mode);localStorage.setItem('war3-page','unit')},mode)
      await page.goto(`http://127.0.0.1:${server.address().port}/?mock=connected`);await page.getByTestId('interface-switch').waitFor()
      await page.evaluate(()=>{
        const original=window.pywebview.api
        window.__r35calls=[];window.__r35options={formation:'original',formation_gap:'128',freeze_scope:'all',freeze_buildings:false,supply_slot:'1',supply_target:'hero',supply_name_1:'恢复用品',supply_name_2:'回城用品',supply_name_3:'测试装备',supply_text_1:'',supply_text_2:'',supply_text_3:'',point_spell:'AUin'}
        const push=action=>{window.__r35calls.push({action,...window.__r35options});return {success:true,message:'界面验证'}}
        window.pywebview.api=new Proxy({
          fullclone_settings:()=>({success:true,options:window.__r35options}),
          fullclone_set_option:(key,value)=>{window.__r35options={...window.__r35options,[key]:value};return {success:true,options:window.__r35options}},
          fullclone_action:push,fullclone_save_supplies:()=>push('supply_save'),
          get_system_status:async()=>({...await original.get_system_status(),...(window.__disconnect?{connected:false}:{} )}),
        },{get:(t,k)=>t[k]||original[k]})
      })
      async function nav(id){
        if(mode==='modern'){await page.getByTestId(`chapter-${id==='elephant'?'elephant':'battle'}`).click();await page.getByTestId(`page-${id}`).click()}
        else await page.locator(`[data-${mode==='classic'?'classic':'legacy19'}-page="${id}"]`).first().click()
        await page.locator(`[data-page-view="${id}"]:not([hidden])`).waitFor()
      }
      await nav('elephant')
      const formation=page.getByLabel('大量复制阵型',{exact:true}),gap=page.getByLabel('复制阵型间距',{exact:true})
      assert(await gap.isDisabled());await formation.selectOption('ring');await gap.fill('64')
      await page.getByRole('button',{name:'大量复制（Ctrl+N）',exact:true}).click()
      await page.getByLabel('冻结部队范围',{exact:true}).selectOption('heroes')
      await page.getByText('冻结包含建筑',{exact:true}).click()
      await page.getByRole('button',{name:'冻结／恢复选中玩家部队',exact:true}).click()
      await page.getByRole('button',{name:'恢复本次冻结的所有部队',exact:true}).click()
      await page.getByLabel('补给包方案',{exact:true}).selectOption('3')
      await page.getByLabel('补给包名称',{exact:true}).fill('第三组测试')
      await page.getByLabel('补给包物品清单',{exact:true}).fill('phea 2 1\npman 1')
      await page.getByRole('button',{name:'保存三组补给包',exact:true}).click()
      await nav('unit');await nav('elephant')
      assert.equal(await gap.inputValue(),'64');assert.equal(await page.getByLabel('补给包物品清单',{exact:true}).inputValue(),'phea 2 1\npman 1')
      await page.getByRole('button',{name:'投放补给包',exact:true}).click()
      await page.getByLabel('补给投放方式',{exact:true}).selectOption('ground')
      await page.getByRole('button',{name:'投放补给包',exact:true}).click()
      await page.getByRole('button',{name:'取消本次放置',exact:true}).waitFor()
      await page.getByRole('button',{name:'取消本次放置',exact:true}).click();await page.waitForTimeout(3200)
      let calls=await page.evaluate(()=>window.__r35calls)
      assert.equal(calls.filter(c=>c.action==='supply_deliver').length,1)
      await page.getByLabel('鼠标位置技能',{exact:true}).selectOption('AHfs')
      await page.getByRole('button',{name:'释放到鼠标位置',exact:true}).click();await nav('unit');await page.waitForTimeout(3200)
      assert.equal(await page.evaluate(()=>window.__r35calls.filter(c=>c.action==='point_spell').length),0)
      await nav('elephant');await page.getByRole('button',{name:'释放到鼠标位置',exact:true}).click()
      await page.waitForFunction(()=>window.__r35calls.some(c=>c.action==='point_spell'))
      calls=await page.evaluate(()=>window.__r35calls)
      assert.equal(calls.find(c=>c.action==='mass_clone').formation,'ring')
      assert.equal(calls.find(c=>c.action==='freeze_owner').freeze_buildings,true)
      assert.equal(calls.find(c=>c.action==='supply_deliver').supply_slot,'3')
      assert.equal(calls.find(c=>c.action==='point_spell').point_spell,'AHfs')
      await page.getByRole('button',{name:'释放到鼠标位置',exact:true}).click()
      await page.evaluate(()=>{window.__disconnect=true})
      await page.waitForTimeout(3500)
      assert.equal(await page.evaluate(()=>window.__r35calls.filter(c=>c.action==='point_spell').length),1)
      await page.getByLabel('补给包物品清单',{exact:true}).scrollIntoViewIfNeeded()
      await page.screenshot({path:resolve(out,`${mode}-r35.png`)})
      for(const width of [800,1024,1450]){await page.setViewportSize({width,height:1000});assert(await page.evaluate(()=>document.body.scrollWidth<=innerWidth),`${mode}:${width}`)}
      assert.deepEqual(errors,[]);results.push({mode,calls,page_cancel:true,explicit_cancel:true,disconnect_cancel:true,settings_retained:true,errors});await page.close()
    }
    await fs.writeFile(resolve(out,'results.json'),JSON.stringify({ok:true,game_access:false,results},null,2));console.log(JSON.stringify({ok:true,layouts:3,game_access:false}))
  }finally{await browser.close();server.close()}
})().catch(e=>{console.error(e);process.exitCode=1;server.close()})
