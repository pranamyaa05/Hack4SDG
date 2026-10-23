import { test, expect, type Page } from "@playwright/test";
async function begin(page: Page, track: "adapt" | "repair") {
  await page.goto("/app/");
  await expect(
    page.getByRole("heading", { name: "Make everyday fit you." }),
  ).toBeVisible();
  if (track === "repair")
    await page
      .getByRole("button", { name: /Repair A replacement drawer pull/ })
      .click();
  await page
    .getByLabel("What is difficult, or what broke?")
    .fill(
      track === "adapt" ? "My grip is weak" : "The drawer pull is missing.",
    );
  await page.getByLabel("I agree to store this project").check();
  await page.getByRole("button", { name: "Continue ↗", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Does this look right?" }),
  ).toBeVisible();
  if (track === "adapt") await page.getByLabel("The handle is intact").check();
  await page
    .getByRole("button", { name: "Confirm object", exact: true })
    .click();
  if (track === "adapt")
    await page.getByLabel("Which would you rather hold?").selectOption("soft");
  else {
    await page
      .getByLabel("What needs repairing?")
      .selectOption("missing_pull_visible_holes");
    await page.getByLabel("Is the drawer face intact").selectOption("sound");
  }
  await page
    .getByRole("button", { name: "Continue to measurements ↗" })
    .click();
  await page.getByRole("button", { name: "Start measuring ↗" }).click();
}
async function enter(page: Page, dimension: string, value: string) {
  const row = page
    .locator(".measurement-row")
    .filter({ has: page.getByLabel(dimension + " in mm", { exact: true }) });
  await row.getByRole("spinbutton").fill(value);
  await row.getByRole("button", { name: "Confirm reading" }).click();
  await expect(row.locator(".measurement-value")).toContainText(value + ".00");
}
test("Adapt: measured package, fit feedback, Statistics, saved design, Re-fit", async ({
  page,
}) => {
  await begin(page, "adapt");
  await enter(page, "handle width", "14");
  await enter(page, "handle thickness", "7");
  await enter(page, "covered length", "90");
  await page.getByRole("button", { name: "See design options ↗" }).click();
  await page
    .getByRole("button", { name: "Generate measured package ↗" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Your next step is a physical test." }),
  ).toBeVisible({ timeout: 60000 });
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: "Download complete package ↓" }).click(),
  ]);
  expect(download.suggestedFilename()).toBe("package.zip");
  await page.getByLabel("Physical fit result").selectOption("fits");
  await page.getByLabel("The object is back in use.").check();
  await page
    .getByRole("button", { name: "Save feedback", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("Fit feedback saved");
  await page.getByRole("button", { name: "Statistics", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Small changes. Real records." }),
  ).toBeVisible();
  await expect(
    page.locator(".stat").filter({ hasText: "Objects kept in use" }),
  ).toContainText("1");
  await page.getByRole("button", { name: "Your designs", exact: true }).click();
  await page.getByRole("button", { name: "View files" }).first().click();
  await expect(
    page.getByRole("heading", { name: "Your next step is a physical test." }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Re-fit this design ↻" }).click();
  await expect(
    page.getByRole("heading", { name: "Does this look right?" }),
  ).toBeVisible();
  await page.getByText("Change my answers", { exact: true }).click();
  await page.getByLabel("Updated need", { exact: true }).selectOption("pain");
  await page
    .getByRole("button", { name: "Save updated need", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Continue to measurements ↗", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Get the fit right." }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/adapt-refit.png",
    fullPage: true,
  });
});
test("Repair: confirmed mounting, CAD package, mobile layout", async ({
  page,
}) => {
  await begin(page, "repair");
  await enter(page, "hole spacing", "96");
  await enter(page, "hole diameter", "4");
  await page.getByRole("button", { name: "See design options ↗" }).click();
  await page.getByLabel("Bolt diameter (mm)", { exact: true }).fill("3");
  await page.getByLabel("Drawer-face thickness (mm)").fill("16");
  await page.getByLabel("Bolt usable length (mm)").fill("70");
  await page.getByLabel("Nut height (mm)").fill("3");
  await page.getByLabel("I measured this hardware").check();
  await page
    .getByRole("button", { name: "Generate measured package ↗" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Your next step is a physical test." }),
  ).toBeVisible({ timeout: 60000 });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("link", { name: "Download complete package ↓" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "test-results/repair-mobile.png",
    fullPage: true,
  });
});
test("Empty state and desktop presentation", async ({ page }) => {
  await page.goto("/app/");
  await page.screenshot({
    path: "test-results/studio-desktop.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Statistics", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Evidence over assumptions." }),
  ).toBeVisible();
});
