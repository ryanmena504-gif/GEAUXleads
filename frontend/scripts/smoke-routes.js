#!/usr/bin/env node
/**
 * Route smoke test — loads every route in a real browser and fails if any
 * page throws (ReferenceError from a dropped import, a crash caught by
 * RouteErrorBoundary, or an uncaught error in the console).
 *
 * Needs Playwright (not a project dependency, so Railway builds stay lean):
 *   npx -p playwright@1 node scripts/smoke-routes.js
 *
 * Usage:
 *   APP_URL=https://geauxleads-frontend-production.up.railway.app node scripts/smoke-routes.js
 *   APP_URL=http://localhost:3000 node scripts/smoke-routes.js
 *
 * Point APP_URL at a deployed frontend to test against real Airtable data.
 * Read-only: it only navigates; it never clicks anything.
 */
const { chromium } = require("playwright");

const APP_URL = (process.env.APP_URL || "http://localhost:3000").replace(/\/$/, "");

// Keep in sync with the <Route> list in src/App.js.
const ROUTES = [
  "/",
  "/opportunities",
  "/missions",
  "/relationships",
  "/intelligence",
  "/review-queue",
  "/settings",
  "/lookup",
  "/debug",
  "/discovery/property-managers",
  "/discovery/real-estate-agents",
  "/discovery/landlords",
  "/discovery/landlords/print",
  "/discovery/investors",
];

async function checkRoute(page, path) {
  const errors = [];
  const onPageError = (err) => errors.push(`uncaught: ${err.message}`);
  const onConsole = (msg) => {
    if (msg.type() === "error" && /ReferenceError|TypeError|is not defined/.test(msg.text())) {
      errors.push(`console: ${msg.text()}`);
    }
  };
  page.on("pageerror", onPageError);
  page.on("console", onConsole);
  try {
    await page.goto(`${APP_URL}${path}`, { waitUntil: "networkidle", timeout: 45_000 });
    if (await page.locator('[data-testid="route-error"]').count()) {
      errors.push(`route error boundary: ${await page.locator('[data-testid="route-error"] pre').innerText()}`);
    }
    const text = (await page.locator("#root").innerText()).trim();
    if (!text) errors.push("page rendered blank");
  } catch (err) {
    errors.push(`navigation: ${err.message}`);
  } finally {
    page.off("pageerror", onPageError);
    page.off("console", onConsole);
  }
  return errors;
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  let failed = 0;

  for (const path of ROUTES) {
    const errors = await checkRoute(page, path);
    if (errors.length) {
      failed += 1;
      console.log(`FAIL ${path}`);
      errors.forEach((e) => console.log(`     ${e}`));
    } else {
      console.log(`ok   ${path}`);
    }
  }

  // One detail page, using the first project the list page links to.
  await page.goto(`${APP_URL}/opportunities`, { waitUntil: "networkidle" });
  const detailHref = await page.evaluate(() => {
    const a = document.querySelector('a[href^="/opportunities/"]');
    return a ? a.getAttribute("href") : null;
  });
  if (detailHref) {
    const errors = await checkRoute(page, detailHref);
    if (errors.length) {
      failed += 1;
      console.log(`FAIL ${detailHref}`);
      errors.forEach((e) => console.log(`     ${e}`));
    } else {
      console.log(`ok   ${detailHref}`);
    }
  } else {
    console.log("skip /opportunities/:id — no project links found");
  }

  await browser.close();
  console.log(failed ? `\n${failed} route(s) failed` : "\nAll routes rendered");
  process.exit(failed ? 1 : 0);
})();
