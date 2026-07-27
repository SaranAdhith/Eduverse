import { expect, test } from "@playwright/test";

// DOC_07 §7.2: enroll + answer 5 diagnostic items -> "close tab" (new context)
// -> resume with the code -> the diagnostic resumes at item 6.
test("resume continues the diagnostic where it left off", async ({
  page,
  context,
}) => {
  await page.goto("/");
  await page.getByRole("link", { name: /start as new participant/i }).click();
  await page.getByLabel(/i have read the above and consent/i).click();
  await page.getByRole("button", { name: /generate my code/i }).click();
  await expect(page).toHaveURL(/\/diagnostic/);

  // Answer the first 5 items.
  for (let i = 0; i < 5; i++) {
    await expect(
      page.getByText(new RegExp(`question ${i + 1} of 25`, "i")),
    ).toBeVisible();
    await page.getByRole("radio").first().check();
    await page.getByRole("button", { name: /submit answer/i }).click();
    await page.getByRole("button", { name: /next question/i }).click();
  }

  // Recover the stored code, then simulate a fresh tab.
  const code = await page.evaluate(() =>
    window.localStorage.getItem("eduverse.participant_code"),
  );
  expect(code).toBeTruthy();
  await context.clearCookies();

  const fresh = await context.newPage();
  await fresh.goto("/resume");
  await fresh.getByLabel(/participant code/i).fill(code as string);
  await fresh.getByRole("button", { name: /^resume$/i }).click();

  // Resume routes to the dashboard; opening the diagnostic again picks up at 6.
  await expect(fresh).toHaveURL(/\/dashboard/);
  await fresh.goto("/diagnostic");
  await expect(fresh.getByText(/question 6 of 25/i)).toBeVisible();
});
