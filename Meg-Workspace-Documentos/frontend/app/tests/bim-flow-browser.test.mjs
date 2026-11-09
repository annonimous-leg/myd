// Real browser/API/PostGIS/Redis/worker/filesystem flow. No intercepted routes.
import assert from 'node:assert/strict';
import { before, after, test } from 'node:test';
import { spawn, execFileSync } from 'node:child_process';
import { once } from 'node:events';
import { createWriteStream } from 'node:fs';
import { readFile, mkdir } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { chromium } from 'playwright';
import { licitacionFlow } from './helpers/licitacion-flow.mjs';

const frontend = resolve('.');
const backend = resolve('../../backend');
const evidence = resolve(process.env.BIM_EVIDENCE_DIR || 'bim-browser-evidence');
const origin = 'http://127.0.0.1:4173';
const apiOrigin = 'http://127.0.0.1:8000';
let browser, api, worker, dispatcher, preview, credentials;
const processes = [];
const env = { ...process.env, CORS_ALLOWED_ORIGINS: JSON.stringify([origin]),
  BIM_STORAGE_PROVIDER:'filesystem', BIM_LOCAL_STORAGE_PATH:join(evidence, 'files'),
  OTEL_EXPORTER_OTLP_ENDPOINT:'' };

function start(name, command, args, cwd) {
  const log = createWriteStream(join(evidence, `${name}.log`), { flags:'a' });
  const process = spawn(command, args, { cwd, env, stdio:['ignore','pipe','pipe'] });
  process.stdout.pipe(log, {end:false});
  process.stderr.pipe(log, {end:false});
  process.on('close',()=>log.end());
  process.on('error', e => log.write(String(e)));
  processes.push(process);
  return process;
}
function startApi() { return start('api', join(backend,'.venv/bin/python'),
  ['-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000','--no-access-log'], backend); }
function startWorker() { return start('worker', join(backend,'.venv/bin/python'),
  ['-m','celery','-A','app.workers.celery_app','worker','--pool=solo','--loglevel=INFO'], backend); }
async function stop(process) {
  if (!process || process.exitCode !== null) return;
  const finished = once(process, 'exit');
  process.kill('SIGTERM');
  const timeout = setTimeout(() => process.kill('SIGKILL'), 10000);
  await finished; clearTimeout(timeout);
}
async function ready(url, process) {
  for (let attempt=0;attempt<180;attempt++) {
    if (process.exitCode !== null) throw new Error(`Service stopped before readiness: ${url}`);
    try { if ((await fetch(url)).ok) return; } catch {}
    await new Promise(resolve => setTimeout(resolve,500));
  }
  throw new Error(`Service never became ready: ${url}`);
}
async function login(page, email) {
  await page.goto(origin);
  await page.getByPlaceholder('tu@correo.com').fill(email);
  await page.locator('input[type="password"]').fill(credentials.password);
  await page.getByRole('button',{name:'Entrar al Sistema'}).click();
  await page.getByRole('navigation').getByRole('button',{name:'Proyectos',exact:true}).waitFor({timeout:60000});
}

before(async () => {
  await mkdir(evidence,{recursive:true});
  credentials = JSON.parse(await readFile(process.env.BIM_ACCEPTANCE_CREDENTIALS,'utf8'));
  api=startApi(); await ready(apiOrigin+'/ready', api);
  dispatcher=start('dispatcher',join(backend,'.venv/bin/python'),['-m','app.workers.job_dispatcher'],backend);
  preview = process.env.MEG_WEB_IMAGE
    ? start('preview', 'docker', ['run', '--rm', '--network=host',
        '-e', 'PORT=4173', '-e', 'API_UPSTREAM=http://127.0.0.1:8000',
        process.env.MEG_WEB_IMAGE], frontend)
    : start('preview',process.execPath,['node_modules/vite/bin/vite.js','preview','--host','127.0.0.1','--port','4173','--strictPort'],frontend);
  await ready(origin,preview);
  browser=await chromium.launch({ executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined,
    args:['--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'] });
});

after(async () => {
  await browser?.close();
  for (const process of processes.reverse()) await stop(process);
});

test('user creates an obra, resumes an IFC job after restart, approves and exports, then opens 4D', {timeout:240000}, async () => {
  const context=await browser.newContext({viewport:{width:1440,height:1000},acceptDownloads:true});
  await context.tracing.start({screenshots:true,snapshots:true});
  const page=await context.newPage();
  const errors=[]; page.on('pageerror',e=>errors.push(e.message));
  try {
    await login(page,credentials.reviewer);
    await page.getByRole('navigation').getByRole('button',{name:'Proyectos',exact:true}).click();
    await page.getByRole('button',{name:'Nuevo',exact:true}).click();
    await page.getByLabel('Título del expediente').fill('Obra sintética de aceptación BIM');
    await page.getByLabel('Órgano', {exact:false}).fill('CI staging');
    await page.getByLabel('Unidad administrativa').fill('Pruebas');
    await page.getByLabel('Serie documental', {exact:false}).first().fill('02100');
    await page.getByLabel('Subserie documental', {exact:false}).fill('02100-01');
    const [created]=await Promise.all([
      page.waitForResponse(r=>r.request().method()==='POST' && new URL(r.url()).pathname==='/api/v1/expedientes'),
      page.getByRole('button',{name:'Crear expediente',exact:true}).click()]);
    assert.equal(created.status(),200);
    await page.getByRole('button',{name:'Calculadora BIM',exact:true}).click();
    const [uploadResponse]=await Promise.all([
      page.waitForResponse(r=>r.request().method()==='POST' && /\/bim\/[^/]+\/modelos$/.test(new URL(r.url()).pathname)),
      page.getByLabel('Subir archivo IFC').setInputFiles(join(backend,'tests/fixtures/ifc/wall_millimetres.ifc'))]);
    assert.equal(uploadResponse.status(),200);
    const model=await uploadResponse.json();
    assert.equal(model.estado_procesamiento,'PENDIENTE');
    // Worker was never started. Restarting both API and dispatcher must retain work.
    await stop(api); await stop(dispatcher);
    api=startApi(); await ready(apiOrigin+'/ready',api);
    dispatcher=start('dispatcher',join(backend,'.venv/bin/python'),['-m','app.workers.job_dispatcher'],backend);
    await page.reload();
    worker=startWorker();
    await page.getByRole('button',{name:'2. Preparar presupuesto'}).waitFor({timeout:60000});
    await page.waitForFunction(()=>[...document.querySelectorAll('button')].some(b=>b.textContent==='2. Preparar presupuesto'&&!b.disabled),{},{timeout:60000});
    await page.screenshot({path:join(evidence,'01-modelo-recuperado.png'),fullPage:true});
    const apiModel=await page.request.get(`${apiOrigin}/api/v1/bim/${model.expediente_id}/modelos/${model.id}/elementos?incluir_malla=true`);
    assert.equal(apiModel.status(),200);
    const elements=await apiModel.json(); assert.equal(elements.length,1);
    assert.equal(elements[0].volumen,2.4); assert.ok(elements[0].malla_vertices.length>0);
    await page.getByRole('button',{name:'2. Preparar presupuesto'}).click();
    await page.getByPlaceholder('Buscar en catálogo (ej. muro, concreto)...').fill('Muro de prueba');
    const [catalogResponse]=await Promise.all([
      page.waitForResponse(r=>r.url().includes('/api/v1/catalogo-apu?')&&r.request().method()==='GET'),
      page.getByRole('button',{name:'Buscar concepto para IfcWall'}).click(),
    ]);
    assert.equal(catalogResponse.status(),200);
    await page.getByRole('button',{name:/Muro de prueba sintética CI/}).click();
    await page.getByPlaceholder('Fuente: contrato, convocatoria o análisis').fill('Prueba sintética CI: factores cero explícitos');
    await page.getByRole('button',{name:'Generar presupuesto',exact:true}).click();
    await page.getByRole('button',{name:'Validar presupuesto'}).waitFor();
    await page.getByRole('button',{name:'Validar presupuesto'}).click();
    await page.getByRole('button',{name:'Aprobar presupuesto'}).click();
    await page.getByText('Estado: APROBADO',{exact:true}).waitFor();
    await page.getByRole('region',{name:'Revisión del presupuesto'}).getByText('$300.00',{exact:true}).first().waitFor();
    await page.screenshot({path:join(evidence,'02-presupuesto-aprobado.png'),fullPage:true});
    for (const format of ['Excel','PDF']) {
      const event=page.waitForEvent('download');
      await page.getByRole('button',{name:`Descargar ${format}`}).click();
      const download=await event;
      const destination=join(evidence,download.suggestedFilename());
      await download.saveAs(destination);
      const bytes=await readFile(destination);
      assert.ok(bytes.length>500);
      assert.equal(bytes.subarray(0,format==='PDF'?4:2).toString(),format==='PDF'?'%PDF':'PK');
    }
    // The target must still open correctly when it falls outside the first 20 programs.
    const fixtures=start('schedule-fixtures',join(backend,'.venv/bin/python'),
      ['-m','scripts.seed_bim_acceptance_ci','--programs-for',model.expediente_id],backend);
    const [fixtureExit]=await once(fixtures,'exit');
    assert.equal(fixtureExit,0);
    await page.getByRole('button',{name:'3. Crear cronograma'}).click();
    await page.locator('input[type="date"]').fill('2026-10-06');
    await page.getByRole('button',{name:'Generar cronograma 4D',exact:true}).click();
    // The program must survive a reload and open in the actual workspace editor.
    await page.getByRole('button',{name:'Editar cronograma en Workspace',exact:true}).waitFor({timeout:60000});
    await page.reload();
    await page.getByRole('button',{name:'3. Crear cronograma'}).click();
    await page.getByRole('button',{name:'Editar cronograma en Workspace',exact:true}).click();
    const scheduleUrl=new URL(page.url());
    assert.equal(scheduleUrl.searchParams.get('app'),'licitaciones-obra');
    assert.equal(scheduleUrl.searchParams.get('seccion'),'cronograma');
    const scheduleId=scheduleUrl.searchParams.get('programa');
    assert.ok(scheduleId,'The 4D generation must link a persisted program ID.');
    await page.getByRole('navigation',{name:'Secciones de Workspace'})
      .getByRole('button',{name:'Cronograma de obra',exact:true}).waitFor();
    await page.waitForFunction(id=>document.querySelector('select[aria-label="Cronograma de esta obra"]')?.value===id,scheduleId);
    await page.screenshot({path:join(evidence,'03-cronograma.png'),fullPage:true});
    await page.setViewportSize({width:390,height:844});
    await page.getByRole('button',{name:'Calculadora BIM',exact:true}).click();
    await page.getByRole('button',{name:'2. Preparar presupuesto'}).click();
    await page.getByText('Estado: APROBADO',{exact:true}).waitFor();
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
    await page.screenshot({path:join(evidence,'04-movil.png'),fullPage:true});
    assert.deepEqual(errors,[]);
    // A genuine IFC contains one measurable wall and another without QTO/shape.
    await page.setViewportSize({width:1440,height:1000});
    await page.getByLabel('Subir archivo IFC').setInputFiles(credentials.partial_ifc);
    await page.waitForFunction(()=>[...document.querySelectorAll('button')].some(b=>b.textContent==='2. Preparar presupuesto'&&!b.disabled),{},{timeout:60000});
    await page.getByRole('button',{name:'2. Preparar presupuesto'}).click();
    const missing=page.getByRole('region',{name:'Completar mediciones faltantes'});
    await missing.waitFor();
    // Select the m3 catalogue for this model too; captures must use its unit.
    if (await page.getByPlaceholder('Buscar en catálogo (ej. muro, concreto)...').count()) {
      await page.getByPlaceholder('Buscar en catálogo (ej. muro, concreto)...').fill('Muro de prueba');
      const [catalogResponse]=await Promise.all([
        page.waitForResponse(r=>r.url().includes('/api/v1/catalogo-apu?')&&r.request().method()==='GET'),
        page.getByRole('button',{name:'Buscar concepto para IfcWall'}).click(),
      ]);
      assert.equal(catalogResponse.status(),200);
      await page.getByRole('button',{name:/Muro de prueba sintética CI/}).click();
    }
    await page.getByPlaceholder('Fuente: contrato, convocatoria o análisis').fill('Prueba parcial: factores cero explícitos');
    await page.getByRole('button',{name:'Generar presupuesto',exact:true}).click();
    const budgetReview=page.getByRole('region',{name:'Revisión del presupuesto'});
    await budgetReview.getByText(/Presupuesto PARCIAL: 1 de 2 elementos medidos/).waitFor();
    await budgetReview.getByText('$300.00',{exact:true}).first().waitFor();
    assert.equal(await budgetReview.getByRole('button',{name:'Confirmar cálculo'}).isDisabled(),true);
    await page.screenshot({path:join(evidence,'06-presupuesto-parcial.png'),fullPage:true});
    await missing.getByLabel('Cantidad faltante (m3)',{exact:true}).fill('1.6');
    await missing.getByLabel('Referencia de la medición',{exact:true}).fill('Levantamiento de prueba revisado');
    await page.getByRole('button',{name:'Generar presupuesto',exact:true}).click();
    await budgetReview.getByText(/Mediciones completas: 2 de 2 elementos medidos/).waitFor();
    await budgetReview.getByText('$500.00',{exact:true}).first().waitFor();
    await page.screenshot({path:join(evidence,'07-mediciones-completadas.png'),fullPage:true});
    const readerContext=await browser.newContext({viewport:{width:1440,height:1000}});
    try {
      const readerPage=await readerContext.newPage();
      await login(readerPage,credentials.reader);
      await readerPage.getByRole('navigation').getByRole('button',{name:'Proyectos',exact:true}).click();
      await readerPage.getByRole('button',{name:/Obra sintética de aceptación BIM/}).click();
      await readerPage.getByRole('button',{name:'Calculadora BIM',exact:true}).click();
      await readerPage.getByLabel('Subir archivo IFC').waitFor({state:'attached'});
      assert.equal(await readerPage.getByLabel('Subir archivo IFC').isDisabled(),true);
      await readerPage.screenshot({path:join(evidence,'05-solo-lectura.png'),fullPage:true});
    } finally { await readerContext.close(); }
    await page.goto(origin+'/?app=topografia');
    await page.getByRole('button',{name:'Levantamiento',exact:true}).click();
    await page.getByPlaceholder('Nombre nuevo levantamiento').fill('Aceptación UTM en metros');
    await page.getByLabel('Sistema de coordenadas').selectOption('32614');
    const [surveyCreated]=await Promise.all([
      page.waitForResponse(r=>r.request().method()==='POST' && /\/topografia\/[^/]+\/levantamientos$/.test(new URL(r.url()).pathname)),
      page.getByRole('button',{name:'Crear levantamiento',exact:true}).click()]);
    assert.equal(surveyCreated.status(),200);
    const survey=await surveyCreated.json();
    assert.equal(survey.crs,'EPSG:32614');
    const [tinCreated]=await Promise.all([
      page.waitForResponse(r=>r.request().method()==='POST' && /\/triangular$/.test(new URL(r.url()).pathname)),
      page.getByLabel('Subir puntos CSV').setInputFiles({name:'terreno.csv',mimeType:'text/csv',
        buffer:Buffer.from('P1,500000,2200000,1\nP2,500001,2200000,-1\nP3,500000,2200001,-1\n')})]);
    assert.equal(tinCreated.status(),200);
    const tin=await tinCreated.json();
    await page.getByLabel('Superficie existente').selectOption(tin.id);
    await page.getByLabel('Elevación de referencia').fill('0');
    const [volumeCreated]=await Promise.all([
      page.waitForResponse(r=>r.request().method()==='POST' && new URL(r.url()).pathname==='/api/v1/topografia/volumenes'),
      page.getByRole('button',{name:'Calcular',exact:true}).click()]);
    assert.equal(volumeCreated.status(),200);
    const volume=await volumeCreated.json();
    assert.equal(volume.volumen_corte_m3,.042);
    assert.equal(volume.volumen_terraplen_m3,.208);
    assert.equal(volume.evidencia.cobertura.completa,true);
    await page.getByRole('button',{name:'Generar presupuesto de movimiento de tierras',exact:true}).waitFor();
    await page.getByLabel('Referencia de parámetros topográficos').fill('CI: revisión sintética del terreno');
    const [earthBudgetResponse] = await Promise.all([
      page.waitForResponse(r=>r.request().method()==='POST' && /\/topografia\/[^/]+\/volumenes\/[^/]+\/generar-presupuesto$/.test(new URL(r.url()).pathname)),
      page.getByRole('button',{name:'Generar presupuesto de movimiento de tierras',exact:true}).click()]);
    assert.equal(earthBudgetResponse.status(),200,await earthBudgetResponse.text());
    const earthBudget = await earthBudgetResponse.json();
    assert.equal(earthBudget.partidas.length,2);
    assert.ok(earthBudget.partidas.every(p=>p.metadatos.topografia.calculo_id===volume.id));
    const earthReview=page.getByRole('region',{name:'Revisión del presupuesto'});
    let pricedEarthBudget;
    for (const number of [1,2]) {
      await earthReview.getByLabel(`Buscar concepto para partida ${number}`).fill('CI-EARTHWORK');
      const select=earthReview.getByLabel(`Concepto para partida ${number}`,{exact:true});
      await select.locator('option').filter({hasText:'Movimiento de tierras sintético CI'}).waitFor({state:'attached'});
      const option=await select.locator('option').filter({hasText:'Movimiento de tierras sintético CI'}).getAttribute('value');
      await select.selectOption(option);
      const [priced] = await Promise.all([
        page.waitForResponse(r=>r.request().method()==='PUT' && /\/partidas\/[^/]+\/catalogo$/.test(new URL(r.url()).pathname)),
        earthReview.getByRole('button',{name:`Asignar concepto a partida ${number}`,exact:true}).click()]);
      assert.equal(priced.status(),200);
      const result=await priced.json();
      assert.ok(result.partidas.every(p=>p.metadatos.topografia.calculo_id===volume.id));
      pricedEarthBudget=result;
    }
    await earthReview.getByRole('status').filter({hasText:'Estado: CALCULADO'}).waitFor();
    await earthReview.getByRole('button',{name:'Validar presupuesto',exact:true}).click();
    await earthReview.getByRole('status').filter({hasText:'Estado: VALIDADO'}).waitFor();
    await earthReview.getByRole('button',{name:'Aprobar presupuesto',exact:true}).click();
    await earthReview.getByRole('status').filter({hasText:'Estado: APROBADO'}).waitFor();
    for (const format of ['Excel','PDF']) {
      const [download]=await Promise.all([page.waitForEvent('download'),
        earthReview.getByRole('button',{name:`Descargar ${format}`,exact:true}).click()]);
      await download.saveAs(join(evidence,format==='Excel'?'earthwork-budget.xlsx':'earthwork-budget.pdf'));
    }
    // Reopen the files actually downloaded through the UI and check their contents.
    const exported=execFileSync(join(backend,'.venv/bin/python'),['-c',`
import json, sys, zipfile
from openpyxl import load_workbook
from pypdf import PdfReader
expected=json.loads(sys.argv[3])
with zipfile.ZipFile(sys.argv[1]) as archive:
    assert archive.testzip() is None
workbook=load_workbook(sys.argv[1], data_only=True)
assert workbook['Topografía']['B2'].value == expected['calculo_id']
assert workbook['Topografía']['B3'].value == expected['sha256']
rows={row[0]:row for row in list(workbook['Presupuesto'].values)[1:] if isinstance(row[0],int)}
source_rows=list(workbook['Fuentes de precio'].values)[1:]
sources={row[0]:row for row in source_rows}
assert len(rows) == len(source_rows) == len(sources) == 2
assert set(rows) == set(sources) == {line['numero'] for line in expected['partidas']}
for line in expected['partidas']:
    row, source = rows[line['numero']], sources[line['numero']]
    assert row[0] == source[0] == line['numero']
    assert row[2] == 'm3' and row[3] == line['cantidad']
    assert row[4] == line['precio_unitario'] and row[5] == round(line['cantidad']*line['precio_unitario'],2)
    assert source[1] == line['catalogo_id'] and source[2] == 'CI-EARTHWORK'
    assert source[5] == 'CI_SYNTHETIC_NOT_MARKET_PRICE' and source[11] == line['sha256']
text=''.join(page.extract_text() for page in PdfReader(sys.argv[2]).pages)
assert 'CI-EARTHWORK' in text and 'CI_SYNTHETIC_NOT_MARKET_PRICE' in text
compact=''.join(text.split())
assert expected['calculo_id'] in compact
for line in expected['partidas']:
    visible=f"m3{line['cantidad']:,.4f}$"+f"{line['precio_unitario']:,.2f}$"+f"{line['cantidad']*line['precio_unitario']:,.2f}"
    assert visible in compact, (visible, text)
print(json.dumps({'xlsx':'verified','pdf':'verified','calculo_id':expected['calculo_id']}))
`,join(evidence,'earthwork-budget.xlsx'),join(evidence,'earthwork-budget.pdf'),JSON.stringify({
      calculo_id:volume.id,sha256:volume.evidencia.sha256,
      partidas:[...pricedEarthBudget.partidas].sort((a,b)=>a.numero-b.numero).map(p=>({
        numero:p.numero,cantidad:p.cantidad,precio_unitario:p.precio_unitario,
        catalogo_id:p.metadatos.catalogo_asignado.catalogo_id,sha256:p.metadatos.catalogo_asignado.sha256}))
    })],{cwd:backend,env,encoding:'utf8',timeout:20000});
    assert.equal(JSON.parse(exported).xlsx,'verified');
    await page.screenshot({path:join(evidence,'10-topografia-utm.png'),fullPage:true});
    await page.getByLabel('Elevación de referencia').fill('1');
    assert.equal(await page.getByRole('button',{name:'Generar presupuesto de movimiento de tierras',exact:true}).count(),0);
    await page.getByPlaceholder('Nombre nuevo levantamiento').fill('Otro levantamiento UTM 15');
    await page.getByLabel('Sistema de coordenadas').selectOption('32615');
    const [secondSurveyCreated]=await Promise.all([
      page.waitForResponse(r=>r.request().method()==='POST' && /\/topografia\/[^/]+\/levantamientos$/.test(new URL(r.url()).pathname)),
      page.getByRole('button',{name:'Crear levantamiento',exact:true}).click()]);
    assert.equal(secondSurveyCreated.status(),200);
    await page.getByRole('button',{name:'Calcular',exact:true}).waitFor({state:'hidden'});
    assert.equal(await page.getByRole('button',{name:'Calcular',exact:true}).count(),0);
    await page.getByLabel('Levantamiento activo').selectOption(survey.id);
    await page.getByLabel('Superficie existente').waitFor();
    assert.equal(await page.getByLabel('Superficie existente').inputValue(),'');
    assert.equal(await page.getByRole('button',{name:'Calcular',exact:true}).isDisabled(),true);
    const projects = start('project-fixtures', join(backend,'.venv/bin/python'),
      ['-m','scripts.seed_bim_acceptance_ci','--projects-after',model.expediente_id],backend);
    const [projectsExit]=await once(projects,'exit');
    assert.equal(projectsExit,0);
    await page.goto(origin+'/?app=megalodon-costos');
    await page.getByRole('button',{name:'Presupuesto',exact:true}).click();
    await page.getByRole('button',{name:'Actualizar material',exact:true}).click();
    await page.getByText('Catálogos en la base conectada',{exact:true}).click();
    await page.getByText('Investigación de mercado Megalodon · enero 2020',{exact:false}).waitFor();
    await page.getByLabel('Material revisado',{exact:true}).selectOption(credentials.indexed_material);
    await page.getByLabel('Fecha de corte de publicaciones',{exact:true}).fill('2020-09-10');
    await page.getByRole('button',{name:'Usar última publicación disponible',exact:true}).click();
    await page.getByText('Variación observada: 15.0000% · corte 2020-09-10.',{exact:true}).waitFor();
    await page.getByText('Original: $100.0000 MXN · Estimado: $115.00 MXN/kg sin IVA.',{exact:true}).waitFor();
    await page.screenshot({path:join(evidence,'08-catalogos-indices.png'),fullPage:true});
    // Synthetic source ZIP crosses the real import API and migrated schema.
    // The private authentic CMIC/Varela packages are exercised separately.
    await page.getByRole('button',{name:'Investigación de mercado Megalodon',exact:true}).click();
    await page.getByText('Ediciones importadas y revisiones pendientes',{exact:true}).click();
    const [previewed] = await Promise.all([
      page.waitForResponse(r=>r.request().method()==='POST' && new URL(r.url()).pathname==='/api/v1/catalogo-apu/importaciones/verificar'),
      page.getByLabel('Importar paquete de catálogo ZIP').setInputFiles(credentials.catalog_package)]);
    assert.equal(previewed.status(),200);
    const [imported] = await Promise.all([
      page.waitForResponse(r=>r.request().method()==='POST' && new URL(r.url()).pathname==='/api/v1/catalogo-apu/importaciones'),
      page.getByRole('button',{name:'Importar fuentes seleccionadas',exact:true}).click()]);
    assert.equal(imported.status(),200);
    const edition = await imported.json();
    assert.equal(edition.resumen.proyecciones_costeo,1);
    await page.getByLabel('Modelo paramétrico',{exact:true}).selectOption({label:'MODEL-TEST · Synthetic parametric model · $4029.74/m2'});
    await page.getByLabel('Localidad de la obra',{exact:true}).selectOption({label:'Synthetic city · FIC 0.897'});
    await page.getByLabel('Cantidad m2',{exact:true}).fill('36');
    await page.getByLabel('Justificación y condiciones del proyecto',{exact:true}).fill('Caso sintético de aceptación del modelo base');
    const [estimated] = await Promise.all([
      page.waitForResponse(r=>r.request().method()==='POST' && new URL(r.url()).pathname==='/api/v1/catalogo-apu/estimaciones-parametricas'),
      page.getByRole('button',{name:'Calcular y guardar antepresupuesto',exact:true}).click()]);
    assert.equal(estimated.status(),200);
    const estimate = await estimated.json();
    assert.equal(Number(estimate.monto),130128.36);
    assert.equal(estimate.evidencia.apto_aprobacion_contractual,false);
    await page.getByLabel('Buscar en catálogos importados',{exact:true}).fill('TEST-EXC');
    await page.getByLabel('Concepto importado',{exact:true}).selectOption({label:'TEST-EXC · Synthetic excavation with six-decimal consumption · 152.43 / m3 · 2026-01-01'});
    await page.getByLabel('Cantidad medida m3',{exact:true}).fill('2.4');
    await page.getByRole('button',{name:'Agregar concepto al presupuesto',exact:true}).click();
    await page.getByLabel('Cantidad medida m3',{exact:true}).fill('0.0420');
    await page.getByRole('button',{name:'Agregar concepto al presupuesto',exact:true}).click();
    await page.getByRole('cell',{name:'0.042',exact:true}).waitFor();
    await page.getByPlaceholder('Contrato, convocatoria, análisis...').fill('Caso sintético sin recargos para comprobar precio fuente');
    const [pricedCatalogue] = await Promise.all([
      page.waitForResponse(r=>r.request().method()==='POST' && /\/presupuestos\/[^/]+\/presupuestos$/.test(new URL(r.url()).pathname)),
      page.getByRole('button',{name:'Guardar en backend',exact:true}).click()]);
    assert.equal(pricedCatalogue.status(),200);
    const catalogBudget = await pricedCatalogue.json();
    assert.equal(catalogBudget.monto_total,372.23);
    assert.equal(catalogBudget.partidas[1].cantidad,0.042);
    assert.equal(catalogBudget.partidas[1].importe,6.40);
    assert.equal(catalogBudget.partidas[0].conceptos[0].insumos[0].cantidad,0.227273);
    assert.equal(catalogBudget.partidas[0].metadatos.catalogo_asignado.origen_importacion.importacion_id,edition.id);
    await page.screenshot({path:join(evidence,'11-importacion-costeo-catalogo.png'),fullPage:true});
    await page.getByRole('button',{name:'Validar',exact:true}).click();
    await page.getByRole('button',{name:'Aprobar',exact:true}).click();
    await page.getByText('APROBADO',{exact:true}).waitFor();
    assert.equal(await page.getByLabel('Cantidad partida 1',{exact:true}).isDisabled(),true);
    await page.getByLabel('Motivo de revisión').fill('CI: nueva medición sin sustituir la versión aprobada');
    const [revisionResponse] = await Promise.all([
      page.waitForResponse(r=>r.request().method()==='POST' && r.url().endsWith('/revisiones')),
      page.getByRole('button',{name:'Crear revisión independiente',exact:true}).click()]);
    assert.equal(revisionResponse.status(),201);
    const revision = await revisionResponse.json();
    assert.equal(revision.metadatos.revision.presupuesto_origen_id,catalogBudget.id);
    await page.getByLabel('Cantidad partida 1',{exact:true}).fill('3');
    await page.getByRole('button',{name:'Guardar cantidad',exact:true}).first().click();
    await page.getByText('Total guardado: $463.69',{exact:true}).waitFor();
    await page.reload();
    await page.getByRole('button',{name:'Presupuesto',exact:true}).click();
    await page.getByRole('button',{name:/Abrir .*CALCULADO.*463.69/}).click();
    assert.equal(await page.getByLabel('Cantidad partida 1',{exact:true}).inputValue(),'3');
    await page.getByText('Ver conceptos e insumos',{exact:true}).first().click();
    await page.getByRole('button',{name:'Comparar con versión de origen',exact:true}).click();
    await page.getByRole('status').filter({hasText:'Base: $372.23'}).waitFor();
    const budgetsResponse = await page.request.get(`${apiOrigin}/api/v1/presupuestos/${model.expediente_id}/presupuestos`);
    assert.equal(budgetsResponse.status(),200);
    const budgets = await budgetsResponse.json();
    const approved = budgets.find(b=>b.id===catalogBudget.id);
    const changed = budgets.find(b=>b.id===revision.id);
    assert.equal(approved.estado,'APROBADO');
    assert.equal(approved.monto_total,372.23);
    assert.equal(approved.partidas[0].cantidad,2.4);
    assert.equal(changed.partidas[0].conceptos[0].insumos[0].cantidad,0.227273);
    assert.equal(changed.partidas[0].metadatos.catalogo_asignado.sha256,
                 approved.partidas[0].metadatos.catalogo_asignado.sha256);
    await page.screenshot({path:join(evidence,'12-costos-revision-persistida.png'),fullPage:true});

    await page.goto(origin+'/?app=legl-consultor');
    await page.getByText('969 artículos consultables · ver cobertura',{exact:true}).click();
    await page.getByText('Documentos sin artículos consultables: Manual Comité Adquisiciones.',{exact:true}).waitFor();
    await page.screenshot({path:join(evidence,'09-cobertura-corpus.png'),fullPage:true});
    assert.deepEqual(errors,[]);

  } finally {
    await page.screenshot({path:join(evidence,'last-screen.png'),fullPage:true}).catch(()=>{});
    await context.tracing.stop({path:join(evidence,'bim-flow-trace.zip')});
    await context.close();
  }
});


test('bidder prepares a proposal workspace and source requirements stay blocked for human review', {timeout:240000}, async () => {
  await licitacionFlow({ browser, credentials, origin, evidence, login });
});
