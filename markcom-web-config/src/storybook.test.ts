import { describe, expect, it } from 'vitest';
import { STORIES } from './config.ts';
import { createStorybookConfig } from './storybook.ts';

describe('createStorybookConfig', () => {
  it('loads the stories glob', () => {
    expect(createStorybookConfig().stories).toEqual([STORIES]);
  });

  it('disables telemetry', () => {
    expect(createStorybookConfig().core.disableTelemetry).toBe(true);
  });
});
