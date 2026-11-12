import i18next from 'i18next';
import { initReactI18next } from 'react-i18next';

/**
 * A Vitest setup file for sites: react-i18next's t() returns each key unchanged (i18next's
 * `cimode`), so unit tests assert locale keys, never wording that may be reworded.
 * Use: `setupFiles: ['@markcom/i18n/vitest-setup']`.
 */
await i18next.createInstance().use(initReactI18next).init({ lng: 'cimode' });
