// Production-bundle CSS regression checks. API responses are anonymous test
// fixtures; these checks do not certify authenticated backend workflows.
import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { chromium } from 'playwright';

const origin = 'http://127.0.0.1:4173';
let server;
let browser;

before(async () => {
  const args = ['node_modules/vite/bin/vite.js', 'preview',
    '--host', '127.0.0.1', '--port', '4173', '--strictPort'];
  if (process.env.STYLE_BUILD_DIR) args.push('--outDir', process.env.STYLE_BUILD_DIR);
  server = spawn(process.execPath, args, { stdio: 'ignore' });
  for (let attempt = 0; attempt < 100; attempt++) {
    if (server.exitCode !== null) throw new Error('Production preview stopped');
    try { if ((await fetch(origin)).ok) break; } catch { /* wait for preview */ }
    if (attempt === 99) throw new Error('Production preview did not become ready');
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  browser = await chromium.launch({
    executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined,
  });
});

after(async () => {
  await browser?.close();
  if (server && server.exitCode === null) {
    const closed = once(server, 'exit');
    server.kill();
    await closed;
  }
});

test('production login remains usable on desktop and mobile', async () => {
  for (const viewport of [{ width: 1280, height: 800 }, { width: 390, height: 844 }, { width: 390, height: 500 }]) {
    const page = await browser.newPage({ viewport });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    // Anonymous session and unavailable backend, explicitly confined to tests.
    await page.route('**/api/v1/**', route => route.fulfill({
      status: 401, contentType: 'application/json', body: '{"detail":"Anonymous fixture"}',
    }));
    await page.goto(origin);
    const email = page.getByPlaceholder('tu@correo.com');
    await email.waitFor({ state: 'visible' });
    await page.waitForFunction(() => getComputedStyle(document.querySelector('form')).opacity === '1');
    const bounds = await email.boundingBox();
    assert.ok(bounds.width > 250 && bounds.x >= 0 && bounds.x + bounds.width <= viewport.width);
    assert.equal(bounds.height, 44);
    const password = page.locator('input[type="password"]');
    await password.fill('synthetic-test');
    await page.locator('button[type="button"]').click();
    await page.locator('input[type="text"]').waitFor({ state: 'visible' });
    assert.equal(await page.locator('input[type="text"]').inputValue(), 'synthetic-test');
    await page.getByRole('button', { name: 'Entrar al Sistema' }).click();
    await page.getByText('El usuario es obligatorio', { exact: true }).waitFor();
    await page.waitForFunction(() => getComputedStyle(document.querySelector('input[type="email"]')).borderColor === 'rgb(42, 42, 62)');
    const styles = await email.evaluate(element => {
      const style = getComputedStyle(element);
      return { radius: style.borderRadius, color: style.borderColor };
    });
    assert.equal(styles.radius, '6px');
    assert.equal(styles.color, 'rgb(42, 42, 62)');
    await page.emulateMedia({ forcedColors: 'active' });
    assert.equal(await email.evaluate(element => getComputedStyle(element).outlineStyle), 'solid');
    await page.emulateMedia({ forcedColors: 'none' });
    const submit = await page.getByRole('button', { name: 'Entrar al Sistema' }).boundingBox();
    const version = await page.getByText(/Megalodon OS v3\.1/).boundingBox();
    assert.ok(version.y >= submit.y + submit.height, 'Version label must not overlap the submit control');
    assert.deepEqual(errors, []);
    if (process.env.STYLE_EVIDENCE_DIR) {
      await page.waitForFunction(() => {
        const version = [...document.querySelectorAll('p')].find(element => element.textContent.includes('Megalodon OS v3.1'));
        return version && getComputedStyle(version).opacity === '1';
      });
      await mkdir(process.env.STYLE_EVIDENCE_DIR, { recursive: true });
      await page.screenshot({ path: join(process.env.STYLE_EVIDENCE_DIR, `login-${viewport.width}-${viewport.height}.png`) });
    }
    await page.close();
  }
});

test('compiled semantic colors, font and enter animations resolve in the browser', async () => {
  const page = await browser.newPage();
  await page.goto(origin);
  const values = await page.evaluate(() => {
    const probe = document.createElement('div');
    probe.className = 'bg-primary text-primary-foreground border border-input rounded-md font-mono animate-in fade-in-0 zoom-in-95';
    document.body.append(probe);
    const styles = getComputedStyle(probe);
    const indicator = document.createElement('div');
    indicator.className = 'border-(--chart-indicator-color) border-dashed border-[1.5px]';
    document.body.append(indicator);
    const indicatorBorders = ['#ff0000', '#00ff00'].map(color => {
      indicator.style.setProperty('--chart-indicator-color', color);
      return getComputedStyle(indicator).borderColor;
    });
    return { background: styles.backgroundColor, border: styles.borderColor,
      radius: styles.borderRadius, font: styles.fontFamily, animation: styles.animationName,
      foreground: styles.color, enterOpacity: styles.getPropertyValue('--tw-enter-opacity').trim(), indicatorBorders };
  });
  assert.equal(values.radius, '6px');
  assert.notEqual(values.background, 'rgba(0, 0, 0, 0)');
  assert.notEqual(values.background, values.foreground);
  assert.equal(values.border, 'rgb(46, 46, 56)');
  assert.match(values.font, /JetBrains Mono/);
  assert.equal(values.animation, 'enter');
  assert.equal(values.enterOpacity, '0');
  assert.deepEqual(values.indicatorBorders, ['rgb(255, 0, 0)', 'rgb(0, 255, 0)']);
  await page.close();
});

// Layout fixtures exercise the compiled BIM UI, without authenticating to a
// backend or claiming IFC geometry/quantity validation.
test('BIM studio stays reachable on desktop and short mobile screens', async () => {
  for (const viewport of [{ width: 1440, height: 900 }, { width: 1024, height: 768 }, { width: 390, height: 844 }, { width: 390, height: 500 }]) {
    const page = await browser.newPage({ viewport });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.addInitScript(() => localStorage.setItem('megalodon-expediente-activo',
      JSON.stringify({ state: { expedienteActivoId: 'visual-project' }, version: 0 })));
    await page.route('**/*', route => {
      const path = new URL(route.request().url()).pathname;
      if (!path.startsWith('/api/') && !['/health', '/ready'].includes(path)) return route.continue();
      let data = [];
      if (path === '/ready') data = { status: 'ready' };
      if (path.endsWith('/auth/me')) data = { id: 'visual-user', full_name: 'Revisión visual', email: 'visual@example.test', role: 'admin' };
      if (path.endsWith('/mi-plan')) data = { plan: 'enterprise', plan_efectivo: 'enterprise', limites: {}, uso_actual: {} };
      if (path === '/api/v1/expedientes') data = [{ id: 'visual-project', titulo: 'Obra de prueba · revisión visual BIM/CAD', estado: 'ABIERTO' }];
      if (path.endsWith('/modelos')) data = [{ id: 'visual-model', nombre: 'Modelo sintético de revisión', estado_procesamiento: 'COMPLETADO', num_elementos: 40, niveles: ['Planta baja', 'Planta alta'] }];
      if (path.endsWith('/elementos')) data = Array.from({ length: 40 }, (_, i) => ({
        id: `e${i}`, tipo: `IfcPrueba${i}`, nombre: `Elemento ${i}`, nivel: i % 2 ? 'Planta alta' : 'Planta baja',
        volumen: 3, area: 5, fuente_volumen: 'QTO_IFC', fuente_area: 'QTO_IFC',
        malla_vertices: [0, 0, 0, 4, 0, 0, 0, 3, 0], malla_caras: [0, 1, 2],
      }));
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) });
    });
    await page.goto(`${origin}/?app=bim-calculator`);
    await page.locator('.bim-studio-inspector').waitFor();
    await page.waitForFunction(() => {
      let node = document.querySelector('.bim-studio');
      while (node) { if (getComputedStyle(node).opacity !== '1') return false; node = node.parentElement; }
      return true;
    });
    const studio = page.locator('.bim-studio');
    assert.equal(await studio.evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(255, 255, 255)');
    await page.getByRole('button', { name: 'Activar modo oscuro', exact: true }).click();
    await page.waitForFunction(() => document.documentElement.dataset.theme === 'dark');
    assert.notEqual(await studio.evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(255, 255, 255)');
    await page.reload();
    await page.locator('.bim-studio-inspector').waitFor();
    await page.getByRole('button', { name: 'Activar modo claro', exact: true }).waitFor();
    await page.getByRole('button', { name: 'Activar modo claro', exact: true }).click();
    await page.waitForFunction(() => document.documentElement.dataset.theme === 'light');
    assert.equal(await page.getByRole('menuitem', { name: 'Workspace', exact: true }).count(), 0);
    await page.getByRole('button', { name: 'Abrir bandeja de trabajo' }).click();
    await page.getByRole('menuitem', { name: 'Workspace', exact: true }).waitFor();
    await page.getByRole('menuitem', { name: 'Tezcatlipoca', exact: true }).waitFor();
    await page.getByRole('menuitem', { name: 'Firma / Field SAT', exact: true }).waitFor();
    await page.keyboard.press('Escape');
    assert.equal(await page.getByRole('button', { name: 'Abrir bandeja de trabajo' }).evaluate(el => el === document.activeElement), true);
    await page.getByText('Herramientas de vista', { exact: true }).click();
    await page.getByLabel('Mostrar IfcPrueba0', { exact: true }).uncheck();
    await page.getByText('39 de 40 elementos visibles', { exact: true }).waitFor();
    await page.getByRole('button', { name: 'Restablecer vista', exact: true }).click();
    await page.getByText('40 de 40 elementos visibles', { exact: true }).waitFor();
    await page.getByText('Herramientas de vista', { exact: true }).click();
    assert.ok(await studio.evaluate(el => el.scrollWidth <= el.clientWidth), 'No horizontal overflow');
    const factors = await page.locator('.bim-studio-cost-factors input').evaluateAll(inputs => inputs.map(el => el.getBoundingClientRect().width));
    assert.ok(factors.every(width => width >= 115), 'Cost inputs must remain readable');
    if (viewport.width >= 1024) {
      // R3F resizes its canvas asynchronously after closing the view tools.
      await page.waitForFunction(() => Math.abs(document.querySelector('canvas').getBoundingClientRect().height -
        document.querySelector('.bim-studio-viewport').getBoundingClientRect().height) < 1);
      const canvasBefore = await page.locator('canvas').boundingBox();
      const content = page.locator('.bim-studio-inspector > div').nth(1);
      await content.evaluate(el => { el.scrollTop = el.scrollHeight; });
      assert.ok(await content.evaluate(el => el.scrollTop > 0), 'Inspector scrolls independently');
      assert.deepEqual(await page.locator('canvas').boundingBox(), canvasBefore);
    } else {
      assert.ok(await studio.evaluate(el => el.scrollHeight > el.clientHeight), 'Mobile uses the whole studio for scrolling');
      await page.getByRole('button', { name: 'Resumen', exact: true }).scrollIntoViewIfNeeded();
      const bounds = await page.getByRole('button', { name: 'Resumen', exact: true }).boundingBox();
      assert.ok(bounds.y >= 0 && bounds.y + bounds.height <= viewport.height, 'Inspector navigation is reachable');
      await studio.evaluate(el => { el.scrollTop = 0; });
    }
    const plan = page.getByRole('button', { name: 'Planta (2D)', exact: true });
    await plan.click();
    assert.equal(await plan.getAttribute('aria-pressed'), 'true');
    const wire = page.getByRole('button', { name: 'Alambre', exact: true });
    await wire.focus(); await page.keyboard.press('Space');
    assert.equal(await wire.getAttribute('aria-pressed'), 'true');
    await page.getByRole('button', { name: '2. Preparar presupuesto', exact: true }).click();
    assert.equal(await page.getByRole('button', { name: 'Presupuesto', exact: true }).getAttribute('aria-pressed'), 'true');
    await page.getByRole('button', { name: '3. Crear cronograma', exact: true }).click();
    assert.equal(await page.getByRole('button', { name: 'Cronograma', exact: true }).getAttribute('aria-pressed'), 'true');
    await page.getByRole('button', { name: '1. Revisar cantidades', exact: true }).click();
    await page.getByRole('button', { name: 'Vista 3D', exact: true }).click();
    await page.waitForFunction(() => [...document.querySelectorAll('button')]
      .some(el => el.textContent.trim() === 'Vista 3D' && el.getAttribute('aria-pressed') === 'true'));
    await studio.evaluate(el => { el.scrollTop = 0; });
    if (process.env.STYLE_EVIDENCE_DIR) {
      await mkdir(process.env.STYLE_EVIDENCE_DIR, { recursive: true });
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      await page.screenshot({ path: join(process.env.STYLE_EVIDENCE_DIR, `bim-${viewport.width}-${viewport.height}.png`) });
      if (viewport.width < 1024) {
        await page.getByRole('button', { name: 'Resumen', exact: true }).scrollIntoViewIfNeeded();
        await page.screenshot({ path: join(process.env.STYLE_EVIDENCE_DIR, `bim-inspector-${viewport.width}-${viewport.height}.png`) });
      }
    }
    assert.deepEqual(errors, []);
    await page.close();
  }
});
