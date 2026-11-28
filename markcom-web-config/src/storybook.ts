import { STORIES } from './config.js';

/** The part of Storybook's StorybookConfig this sets; a project checks it with `satisfies StorybookConfig`. */
type StorybookSettings = {
  stories: string[];
  addons: string[];
  framework: string;
  core: { disableTelemetry: boolean };
  features: { backgrounds: boolean };
};

export function createStorybookConfig(): StorybookSettings {
  return {
    stories: [STORIES],
    addons: ['@storybook/addon-a11y', '@storybook/addon-vitest', 'storybook-addon-pseudo-states'],
    framework: '@storybook/react-vite',
    core: { disableTelemetry: true },
    // The app's own page background (global.css) must be what axe and screenshots see.
    features: { backgrounds: false },
  };
}
