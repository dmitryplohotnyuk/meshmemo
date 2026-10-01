const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../../src/meshtastic_sf/web/static');
function context(preferred = 'ru', languages = ['uk-UA']) {
  const storage = new Map(preferred ? [['meshmemo-language', preferred]] : []);
  const picker = {value:''};
  const context = {window:{}, Intl, Map, CustomEvent: class {}, navigator:{languages},
    localStorage:{getItem:key=>storage.get(key),setItem:(key,value)=>storage.set(key,value)},
    document:{documentElement:{},querySelectorAll:()=>[],getElementById:()=>picker,dispatchEvent:()=>{}},
    fetch:async url=>({ok:true,json:async()=>JSON.parse(fs.readFileSync(path.join(root,url.replace('/static/','')),'utf8'))})};
  vm.runInNewContext(fs.readFileSync(path.join(root,'i18n.js'),'utf8'), context);
  return {...context, storage, api:context.window.I18n};
}
test('locale preference, plurals, interpolation and server activity',async()=>{
  const ctx=context(); await ctx.api.ready;
  assert.equal(ctx.api.count(1),'1 сообщение'); assert.equal(ctx.api.count(2),'2 сообщения');
  assert.equal(ctx.api.count(5),'5 сообщений'); assert.equal(ctx.api.count(21),'21 сообщение');
  await ctx.api.setLanguage('uk');
  assert.equal(ctx.document.documentElement.lang,'uk');
  assert.equal(ctx.api.count(5),'5 повідомлень');
  assert.equal(ctx.api.t('Текущий порт: {port}',{port:'COM7'}),'Поточний порт: COM7');
  await ctx.api.setLanguage('en');
  assert.equal(ctx.api.count(1),'1 message'); assert.equal(ctx.api.count(2),'2 messages');
  assert.equal(ctx.api.server('Автоочистка: удалено 12 записей'),'Automatic cleanup: 12 records deleted');
  assert.equal(ctx.api.server('Настройки сервера сохранены'),'Server settings saved');
  assert.equal(ctx.storage.get('meshmemo-language'),'en');
  assert.equal(ctx.api.t('<script>untrusted</script>'),'<script>untrusted</script>');
});
test('browser locale fallback and storage failure do not break initialization',async()=>{
  const ctx=context(null,['fr-FR','uk-UA']); await ctx.api.ready;
  assert.equal(ctx.api.language,'uk');
  ctx.localStorage.setItem=()=>{throw new Error('storage blocked');};
  await ctx.api.setLanguage('en'); assert.equal(ctx.api.language,'en');
  const unsupported=context(null,['fr-FR']); await unsupported.api.ready;
  assert.equal(unsupported.api.language,'en');
});
