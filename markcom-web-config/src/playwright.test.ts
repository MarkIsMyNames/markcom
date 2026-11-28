import { describe, expect, it } from 'vitest';
import { APP_URL, STORYBOOK_URL } from './config.ts';
import { createPlaywrightConfig } from './playwright.ts';

describe('createPlaywrightConfig', () => {
  it.each([
    { name: 'visual', baseURL: STORYBOOK_URL },
    { name: 'e2e', baseURL: APP_URL },
  ])('has a $name project on $baseURL', ({ name, baseURL }: { name: string; baseURL: string }) => {
    const project = createPlaywrightConfig().projects?.find((p) => p.name === name);
    expect(project?.use?.baseURL).toBe(baseURL);
  });

  it('waits for storybook to serve', () => {
    const server = createPlaywrightConfig().webServer;
    expect(server).toMatchObject({ url: STORYBOOK_URL });
  });
});
