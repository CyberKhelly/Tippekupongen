import { chromium } from 'playwright';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const CHROMIUM = 'C:/Users/kimme/AppData/Local/ms-playwright/chromium-1223/chrome-win64/chrome.exe';

const browser = await chromium.launch({
  executablePath: CHROMIUM,
  headless: true,
  args: ['--no-sandbox', '--disable-setuid-sandbox'],
});

const page = await browser.newPage();
await page.setViewportSize({ width: 1440, height: 900 });

// Coupon page — wait for the match table to appear (data loaded)
await page.goto('http://localhost:3000/coupon', { waitUntil: 'networkidle', timeout: 20000 });
await page.waitForTimeout(2000);
await page.screenshot({ path: join(ROOT, 'screenshot_coupon.png'), fullPage: false });
console.log('Saved screenshot_coupon.png');

// History page
await page.goto('http://localhost:3000/history', { waitUntil: 'networkidle', timeout: 15000 });
await page.waitForTimeout(1500);
await page.screenshot({ path: join(ROOT, 'screenshot_history.png'), fullPage: false });
console.log('Saved screenshot_history.png');

await browser.close();
