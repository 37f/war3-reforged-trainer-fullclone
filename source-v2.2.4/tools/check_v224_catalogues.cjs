// R32: exercise the author's new catalogue actions in Edge with mock RPC only.
const { createRequire } = require('node:module')
const { resolve, extname, sep } = require('node:path')
const fs = require('node:fs/promises'), http = require('node:http'), assert = require('node:assert/strict')
const { chromium } = createRequire(resolve('frontend/package.json'))('playwright-core')
const root = resolve('frontend/dist'), out = resolve(process.argv[2] || '../r32-catalogue-ui')
const server = http.createServer(async (req,res) => {
  try {
    const path = resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname).replace(/\/$/,'/index.html'))
    if (!path.startsWith(root+sep)) { res.writeHead(403); return res.end() }
    res.setHeader('Content-Type',{'.html':'text/html','.js':'application/javascript','.css':'text/css','.woff2':'font/woff2'}[extname(path)] || 'application/octet-stream')
    res.end(await fs.readFile(path))
  } catch { res.writeHead(404); res.end() }
})
;(async()=>{
  await fs.mkdir(out,{recursive:true}); await new Promise(r=>server.listen(0,'127.0.0.1',r))
  const browser = await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true})
  const results=[]
  try {
    for (const mode of ['modern','classic','legacy19']) {
      const page=await browser.newPage({viewport:{width:1450,height:1000}}),errors=[]
      page.on('pageerror',e=>errors.push(e.message))
      await page.addInitScript(mode=>{
        localStorage.setItem('war3-interface-mode',mode)
        localStorage.setItem('war3-page','resources')
        localStorage.setItem('war3-catalog-kind','item')
      },mode)
      await page.goto(`http://127.0.0.1:${server.address().port}/?mock=connected`)
      await page.getByTestId('interface-switch').waitFor()
      await page.evaluate(()=>{
        const original=window.pywebview.api
        const codes={item:'ratf',ability:'AHbz',unit:'hfoo',upgrade:'Rhme'}
        const row=kind=>({id:kind,kind,rawcode:codes[kind],base:codes[kind],name:`测试${kind}`,name_zh:`测试${kind}`,name_en:kind,category:'测试',description:'目录操作回归',scope:'测试章节',changeType:'added',changeCount:0,files:[],changes:[],maxLevel:kind==='upgrade'?3:undefined})
        window.__catalogueCalls=[];window.__catalogueConnected=true
        window.pywebview.api=new Proxy({
          search_id_catalog:kind=>({success:true,rows:[row(kind)],matchCount:1,totalCount:1}),
          fullclone_current_catalog:()=>({success:true,jobId:'catalogue'}),
          get_map_catalog_progress:id=>id?{jobId:'catalogue',status:'succeeded',elapsed:0.1,source:'测试章节',rowCount:4,counts:{item:1,ability:1,unit:1,upgrade:1},scopes:['测试章节']}:{jobId:'',status:'idle',elapsed:0},
          search_map_catalog:(_id,kind)=>({success:true,rows:[row(kind)],matchCount:1,totalCount:4}),
          get_map_catalog_entry:(_id,id)=>row(id),
          execute_elephant_action:(action,params)=>{window.__catalogueCalls.push({action,params});return{success:true,parameters:{}}},
          get_system_status:async()=>({...await original.get_system_status(),connected:window.__catalogueConnected}),
        },{get:(target,key)=>target[key]||original[key]})
      })
      const nav=async id=>{
        if(mode==='modern') {await page.getByTestId('chapter-codex').click();await page.getByTestId(`page-${id}`).click()}
        else await page.locator(`[data-${mode==='classic'?'classic':'legacy19'}-page="${id}"]`).first().click()
        await page.locator(`[data-page-view="${id}"]:not([hidden])`).waitFor()
      }
      const calls=()=>page.evaluate(()=>window.__catalogueCalls)
      const count=async n=>{await page.waitForFunction(n=>window.__catalogueCalls.length===n,n)}
      for (const custom of [false,true]) {
        const id=custom?'map_catalog':'catalogs';await nav(id)
        const view=page.locator(`[data-page-view="${id}"]:not([hidden])`)
        if(custom)await view.getByRole('button',{name:'读取当前地图',exact:true}).click()
        const group=view.getByRole('radiogroup',{name:custom?'对象类型':'目录',exact:true})
        for(const [kind,label,code,action] of [['item','物品','ratf','add_item'],['ability','技能','AHbz','add_ability'],['upgrade','科技','Rhme','set_tech'],['unit','单位','hfoo','create_unit']]) {
          await group.getByRole('radio',{name:custom?new RegExp(label):label,exact:!custom}).click()
          await view.getByRole('row').filter({hasText:code}).click()
          const sheet=view.locator('aside');await sheet.getByRole('heading',{name:`测试${kind}`,exact:true}).waitFor()
          const before=(await calls()).length
          if(kind==='unit') {
            await sheet.getByText('归属开关关闭时给自己，开启时按大象面板选择。',{exact:true}).waitFor()
            const spawn=sheet.getByRole('button',{name:'生成到鼠标处',exact:true})
            await spawn.click();await sheet.getByRole('button',{name:/秒后生成 · 取消/}).click()
            await page.waitForTimeout(3200);assert.equal((await calls()).length,before)
            await spawn.click();await count(before+1)
            assert.deepEqual((await calls()).at(-1),{action,params:{rawcode:code,to_self:false}})
            // Leaving the entry cancels the author's pending countdown.
            await spawn.click();await sheet.getByRole('button',{name:'关闭',exact:true}).click()
            await page.waitForTimeout(3200);assert.equal((await calls()).length,before+1)
            if(mode==='modern'&&!custom) {
              await view.getByRole('row').filter({hasText:code}).click()
              await spawn.click();await nav('map_catalog')
              await page.waitForTimeout(3200);assert.equal((await calls()).length,before+1)
              await nav(id);await group.getByRole('radio',{name:label,exact:true}).click()
              await view.getByRole('row').filter({hasText:code}).click();await spawn.click()
              await page.evaluate(()=>{window.__catalogueConnected=false})
              await page.waitForTimeout(3500);assert.equal((await calls()).length,before+1)
              await page.evaluate(()=>{window.__catalogueConnected=true})
              await spawn.waitFor({state:'visible'})
            }
          } else {
            if(kind==='upgrade') {
              assert.equal(await sheet.getByLabel('科技等级',{exact:true}).inputValue(),'3')
              await sheet.getByLabel('科技等级',{exact:true}).fill('5')
              await sheet.getByRole('button',{name:'添加科技',exact:true}).click()
            } else await sheet.getByRole('button',{name:'给选中单位',exact:true}).click()
            await count(before+1)
            assert.deepEqual((await calls()).at(-1),{action,params:{rawcode:code,...(kind==='ability'?{level:'1'}:kind==='upgrade'?{level:'5'}:{})}})
          }
        }
        await page.screenshot({path:resolve(out,`${mode}-${id}.png`)})
      }
      assert.deepEqual(errors,[])
      results.push({mode,actions:await calls(),errors});await page.close()
    }
    await fs.writeFile(resolve(out,'results.json'),JSON.stringify({ok:true,results},null,2))
    console.log(JSON.stringify({ok:true,layouts:results.length,actions:results.reduce((n,r)=>n+r.actions.length,0),out}))
  } finally {await browser.close();server.close()}
})().catch(e=>{console.error(e);server.close();process.exitCode=1})
