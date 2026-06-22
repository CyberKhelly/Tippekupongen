import puppeteer from 'puppeteer';
import { existsSync, mkdirSync, readdirSync } from 'fs';
import { join } from 'path';

const ROOT = 'C:/Users/kimme/Desktop/Tippekupongen';
const DIR = join(ROOT, 'temporary_screenshots');
if (!existsSync(DIR)) mkdirSync(DIR, { recursive: true });

function nextIndex() {
  const nums = readdirSync(DIR)
    .map(f => f.match(/^screenshot-(\d+)/))
    .filter(Boolean)
    .map(m => parseInt(m[1], 10));
  return nums.length ? Math.max(...nums) + 1 : 1;
}

const browser = await puppeteer.launch({
  headless: 'new',
  args: ['--no-sandbox', '--disable-setuid-sandbox'],
});

async function snap(page, label) {
  const idx = nextIndex();
  const path = join(DIR, `screenshot-${idx}-${label}.png`);
  await page.screenshot({ path, fullPage: false });
  console.log(`OK screenshot-${idx}-${label}.png`);
}

try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });

  await page.goto('http://localhost:3004/coupon', { waitUntil: 'load', timeout: 30000 });
  await page.waitForFunction(
    () => [...document.querySelectorAll('tbody td')].some(td => td.innerText?.trim().length > 3),
    { timeout: 15000 }
  ).catch(() => {});
  await new Promise(r => setTimeout(r, 1000));

  // Main table
  await snap(page, 'table');

  // Expand row 0 (Marokko vs Haiti — WC, has good data)
  const rows = await page.$$('tbody tr');
  if (rows[0]) {
    await rows[0].click();
    await new Promise(r => setTimeout(r, 1200));
    await snap(page, 'card-header');

    // Scroll to see full card
    await page.evaluate(() => {
      const rows = document.querySelectorAll('tbody tr');
      if (rows[1]) rows[1].scrollIntoView({ block: 'start', behavior: 'instant' });
    });
    await new Promise(r => setTimeout(r, 300));
    await snap(page, 'card-tabell');

    // Scroll more to see Angrep+Forsvar
    await page.evaluate(() => window.scrollBy(0, 200));
    await new Promise(r => setTimeout(r, 300));
    await snap(page, 'card-angrep-analyse');
  }

  // Try row 5 (Ecuador vs Deutschland - heldekk, high CDS)
  if (rows[5]) {
    if (rows[0]) await rows[0].click(); // close first
    await new Promise(r => setTimeout(r, 400));
    await rows[5].click();
    await new Promise(r => setTimeout(r, 1200));
    await page.evaluate(() => {
      const all = document.querySelectorAll('tbody tr');
      if (all[6]) all[6].scrollIntoView({ block: 'center', behavior: 'instant' });
    });
    await new Promise(r => setTimeout(r, 300));
    await snap(page, 'card-ecuador');
  }
} finally {
  await browser.close();
}
