import { test, expect } from '@playwright/test';

const base = process.env.MEGALODON_UI_URL;
const email = process.env.MEGALODON_E2E_EMAIL;
const password = process.env.MEGALODON_E2E_PASSWORD;

test.skip(!base || !email || !password, 'Requires MEGALODON_UI_URL, MEGALODON_E2E_EMAIL and MEGALODON_E2E_PASSWORD');

test('login -> command center -> topography -> Tezcatlipoca context', async ({ page }) => {
  await page.goto(base!);
  await page.getByLabel(/email/i).fill(email!);
  await page.getByLabel(/contraseña|password/i).fill(password!);
  await page.getByRole('button', { name: /iniciar sesión|login/i }).click();

  await expect(page.getByText(/Inicio|Command Center/i).first()).toBeVisible();
  await page.getByRole('button', { name: /Topografía/i }).click();
  await expect(page.getByText(/Tezcatlipoca/i).first()).toBeVisible();
});
