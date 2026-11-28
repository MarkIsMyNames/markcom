import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

type StoryEntry = { id: string; type: string };
type StoryIndex = { entries: Record<string, StoryEntry> };

export function testStoryScreenshots(): void {
  test('every story matches its baseline', async ({
    page,
    request,
  }: {
    page: Page;
    request: APIRequestContext;
  }): Promise<void> => {
    const index: StoryIndex = (await (await request.get('/index.json')).json()) as StoryIndex;
    const storyIds: string[] = Object.values(index.entries)
      .filter((entry: StoryEntry): boolean => entry.type === 'story')
      .map((entry: StoryEntry): string => entry.id);

    for (const id of storyIds) {
      await test.step(id, async (): Promise<void> => {
        await page.goto(`/iframe.html?id=${id}&viewMode=story`);
        await page.locator('#storybook-root').waitFor();
        await page.evaluate((): Promise<FontFaceSet> => document.fonts.ready);
        await expect.soft(page).toHaveScreenshot(`${id}.png`, { fullPage: true });
      });
    }
  });
}
