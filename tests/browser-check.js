/* eslint-disable @typescript-eslint/no-unused-expressions */
async (page) => {
  // Synthetic fixtures for UI validation only; every API request is intercepted.
  const now = Date.now()/1000;
  let submitted = null;
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.unroute('**/api/**');
  await page.route('**/api/**', async route => {
    const path = '/api/' + route.request().url().split('/api/')[1].split('?')[0];
    let body;
    if (path === '/api/status') body = {actor:'Fixture de teste',csrf:'fixture-token',demo:false,name:'project-infinity',ready:true,running:true,players:2,max_players:20,version:'1.20.1',ram_bytes:6.3*1024**3,cpu_percent:83.2,uptime_seconds:15610,sampled_at:now,error:null,manager:{restarts:3},job:{state:'idle',message:''}};
    else if(path === '/api/backups') body = [{name:'backup-mundo-teste.zip',size:201234567,modified:now,complete:true,metrics:{cpu_percent:150.5,ram_bytes:6*1024**3,host_cpu_percent:18.8,host_ram_bytes:9*1024**3,observed_at:now}}];
    else if(path.endsWith('/content')) body = {files:2,uncompressed:203456789,truncated:false,entries:['world/level.dat','world/region/r.0.0.mca']};
    else if(path === '/api/logs') body = {text:'[INFO] Backup de teste iniciado\n[WARN] Mensagem de teste\n[ERROR] Falha simulada',sampled_at:now};
    else if(path === '/api/audit') body = [];
    else if(path === '/api/spark') body = [{name:'fixture.sparkprofile',size:4000,modified:now}];
    else if(path === '/api/spark/fixture.sparkprofile') body = {name:'fixture.sparkprofile',start:now-60,end:now,sampled_ms:1000,threads:['Server thread'],mapped:true,rows:[{id:'examplemod',name:'Mod de exemplo',version:'1.0',direct_ms:600,direct_percent:60,inclusive_ms:800,inclusive_percent:80,methods:[{name:'example.Tick.run()V',direct_ms:600,percent:60}]},{id:'minecraft',name:'Minecraft (base)',version:'',direct_ms:400,direct_percent:40,inclusive_ms:1000,inclusive_percent:100,methods:[]}]};
    else if(path === '/api/actions') { submitted=route.request().postDataJSON(); body={state:'running',message:'Operação simulada'}; }
    else body={};
    await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
  });
  await page.reload();
  await page.getByText('Online e respondendo',{exact:true}).waitFor();
  const widths = [];
  for(const width of [390,1440]) {
    await page.setViewportSize({width,height:900});
    for(const colorScheme of ['light','dark']) {
      await page.emulateMedia({colorScheme});
      await page.getByRole('button',{name:'Visão geral',exact:true}).click();
      if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)) throw new Error('Overflow overview');
      await page.screenshot({path:`qa-${width}-${colorScheme}.png`,fullPage:true});
      await page.getByRole('button',{name:'Backups do mundo',exact:true}).click();
      await page.getByRole('heading',{name:'backup-mundo-teste.zip',exact:true}).waitFor();
      if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)) throw new Error('Overflow backups');
      await page.getByRole('button',{name:'Desempenho · spark',exact:true}).click();
      await page.getByText('Mod de exemplo',{exact:true}).waitFor();
      await page.getByText('Mod de exemplo',{exact:true}).click();
      await page.getByText('example.Tick.run()V',{exact:true}).waitFor();
      if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)) throw new Error('Overflow spark');
      await page.screenshot({path:`qa-spark-${width}-${colorScheme}.png`,fullPage:true});
      await page.getByLabel('Buscar mod ou componente').fill('inexistente');
      await page.getByText('Nenhum componente corresponde à busca.').waitFor();
      await page.getByLabel('Buscar mod ou componente').fill('');
      await page.getByLabel('Ordenar por').selectOption('inclusive');
      if(!(await page.locator('#spark-ranking details').first().innerText()).includes('Minecraft (base)')) throw new Error('Spark ordering failed');
      await page.getByLabel('Ordenar por').selectOption('direct');
      widths.push({width,colorScheme,overflow:false});
    }
  }
  await page.getByRole('button',{name:'Backups do mundo',exact:true}).click();
  await page.getByRole('button',{name:'Conteúdo',exact:true}).click();
  await page.getByText('world/level.dat\nworld/region/r.0.0.mca',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Fechar',exact:true}).click();
  await page.getByRole('button',{name:'Restaurar',exact:true}).click();
  await page.locator('#restore-confirm').fill('RESTAURAR');
  await page.getByRole('button',{name:'Confirmar',exact:true}).click();
  if(submitted?.action!=='restore' || submitted.confirm!=='backup-mundo-teste.zip') throw new Error('Invalid restore confirmation');
  await page.getByRole('button',{name:'Logs ao vivo',exact:true}).click();
  await page.getByLabel('Buscar mensagem').fill('Falha simulada');
  await page.locator('#full-log').filter({hasText:'Falha simulada'}).waitFor();
  if(errors.length) throw new Error(errors.join('\n'));
  await page.unroute('**/api/**');
  return {widths,restoreConfirmation:'passed (mock only)',logFilter:'passed',pageErrors:errors};
}
