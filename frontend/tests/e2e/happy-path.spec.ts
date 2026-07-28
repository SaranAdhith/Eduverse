import { expect, test } from "@playwright/test";

// DOC_07 §7.1: enroll -> diagnostic (auto-answer A) -> dashboard -> open first
// step -> submit gate (auto-answer A) -> expect pass or fail with routing.
test("enroll, complete diagnostic, and attempt a gate", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: /enrol and begin/i }).click();

  // Consent + enroll.
  await page.getByLabel(/i have read the above and consent/i).click();
  await page
    .getByRole("button", { name: /consent and begin placement/i })
    .click();

  // The issued code gets a screen of its own before the paper starts.
  await page.getByRole("button", { name: /begin placement paper/i }).click();

  // Diagnostic: answer every item by choosing the first option.
  await expect(page).toHaveURL(/\/diagnostic/);
  for (let i = 0; i < 25; i++) {
    await page.getByRole("radio").first().check();
    const submit = page.getByRole("button", { name: /submit answer/i });
    await submit.click();
    // Advance past the correctness reveal.
    const next = page.getByRole("button", {
      name: /continue|see starting estimates/i,
    });
    await next.click();
  }

  // Completion -> dashboard.
  await page.getByRole("button", { name: /start learning/i }).click();
  await expect(page).toHaveURL(/\/dashboard/);

  // Open the first lesson.
  await page.getByRole("link", { name: /open lesson/i }).click();
  await expect(page).toHaveURL(/\/learn\//);

  // Skip the video wait if present, then go to the gate.
  const finished = page.getByRole("button", {
    name: /i've already finished the video/i,
  });
  if (await finished.isVisible().catch(() => false)) {
    await finished.click();
  }
  await page.getByRole("link", { name: /take the check/i }).click();
  await expect(page).toHaveURL(/\/gate/);

  // Answer all 5 gate items with the first choice.
  for (let i = 0; i < 5; i++) {
    await page.getByRole("radio").first().check();
    await page
      .getByRole("button", { name: /next question|submit answers/i })
      .click();
  }

  // Either outcome is acceptable; both route somewhere sensible.
  await expect(
    page.getByText(/you can move on\.|one more pass at this one\./i),
  ).toBeVisible();
});
