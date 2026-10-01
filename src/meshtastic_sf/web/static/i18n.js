"use strict";
// Explicit UI keys only. Channel names, sender names and chat contents are never translated.
window.I18n = (() => {
  const supported = ['ru', 'uk', 'en'];
  const locales = {ru: 'ru-RU', uk: 'uk-UA', en: 'en-GB'};
  const catalogs = new Map();
  let language = 'ru', dictionary = {}, revision = 0;
  function t(key, values = {}) {
    const message = dictionary[key] ?? key;
    return typeof message === 'string' ? message.replace(/\{(\w+)\}/g, (match, name) => String(values[name] ?? match)) : key;
  }
  function applyStatic() {
    document.documentElement.lang = language;
    document.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n); });
    for (const attr of ['title', 'aria-label', 'placeholder']) {
      document.querySelectorAll(`[data-i18n-${attr}]`).forEach(el => el.setAttribute(attr, t(el.getAttribute(`data-i18n-${attr}`))));
    }
    document.getElementById('language').value = language;
  }
  async function setLanguage(next, persist = true) {
    if (!supported.includes(next)) next = 'en';
    const request = ++revision;
    if (!catalogs.has(next)) {
      const response = await fetch(`/static/locales/${next}.json`);
      if (!response.ok) throw new Error('Language catalog unavailable');
      catalogs.set(next, await response.json());
    }
    if (request !== revision) return;
    language = next; dictionary = catalogs.get(next);
    if (persist) { try { localStorage.setItem('meshmemo-language', next); } catch {} }
    applyStatic();
    document.dispatchEvent(new CustomEvent('languagechange'));
  }
  function server(message) {
    if (!message) return '';
    const history = /^Запрос истории принят: (\d+) сообщений$/.exec(message);
    if (history) return t('Запрос истории принят: {count} сообщений', {count: number(history[1])});
    const cleanup = /^Автоочистка: удалено (\d+) записей$/.exec(message);
    if (cleanup) return t('Автоочистка: удалено {count} записей', {count: number(cleanup[1])});
    return t(message);
  }
  function number(n) { return Number(n || 0).toLocaleString(locales[language]); }
  function count(n) {
    const form = new Intl.PluralRules(locales[language]).select(n);
    return (dictionary.message_count?.[form] ?? dictionary.message_count?.other ?? '{count}').replace('{count}', number(n));
  }
  let preferred;
  try { preferred = localStorage.getItem('meshmemo-language'); } catch {}
  if (!supported.includes(preferred)) preferred = (navigator.languages || [navigator.language]).map(l => l.toLowerCase().split('-')[0]).find(l => supported.includes(l)) || 'en';
  const ready = setLanguage(preferred, false).catch(() => { applyStatic(); });
  return {t, server, number, count, setLanguage, ready, get language() {return language;}, get locale() {return locales[language];}};
})();
