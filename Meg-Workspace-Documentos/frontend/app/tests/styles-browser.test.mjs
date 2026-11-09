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
