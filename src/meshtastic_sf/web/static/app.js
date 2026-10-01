"use strict";
(async () => {
await I18n.ready;
const t = I18n.t, serverText = I18n.server;
const $ = id => document.getElementById(id);
const csrf = document.querySelector('meta[name="csrf-token"]').content;
const fmt = I18n.number;
const date = n => n ? new Date(n * 1000).toLocaleString(I18n.locale) : "—";
const node = (tag, text, cls) => { const el = document.createElement(tag); if (text !== undefined) el.textContent = text; if (cls) el.className = cls; return el; };
let selected = null, query = "", rows = [], historyMode = false, policy = null, polling = false, generation = 0;
let connectionLoaded = false, settingsDirty = false, connectionDirty = false;
let channelSignature = "", messageSignature = "";
const messageCount = I18n.count;
let lastStatus = null, lastChannels = [], lastPorts = [], lastSync = null, settingsSaving = false, serverUnavailable = false;
const replayFields = {'replay-limit':'replay_limit','replay-window':'replay_window_minutes','replay-max-window':'replay_max_window_minutes','replay-interval':'replay_interval_seconds','replay-cooldown':'replay_cooldown_seconds'};
async function api(path, body) {
  let response;
  try { response = await fetch(path, body === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json", "X-CSRF-Token": csrf}, body: JSON.stringify(body)}); }
  catch { throw new Error(t("Сеть недоступна. Проверьте соединение с сервером.")); }
  if (!response.ok) { const error = await response.json().catch(() => ({})); throw new Error(typeof error.detail === "string" ? serverText(error.detail) : t(response.status === 422 ? "Некорректные настройки. Проверьте значения полей." : "Не удалось выполнить запрос")); }
  return response.json();
}
function notice(message) { $("notice").textContent = message || ""; $("notice").hidden = !message; }
function details(id, entries) { const el = $(id); el.replaceChildren(); for (const [label, value] of entries) el.append(node("dt", label), node("dd", value)); }
function renderStatus(data) {
  lastStatus = data;
  const r = data.runtime, d = data.database, s = data.settings;
  const labels = {offline: t("Не подключено"), waiting:t("Ожидание ноды"), connecting: t("Подключаемся…"), connected: s.capture_enabled ? t("Подключено · приём") : t("Подключено · запись на паузе"), error: t("Ошибка подключения"), stopped: t("Сервер остановлен")};
  $("connection").textContent = labels[r.connection] || r.connection;
  $("connection").className = "status " + r.connection;
  $("usb-tag").textContent = r.connection === "connected" ? t("Подключено") : t("Ожидание");
  $("stat-messages").textContent = fmt(d.messages);
  const size = d.database_bytes + d.wal_bytes;
  $("stat-size").textContent = size >= 1048576 ? (size / 1048576).toLocaleString(I18n.locale,{maximumFractionDigits:1}) + " " + t("МБ") : fmt(Math.ceil(size / 1024)) + " " + t("КБ");
  $("stat-duplicates").textContent = fmt(d.duplicates); $("stat-collisions").textContent = fmt(d.collisions);
  details("db-details", [[t("Первая запись"), date(d.oldest_at)], [t("Последняя запись"), date(d.latest_at)], [t("Автоудаление"), s.retention_days ? t("Старше {days} дней",{days:fmt(s.retention_days)}) : t("Выключено")]]);
  details("usb-details", [[t("Порт"), r.device || t("Не выбран")], [t("Прошивка"), r.firmware || "—"], [t("Последний пакет"), date(r.last_packet_at)], [t("Пакетов принято"), fmt(r.packets)], [t("Новых записей"), fmt(r.stored)], [t("Повторов"), fmt(r.duplicates)], [t("Вне условий архива"), fmt(r.excluded)], [t("Пропущено на паузе"), fmt(r.paused)], [t("Некорректных сообщений"), fmt(r.invalid)]]);
  $("capacity-label").textContent = `${fmt(d.messages)} / ${fmt(s.max_records)}`;
  $("capacity-progress").max = s.max_records; $("capacity-progress").value = d.messages;
  $("channel-policy").replaceChildren(...r.channels.map(c => node("p", `${c.name || t("Канал")} · ${c.eligible ? t("архивируется") : t("не архивируется: открытый канал")}`)));
  $("events").replaceChildren(...r.events.map(e => { const el = node("div", undefined, "event"); el.append(node("time", date(e.at)), node("span", serverText(e.message))); return el; }));
  $('port-status').textContent = labels[r.connection] || t('Проверяем подключение…');
  $('port-status').className = 'status ' + r.connection;
  $('port-current').textContent = r.device ? t('Текущий порт: {port}',{port:r.device}) + (r.firmware ? ' · '+t('Прошивка')+' '+r.firmware : '') : (serverText(r.connection_detail) || serverText(r.error) || t('Подключите ноду к USB и выберите способ подключения.'));
  if (!connectionLoaded) { connectionLoaded = true; $('connection-mode').value = data.connection.mode; loadPorts(data.connection.port).catch(e => $('connection-result').textContent=e.message); }
  const replayLabels = {disabled:t("Выключено"), idle:t("Ожидание запроса"), queued:t("Запрос в очереди"), sending:t("Передаём историю"), blocked:t("Выдача заблокирована"), disconnected:t("Нет подключения")};
  $("replay-state").textContent = `${s.replay_enabled ? (replayLabels[r.replay.state] || r.replay.state) : t("Выключено")} · ${t("Передано ноде сообщений истории: {count}",{count:fmt(r.replay.replayed)})}${r.replay.error ? " · " + serverText(r.replay.error) : ""}`;
  if (!policy) fillSettings(s);
  policy = s;
  notice(serverText(r.error) || (d.messages >= s.max_records ? t("Достигнут лимит архива. Увеличьте лимит в настройках, чтобы продолжить запись.") : ""));
}
function setDirty(dirty) {
  settingsDirty = dirty;
  $("settings-result").textContent = dirty ? t("Есть несохранённые изменения") : t("Все изменения сохранены");
  $("settings-result").classList.toggle("dirty", dirty);
  $("save-settings").disabled = $("reset-settings").disabled = !dirty || settingsSaving;
  $("save-settings").textContent = settingsSaving ? t("Сохранение…") : t("Сохранить настройки");
}
function updateDiscoveryInput() { $("replay-heartbeat").disabled = !$("replay-heartbeat-enabled").checked; }
function fillSettings(s) {
  $("max-records").value=s.max_records; $("retention-days").value=s.retention_days; $("dedupe-minutes").value=s.dedupe_seconds/60;
  $("capture-enabled").checked=s.capture_enabled; $("replay-enabled").checked=s.replay_enabled;
  for (const [id,key] of Object.entries(replayFields)) $(id).value=id === 'replay-max-window' ? s[key]/60 : s[key];
  $('replay-heartbeat').value=s.replay_heartbeat_seconds/60; $('replay-heartbeat-enabled').checked=s.replay_heartbeat_enabled;
  updateDiscoveryInput();
}
async function loadPorts(preferred = $('serial-port').value) {
  const ports = await api('/api/ports');
  lastPorts = ports;
  renderPorts(ports, preferred);
}
function renderPorts(ports, preferred = $('serial-port').value) {
  const select = $('serial-port'); select.replaceChildren();
  if (!ports.length) { const option=node('option',t('Нет доступных портов')); option.value=''; select.append(option); }
  for (const p of ports) { const option=node('option',`${p.device} — ${p.description}`); option.value=p.device; select.append(option); }
  if (preferred && !ports.some(p=>p.device===preferred)) { const option=node('option',t('{port} — недоступен',{port:preferred})); option.value=preferred; select.append(option); }
  if (preferred) select.value=preferred;
  select.disabled=$('connection-mode').value!=='manual';
  $('port-hint').textContent=ports.length ? t('Найдено устройств: {count}',{count:fmt(ports.length)}) : t('Подключите ноду и обновите список.');
}
$('connection-mode').onchange=()=>{$('serial-port').disabled=$('connection-mode').value!=='manual';};
$('connection-form').onchange=()=>{ connectionDirty=true; $('reset-connection').hidden=false; $('connection-result').textContent=t('Изменения ещё не применены'); };
$('reset-connection').onclick=()=>{ if (!lastStatus) return; $('connection-mode').value=lastStatus.connection.mode; renderPorts(lastPorts,lastStatus.connection.port); connectionDirty=false; $('reset-connection').hidden=true; $('connection-result').textContent=''; };
$('settings-form').oninput=()=>{ setDirty(true); updateDiscoveryInput(); };
$('reset-settings').onclick=()=>{ if (policy) fillSettings(policy); setDirty(false); };
window.addEventListener('beforeunload',event=>{ if(settingsDirty || connectionDirty){event.preventDefault();event.returnValue='';} });
$('refresh-ports').onclick=async()=>{ $('refresh-ports').disabled=true; try { await loadPorts(); } catch(e) { $('connection-result').textContent=e.message; } finally { $('refresh-ports').disabled=false; } };
$('connection-form').onsubmit=async event=>{ event.preventDefault(); const button=event.submitter; button.disabled=true; try { await api('/api/connection',{mode:$('connection-mode').value,port:$('serial-port').value}); connectionDirty=false; $('reset-connection').hidden=true; $('connection-result').textContent=t('Настройки подключения сохранены'); await refresh(); } catch(e) { $('connection-result').textContent=e.message; } finally {button.disabled=false;} };
function renderChannels(channels) {
  lastChannels = channels;
  $("channel-count").textContent = channels.length;
  if (!selected && channels.length) selected = (channels.find(c => c.count > 0) || channels[0]).scope;
  const signature = JSON.stringify([selected, channels]);
  if (signature === channelSignature) return;
  channelSignature = signature;
  $("channels").replaceChildren(...channels.map(c => {
    const button = node("button", undefined, "channel-button" + (selected === c.scope ? " active" : ""));
    const label = node("span"); label.append(node("strong", c.name || t('Канал {index}',{index:c.channel_index})), node("small", messageCount(c.count)));
    button.append(node("span", "#", "channel-symbol"), label);
    button.setAttribute("aria-pressed", String(selected === c.scope));
    button.title = c.last_at ? t('Последнее сообщение: {date}',{date:date(c.last_at)}) : t('Пока нет сообщений');
    button.onclick = () => { selected = c.scope; query = ""; rows = []; historyMode = false; $("search").value = ""; generation++; renderChannels(channels); loadMessages(false, true).catch(e => notice(e.message)); };
    return button;
  }));
  const channel = channels.find(c => c.scope === selected);
  $("search").disabled = !selected;
  if (channel) { $("chat-title").textContent = channel.name; $("chat-detail").textContent = messageCount(channel.count); }
}
function renderMessages(scrollBottom = false, older = false) {
  const signature = JSON.stringify([selected, query, historyMode, rows]);
  if (!scrollBottom && !older && signature === messageSignature) return;
  messageSignature = signature;
  const container = $("messages"), oldHeight = container.scrollHeight, oldTop = container.scrollTop;
  const atBottom = oldHeight - oldTop - container.clientHeight < 70;
  const elements = []; let previousDay = "";
  for (const m of rows) {
    const day = new Date(m.received_at * 1000).toLocaleDateString(I18n.locale, {day: "numeric", month: "long", year: "numeric"});
    if (day !== previousDay) { elements.push(node("div", day, "day-label")); previousDay = day; }
    const article = node("article", undefined, "message"), content = node("div", undefined, "message-content"), meta = node("div", undefined, "message-meta");
    const avatar = node("span", m.sender_name.slice(0, 2).toUpperCase(), "avatar"); avatar.title = m.sender_id;
    meta.append(node("strong", m.sender_name), node("time", new Date(m.received_at * 1000).toLocaleTimeString(I18n.locale, {hour: "2-digit", minute: "2-digit"})));
    meta.title = t('Получено {date}',{date:date(m.received_at)});
    content.append(meta, node("div", m.text, "bubble"));
    const tags = [];
    if (m.collision) tags.push(t("Вариант сообщения сохранён отдельно"));
    if (m.reply_id) tags.push(t('Ответ на сообщение'));
    if (tags.length) content.append(node("small", tags.join(" · "), "message-note"));
    article.append(avatar, content); elements.push(article);
  }
  if (!rows.length) { const empty = node("div", undefined, "empty"); empty.append(node("div", "⌁", "empty-icon"), node("h3", query ? t("Ничего не найдено") : t("Сообщений пока нет")), node("p", query ? t("Попробуйте другой текст поиска.") : t("Новые сообщения закрытого канала появятся здесь."))); elements.push(empty); }
  container.replaceChildren(...elements);
  if (older) container.scrollTop = oldTop + container.scrollHeight - oldHeight;
  else if (scrollBottom || atBottom) container.scrollTop = container.scrollHeight;
  else container.scrollTop = oldTop;
  $("message-count").textContent = t('Показано: {count}',{count:fmt(rows.length)}) + (query ? ' · '+t('поиск') : '');
  $("latest").hidden = $("history-paused").hidden = !historyMode;
  $("message-count").title = historyMode ? t("Показаны более ранние сообщения. Автообновление ленты приостановлено.") : "";
}
async function loadMessages(older = false, scrollBottom = false) {
  if (!selected) return;
  const scope = selected, token = generation, search = query;
  const params = new URLSearchParams({scope, q: search});
  if (older && rows.length) params.set("before", rows[0].row_id);
  const data = await api("/api/messages?" + params);
  if (scope !== selected || token !== generation || search !== query) return;
  rows = older ? [...data, ...rows] : data;
  if (older) historyMode = true;
  $("older").disabled = data.length < 100;
  renderMessages(scrollBottom, older);
}
async function refresh() {
  if (polling) return; polling = true;
  try { const [status, channels] = await Promise.all([api("/api/status"), api("/api/channels")]); serverUnavailable=false; renderStatus(status); renderChannels(channels); if (!historyMode) await loadMessages(); lastSync = new Date(); $("sync-status").textContent = t("Обновлено в {time}",{time:lastSync.toLocaleTimeString(I18n.locale)}); $("sync-status").classList.remove("error"); }
  catch (e) { serverUnavailable=true; notice(e.message + " " + t("Повторим подключение автоматически.")); $("connection").textContent = $("port-status").textContent = t("Сервер недоступен"); $("connection").className = $("port-status").className = "status error"; $("sync-status").textContent = t("Нет связи с сервером"); $("sync-status").classList.add("error"); }
  finally { polling = false; }
}
document.querySelectorAll("[data-view]").forEach(button => button.onclick = () => {
  document.querySelectorAll("[data-view]").forEach(b => { b.classList.toggle("active", b === button); if(b === button) b.setAttribute("aria-current","page"); else b.removeAttribute("aria-current"); });
  try { sessionStorage.setItem("meshmemo-view",button.dataset.view); } catch {}
  document.querySelectorAll(".view").forEach(v => v.hidden = v.id !== "view-" + button.dataset.view);
  $("crumb").textContent = {chats: t("Чаты"), catalog: t("Каналы сервера"), database: t("База данных"), settings: t("Настройки")}[button.dataset.view];
  window.scrollTo(0,0);
});
let searchTimer;
$("search").oninput = () => { clearTimeout(searchTimer); query = $("search").value; generation++; historyMode = false; searchTimer = setTimeout(() => loadMessages(false, true).catch(e => notice(e.message)), 300); };
$("older").onclick = async () => { $("older").disabled = true; generation++; historyMode = true; try { await loadMessages(true); } catch (e) { notice(e.message); $("older").disabled = false; } };
$("latest").onclick = () => { generation++; historyMode = false; loadMessages(false, true).catch(e => notice(e.message)); };
$("settings-form").onsubmit = async event => {
  event.preventDefault(); const button = event.submitter;
  const body = {max_records: Number($("max-records").value), retention_days: Number($("retention-days").value), dedupe_seconds: Math.round(Number($("dedupe-minutes").value) * 60), capture_enabled: $("capture-enabled").checked, replay_enabled: $("replay-enabled").checked};
  for (const [id,key] of Object.entries(replayFields)) body[key]=Number($(id).value);
  body.replay_heartbeat_enabled=$('replay-heartbeat-enabled').checked;
  body.replay_heartbeat_seconds=Math.round(Number($('replay-heartbeat').value)*60);
  const maximumMinutes = body.replay_max_window_minutes * 60;
  if (!Number.isFinite(maximumMinutes) || maximumMinutes < 1 || maximumMinutes > 10080 || Math.abs(maximumMinutes - Math.round(maximumMinutes)) > 1e-7) { $('settings-result').textContent=t('Укажите глубину в часах с точностью до целой минуты.'); return; }
  body.replay_max_window_minutes = Math.round(maximumMinutes);
  body.replay_window_minutes = Math.min(body.replay_window_minutes, body.replay_max_window_minutes);
  if (body.retention_days && policy && (!policy.retention_days || body.retention_days < policy.retention_days)) {
    if (!window.confirm(t('Сообщения старше {days} дней будут автоматически удаляться из базы. Продолжить?',{days:fmt(body.retention_days)}))) return;
    body.confirm_retention = true;
  }
  settingsSaving = true;
  const controls = [...$('settings-form').querySelectorAll('input,button')].map(el => [el,el.disabled]);
  controls.forEach(([el])=>{el.disabled=true;});
  button.textContent=t('Сохранение…');
  try { policy = await api("/api/settings", body); fillSettings(policy); setDirty(false); $("settings-result").textContent = t("Настройки сохранены"); await refresh(); }
  catch (e) { $("settings-result").textContent = e.message; }
  finally { settingsSaving=false; controls.forEach(([el,disabled])=>{el.disabled=disabled;}); updateDiscoveryInput(); button.disabled=$("reset-settings").disabled=!settingsDirty; button.textContent=t("Сохранить настройки"); }
};
$("integrity").onclick = async () => { $("integrity").disabled = true; try { const data = await api("/api/integrity", {}); $("integrity-result").textContent = data.result === "ok" ? t("Целостность в порядке") : t("Обнаружена ошибка базы"); } catch (e) { $("integrity-result").textContent = e.message; } finally { $("integrity").disabled = false; } };
$("backup").onclick = async () => {
  $("backup").disabled = true;
  try { const response = await fetch("/api/backup", {method: "POST", headers: {"X-CSRF-Token": csrf}}); if (!response.ok) throw new Error(t("Не удалось создать резервную копию")); const url = URL.createObjectURL(await response.blob()); const link = node("a"); link.href = url; link.download = `meshmemo-${new Date().toISOString().slice(0, 10)}.db`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
  catch (e) { notice(e.message); } finally { $("backup").disabled = false; }
};
try { const view = sessionStorage.getItem("meshmemo-view"); const button = [...document.querySelectorAll("[data-view]")].find(b => b.dataset.view === view); if (button) button.click(); } catch {}
refresh(); setInterval(refresh, 3000);
let catalogDirty = false, adminDirty = false;
$('catalog-form').oninput = () => catalogDirty = true;
$('channel-admin-form').oninput = () => adminDirty = true;
window.addEventListener('beforeunload', event => { if(catalogDirty || adminDirty) { event.preventDefault(); event.returnValue=''; } });
let catalogSaving=false;
function resetCatalog() {
  $('catalog-form').reset(); $('catalog-id').value=''; $('catalog-result').textContent='';
  $('catalog-key-hint').hidden=true;
  $('catalog-form-title').textContent=t('Добавить канал'); catalogDirty=false;
}
function openCatalog(entry=null) {
  resetCatalog();
  if(entry) {
    $('catalog-id').value=entry.id; $('catalog-name').value=entry.name;
    $('catalog-capture').checked=entry.capture; $('catalog-replay').checked=entry.replay;
    $('catalog-form-title').textContent=t('Редактировать канал'); $('catalog-key-hint').hidden=false;
  }
  $('catalog-dialog').showModal(); $('catalog-name').focus();
}
function closeCatalog() {
  if(catalogSaving) return;
  if(catalogDirty && !window.confirm(t('Закрыть без сохранения изменений?'))) return;
  $('catalog-dialog').close(); resetCatalog();
}
$('catalog-add').onclick=()=>openCatalog();
$('catalog-cancel').onclick=$('catalog-close').onclick=closeCatalog;
$('catalog-dialog').addEventListener('cancel',event=>{event.preventDefault();closeCatalog();});
const catalogTabs=[$('catalog-tab-list'),$('catalog-tab-admin')];
function selectCatalogTab(tab) {
  catalogTabs.forEach(item=>{
    item.setAttribute('aria-selected',String(item===tab)); item.tabIndex=item===tab?0:-1;
    $(item.getAttribute('aria-controls')).hidden=item!==tab;
  });
}
catalogTabs.forEach(tab=>{
  tab.onclick=()=>selectCatalogTab(tab);
  tab.onkeydown=event=>{
    if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
    event.preventDefault();
    const next=event.key==='Home'?catalogTabs[0]:event.key==='End'?catalogTabs[1]:catalogTabs[1-catalogTabs.indexOf(tab)];
    selectCatalogTab(next); next.focus();
  };
});
async function loadCatalog() {
  const entries=await api('/api/channel-catalog');
  const rendered=entries.map(c => {
    const row=node('tr'); const name=node('th',c.name);name.scope='row';
    row.append(name,node('td',c.last_seen ? date(c.last_seen) : t('Пока нет сообщений'),'catalog-last-seen'));
    for(const field of ['capture','replay']) {
      const cell=node('td');cell.append(node('span',t(c[field]?'Включено':'Выключено'),'tag'+(c[field]?' catalog-enabled':'')));row.append(cell);
    }
    const actions=node('td');const edit=node('button',t('Редактировать'),'secondary');edit.type='button';edit.dataset.channelId=c.id;
    edit.setAttribute('aria-label',t('Редактировать {name}',{name:c.name}));edit.onclick=()=>openCatalog(c);
    actions.append(edit);row.append(actions);return row;
  });
  if(!rendered.length) {
    const row=node('tr'),cell=node('td',t('Каналов пока нет. Добавьте первый канал.'),'catalog-empty');cell.colSpan=5;row.append(cell);rendered.push(row);
  }
  $('catalog-list').replaceChildren(...rendered);
}
$('catalog-form').onsubmit=async event=>{
  event.preventDefault(); if(catalogSaving) return;
  catalogSaving=true;
  const controls=[...$('catalog-form').querySelectorAll('input,button')];
  controls.forEach(control=>control.disabled=true);
  try {
    const savedId=$('catalog-id').value;
    const link=$('catalog-link').value.trim();
    await api('/api/channel-catalog',{name:link?'':$('catalog-name').value,key:link?'':$('catalog-key').value.trim(),link,capture:$('catalog-capture').checked,replay:$('catalog-replay').checked,channel_id:$('catalog-id').value?Number($('catalog-id').value):null});
    $('catalog-dialog').close();resetCatalog(); $('catalog-feedback').textContent=t('Канал сохранён');await loadCatalog();
    const returnButton=savedId ? [...$('catalog-list').querySelectorAll('button')].find(b=>b.dataset.channelId===savedId) : $('catalog-add');
    if(returnButton) returnButton.focus();
  }catch(e){if($('catalog-dialog').open) $('catalog-result').textContent=e.message;else notice(e.message);}
  finally{catalogSaving=false;controls.forEach(control=>control.disabled=false);}
};
$('channel-admin-form').onsubmit=async event=>{
  event.preventDefault();const button=event.submitter;button.disabled=true;
  try{await api('/api/channel-admin',{enabled:$('channel-admin-enabled').checked,public_keys:$('channel-admin-keys').value.split(/\s+/).filter(Boolean)});adminDirty=false;$('channel-admin-result').textContent=t('Все изменения сохранены');}
  catch(e){$('channel-admin-result').textContent=e.message;}finally{button.disabled=false;}
};
async function loadAdminPolicy(){const p=await api('/api/channel-admin');$('channel-admin-enabled').checked=p.enabled;$('channel-admin-keys').value=p.public_keys.join('\n');}
loadCatalog().catch(e=>notice(e.message)); loadAdminPolicy().catch(e=>notice(e.message));
document.querySelector('[data-view="catalog"]').addEventListener('click',()=>loadCatalog().catch(e=>notice(e.message)));
document.addEventListener('languagechange',()=>{ $('catalog-result').textContent=$('catalog-feedback').textContent=$('channel-admin-result').textContent=''; $('catalog-form-title').textContent=t($('catalog-id').value?'Редактировать канал':'Добавить канал'); loadCatalog().catch(e=>notice(e.message)); });


document.addEventListener('languagechange', () => {
  channelSignature = messageSignature = '';
  const active = document.querySelector('[data-view].active').dataset.view;
  $('crumb').textContent = t({chats:'Чаты',catalog:'Каналы сервера',database:'База данных',settings:'Настройки'}[active]);
  if (lastStatus) renderStatus(lastStatus);
  renderChannels(lastChannels); renderMessages(); renderPorts(lastPorts);
  setDirty(settingsDirty);
  $('connection-result').textContent = connectionDirty ? t('Изменения ещё не применены') : '';
  $('integrity-result').textContent = '';
  if (serverUnavailable) {
    $('connection').textContent=$('port-status').textContent=t('Сервер недоступен');
    $('connection').className=$('port-status').className='status error';
    $('sync-status').textContent=t('Нет связи с сервером');
    notice(t('Сеть недоступна. Проверьте соединение с сервером.')+' '+t('Повторим подключение автоматически.'));
  } else if (lastSync) $('sync-status').textContent = t('Обновлено в {time}',{time:lastSync.toLocaleTimeString(I18n.locale)});
});
$('language').onchange = async () => {
  const previous = I18n.language;
  $('language').disabled = true;
  try { await I18n.setLanguage($('language').value); }
  catch { $('language').value = previous; notice(t('Не удалось загрузить язык. Повторите попытку.')); }
  finally { $('language').disabled = false; }
};
})();
