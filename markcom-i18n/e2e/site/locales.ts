import { LocaleSet } from '../../src/locales.ts';
import en from './locales/en.json' with { type: 'json' };
import ga from './locales/ga.json' with { type: 'json' };

export const locales: LocaleSet<'en' | 'ga', typeof en> = new LocaleSet({ en, ga }, 'en');
