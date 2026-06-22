const puppeteer = require('./node_modules/puppeteer');

(async () => {
  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });

  const errors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') errors.push(msg.text().slice(0, 80));
  });

  console.log('loading production page on 3002...');
  await page.goto('http://localhost:3002/coupon', { waitUntil: 'networkidle0', timeout: 30000 });
  await new Promise(r => setTimeout(r, 5000));

  await page.screenshot({ path: 'temporary_screenshots/screenshot-12-main-prod.png', fullPage: false });
  console.log('saved main page');

  if (errors.length) console.log('errors:', errors.slice(0, 3).join('; '));

  const rows = await page.$$('tbody tr');
  console.log('table rows found:', rows.length);

  if (rows.length > 0) {
    // Screenshot table area specifically
    const table = await page.$('table');
    if (table) {
      const box = await table.boundingBox();
      await page.screenshot({
        path: 'temporary_screenshots/screenshot-13-table-zoom.png',
        clip: { x: box.x, y: Math.max(0, box.y - 10), width: Math.min(box.width, 1440), height: Math.min(box.height + 20, 900) },
      });
      console.log('saved table zoom');
    }

    // Expand third row
    await rows[2].click();
    await new Promise(r => setTimeout(r, 2000));
    await page.screenshot({ path: 'temporary_screenshots/screenshot-14-expanded-card.png', fullPage: true });
    console.log('saved expanded card (full page)');

    // Zoom into the expanded card header
    const card = await page.$('.animate-expand-down');
    if (card) {
      const cardBox = await card.boundingBox();
      if (cardBox) {
        await page.screenshot({
          path: 'temporary_screenshots/screenshot-15-card-header-zoom.png',
          clip: { x: cardBox.x, y: cardBox.y, width: cardBox.width, height: Math.min(cardBox.height, 600) },
        });
        console.log('saved card header zoom');
      }
    }
  }

  await browser.close();
  console.log('done');
})().catch(e => { console.error(e.message); process.exit(1); });
