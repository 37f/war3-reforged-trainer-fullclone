// Author 2.2.5 display memory survives both page unmount and browser reload.
const { createRequire }=require('node:module'),{resolve,extname,sep}=require('node:path')
const fs=require('node:fs/promises'),http=require('node:http'),assert=require('node:assert/strict')
const {chromium}=createRequire(resolve('frontend/package.json'))('playwright-core')
const root=resolve('frontend/dist'),out=resolve(process.argv[2]||'../r33-author-memory-ui')
const server=http.createServer(async(req,res)=>{
  try{
    const path=resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname).replace(/\/$/,'/index.html'))
    if(!path.startsWith(root+sep)){res.writeHead(403);return res.end()}
    res.setHeader('Content-Type',{'.html':'text/html','.js':'application/javascript','.css':'text/css','.woff2':'font/woff2'}[extname(path)]||'application/octet-stream')
    res.end(await fs.readFile(path))
  }catch{res.writeHead(404);res.end()}
})
;(async()=>{
  await fs.mkdir(out,{recursive:true});await new Promise(r=>server.listen(0,'127.0.0.1',r))
  const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true})
  try{
    const page=await browser.newPage({viewport:{width:1450,height:1000}}),errors=[]
    page.on('pageerror',e=>errors.push(e.message))
    await page.goto(`http://127.0.0.1:${server.address().port}/?mock=connected`)
    await page.getByTestId('interface-switch').waitFor()
    const order=()=>page.locator('[data-testid^="chapter-"]').evaluateAll(xs=>xs.map(x=>x.dataset.testid))
    const initial=await order()
    await page.getByTestId('chapter-battle').press('Alt+Shift+ArrowRight')
    const reordered=await order();assert.notDeepEqual(reordered,initial)
    await page.getByTestId('chapter-codex').click();await page.getByTestId('page-catalogs').click()
    const view=page.locator('[data-page-view="catalogs"]')
    await view.getByRole('radio',{name:'单位',exact:true}).click()
    await view.getByLabel('搜索目录',{exact:true}).fill('hfoo')
    await page.getByTestId('chapter-battle').click();await page.getByTestId('page-resources').click()
    await page.getByTestId('chapter-codex').click();await page.getByTestId('page-catalogs').click()
    assert.equal(await view.getByLabel('搜索目录',{exact:true}).inputValue(),'hfoo')
    await page.reload();await page.getByTestId('interface-switch').waitFor()
    assert.deepEqual(await order(),reordered)
    assert.equal(await view.getByLabel('搜索目录',{exact:true}).inputValue(),'hfoo')
    assert.equal(await view.getByRole('radio',{name:'单位',exact:true}).getAttribute('aria-checked'),'true')
    await page.getByTestId('chapter-battle').dragTo(page.getByTestId('chapter-fields'),{targetPosition:{x:2,y:10}})
    assert.deepEqual(await order(),initial)
    await page.reload();await page.getByTestId('interface-switch').waitFor();assert.deepEqual(await order(),initial)
    assert.deepEqual(errors,[])
    await page.screenshot({path:resolve(out,'author-memory.png')})
    const report={ok:true,mock_only:true,query_survived_unmount:true,query_and_kind_survived_reload:true,
      keyboard_order_survived_reload:true,drag_order_survived_reload:true,errors}
    await fs.writeFile(resolve(out,'results.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report))
  }finally{await browser.close();server.close()}
})().catch(e=>{console.error(e);server.close();process.exitCode=1})
