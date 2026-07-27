import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// DOC_07 §7.3: axe-core scan on every route, no critical violations.
async function scan(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  const critical = results.violations.filter((v) => v.impact === "critical");
  expect(critical, JSON.stringify(critical, null, 2)).toEqual([]);
}

test("public routes have no critical a11y violations", async ({ page }) => {
  for (const path of ["/", "/enroll", "/resume"]) {
    await page.goto(path);
    await scan(page);
  }
});

test("authenticated routes have no critical a11y violations", async ({
  page,
}) => {
  // Enroll to reach the participant-only routes.
  await page.goto("/enroll");
  await page.getByLabel(/i have read the above and consent/i).click();
  await page.getByRole("button", { name: /generate my code/i }).click();
  await expect(page).toHaveURL(/\/diagnostic/);
  await scan(page);

  // Answer through to the dashboard, then scan it.
  for (let i = 0; i < 25; i++) {
    await page.getByRole("radio").first().check();
    await page.getByRole("button", { name: /submit answer/i }).click();
    await page.getByRole("button", { name: /next question|see results/i }).click();
  }
  await page.getByRole("button", { name: /begin learning/i }).click();
  await expect(page).toHaveURL(/\/dashboard/);
  await scan(page);
});
