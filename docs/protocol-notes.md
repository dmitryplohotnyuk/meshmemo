# Исследование совместимости Meshtastic Store & Forward v1

Актуальная совместимость сервера 0.1.0a8 и переносимого USF2 описана в
[firmware-compatibility.md](firmware-compatibility.md). Ниже сохранено исходное
исследование и его исторические ограничения.

Дата проверки: **2026-09-25**. Метод: чтение официальных исходников,
protobuf-схем и обработчиков клиентов по фиксированным commit hashes.
Аппаратные тесты не выполнялись; приложение не реализовывалось.

Дополнение этапа реализации: USB diagnostics profile 0 и Python-пакет уже
созданы. В предложенном stable replay с исходными sender/ID выявлен
[повтор AES-CTR nonce](replay-security.md). Этот профиль заблокирован;
исторические выводы ниже не являются разрешением включить его.

## Решение

Обновление после исследования: 2026-09-25 пользователь выбрал патч только
серверной USB-ноды — [ADR 0001](adr/0001-patched-usb-node.md). Ниже сохраняется
вывод о стандартной firmware; он не запрещает согласованную разработку патча.
Подключённая нода проверена: [hardware-inventory.md](hardware-inventory.md).

**No-go для исходной архитектуры ТЗ: Linux + стандартный USB Client API +
неизменённая обычная Meshtastic-нода не сохраняют исходного sender при replay.**

Это ограничение находится в firmware, а не в Python-библиотеке. Установка
другого `from` в protobuf, вызов приватного `_sendPacket()` или отправка
`ToRadio` напрямую не обходят его. При неизменных ограничениях ТЗ нужно
остановиться до реализации сервера. Остальные функции приложения технически
не устраняют этот блокер.

Независимо от USB-блокера обнаружено расхождение replay identity между
release/development firmware и мобильными клиентами. Формулировка
«актуальный S&F v1» недостаточна: нужна совместимая матрица версий.

## Проверенные версии

Ветки зафиксированы на момент исследования. GitHub `releases/latest` —
опубликованный релиз, выбранный GitHub; это не доказательство версии,
доступной каждому пользователю в App Store/Google Play или установленной на устройстве.

| Репозиторий | Ref | Commit |
| --- | --- | --- |
| firmware | develop | `f90b48ea6cda35b5f6fdd4cd659498d28d8bd153` |
| firmware | v2.7.26.54e0d8d | `54e0d8d0ab2ff56b3a9ce967e53f79e49af560fb` |
| protobufs | master | `51028ca5a6945c76d3977c2bb803f9947d319ac5` |
| python | master | `be366660828b5a54469e703209a10aa954927791` |
| python | 2.7.11 | `19d066970e652a5a72a18718149b638e3473a6eb` |
| Meshtastic-Apple | main | `6f3ee55bc7c9ff9b2d6f0c64b23de05ddeeaae21` |
| Meshtastic-Apple | v2.7.21 | `4ea817379c4d70075c3c5b8cc0cecee7938a23bd` |
| Meshtastic-Android | main | `ecf0b1283b8dd21200d3083c930537fd52c92709` |
| Meshtastic-Android | v2.8.1 | `7c6a6cc195a2248cd50ed7f2395451cabcd93fdc` |

Машиночитаемый список изученных файлов, immutable URLs и SHA-256 находится
в [upstream-snapshot.json](upstream-snapshot.json). Эти refs — исследовательский
снимок независимых проектов, а не lockfile протестированного стека. Совместимость
generated protobuf конкретного Python wheel с выбранной firmware ещё не проверялась.

## Доказательство ограничения отправителя

1. Штатный сервер в `StoreForwardModule::preparePayload()` записывает в
   `MeshPacket.from` автора сохранённого сообщения. Затем вызывает
   `MeshService::sendToMesh()`, минуя вход Client API. Это верно для
   [release][fw-sf-release] и [develop][fw-sf].
2. USB Client API проходит через `PhoneAPI::handleToRadio()` →
   `handleToRadioPacket()` → `MeshService::handleToRadio()`.
   В последнем методе `p.from = 0` выполняется перед отправкой.
   Проверено в [develop, строки 289–338][fw-usb] и
   [release, строки 179–216][fw-usb-release].
3. В [Router::send()][fw-router] `p->from = getFrom(p)` превращает нулевой
   sender в ID локальной USB-ноды перед радио-передачей.
4. [StoreAndForward protobuf][proto-sf] содержит текст и `original_id`, но
   не содержит отдельного original sender. Клиенты получают автора из
   внешнего `MeshPacket.from` / производного `DataPacket.from`:
   [iOS][ios-text], [Android][android-sf].

Пример: сообщение `(from=A, id=X)` хранится на Linux. Host собирает replay
`(from=A, to=C, port=65)`. После штатного USB пути по радио уходит пакет
`(from=USB_NODE, to=C, port=65)`. Клиент C не может восстановить A из
S&F payload. Условие теста A «sender отображается как A» нарушается.

В develop есть `MESHTASTIC_ENABLE_FRAME_INJECTION` и в Portduino — путь
`SIMULATOR_APP`. Это специальные RX/simulation механизмы, не штатная
возможность передачи replay через обычную USB-ноду. Они не приняты как
решение и не проверялись на оборудовании. Транспорт TCP также не является
решением: замена serial framing не меняет `MeshService::handleToRadio()`.

## Wire contract и различия identity

Port: `STORE_FORWARD_APP = 65`, см. [portnums.proto][proto-ports].
Payload: сериализованный `meshtastic.StoreAndForward` внутри
`MeshPacket.decoded.payload`. Это не обычный `sendText()`.

| Поле | Назначение |
| --- | --- |
| `rr` | Тип request/response |
| `stats` / `history` / `heartbeat` / `text` | Взаимоисключающие варианты payload |
| `original_id` | Исходный packet ID в текущей master-схеме, поле 6 |
| Внешний `from` | Исходный автор replay-текста; для control — сервер |
| Внешний `to` | Клиент, запросивший replay по mesh |
| Внешний `channel` | Индекс канала в decoded Client API; в радио-форме используется hash |
| Внешний `id` | Зависит от поколения реализации, см. ниже |

### Два поведения внутри S&F v1

| Реализация | ID replay по радио | Отправитель |
| --- | --- | --- |
| Firmware release v2.7.26 | `p->id = stored.id`; поле `original_id` не заполняется | `stored.from` |
| Firmware develop | Новый ID из `allocDataPacket()`, `sf.original_id = stored.id` | `stored.from` |
| Firmware develop, `local=true` | Исходный ID, обычный `TEXT_MESSAGE_APP` | `stored.from` |

Источники: [release preparePayload][fw-sf-release], [develop preparePayload][fw-sf].
Локальный `getForPhone()`/`local=true` выдаёт историю подключённому к самому
S&F-серверу клиенту. Это другой маршрут, его успех не доказывает replay по LoRa.

### Мобильные клиенты

- **iOS main и v2.7.21:** обработчик `routerTextBroadcast/Direct` передаёт
  внешний packet в `textMessageAppPacket`. Текст распаковывается, broadcast
  попадает в channel chat, автор берётся из `packet.from`, а дедупликация и
  сохранение используют `packet.id`. Прочитанные пути не подставляют
  `StoreAndForward.originalID` вместо ID. См. [dispatch main][ios-dispatch],
  [ingestion main][ios-text], [dispatch release][ios-dispatch-release],
  [ingestion release][ios-text-release].
- **Android main:** для `ROUTER_TEXT_*` ненулевой `original_id` подставляется
  в `DataPacket.id`; при отсутствии используется header ID. Broadcast
  destination восстанавливается, sender остаётся из внешнего packet.
  См. [StoreForwardPacketHandlerImpl][android-sf].
- **Android v2.8.1:** тот же путь распаковывает текст и broadcast destination,
  но сохраняет внешний ID; подстановки `original_id` нет.
  См. [release handler][android-sf-release].

**Вывод из кода:** develop replay с новым outer ID не обеспечивает live/replay
dedupe в проверенном iOS и Android release. Android main содержит необходимую
нормализацию ID, но это не результат hardware test и не исправление USB sender.
Повторная выдача с прежним outer ID тоже не универсальный обход: firmware
имеет radio duplicate cache по sender/ID, поэтому отдельно проверяется
достижимость offline-клиента через промежуточные ноды, уже видевшие оригинал.
См. [PacketHistory][fw-history] и [FloodingRouter][fw-flood].

## Семантика запросов и состояния

Ниже — наблюдения за [StoreForwardModule.cpp][fw-sf], а не новая спецификация.

| Событие | Наблюдаемое поведение |
| --- | --- |
| Idle + `CLIENT_HISTORY` (65) | Проверка busy/default channel, вычисление выборки, отправка `ROUTER_HISTORY` (6), затем replay |
| История непустая | Установка `busy`, `busyTo`; выдача по таймеру при разрешённом airtime |
| Нет доступного следующего packet | Сброс `requestCount` и `busy` |
| `CLIENT_ABORT` (106) / `CLIENT_ERROR` (64) от активного клиента | Сброс active replay; от другого клиента replay не отменяется |
| `CLIENT_PING` (67) | `ROUTER_PONG` (4) |
| `CLIENT_PONG` (68) | Дополнительная выдача не запускается |
| `CLIENT_STATS` (66) | `ROUTER_STATS` (7), а при busy — `ROUTER_BUSY` (5) |
| Heartbeat enabled, idle, interval elapsed, airtime allowed | `ROUTER_HEARTBEAT` (2), broadcast, `secondary=0` |
| History request при busy/default channel | Текстовая ошибка; это не тот же ответ, что busy на stats |

`ROUTER_PING=3`, `ROUTER_ERROR=1`, `ROUTER_TEXT_DIRECT=8`,
`ROUTER_TEXT_BROADCAST=9`; `UNSET=0`. DM-вариант существует в протоколе,
но не входит в функциональность проекта по ТЗ.

### Window, cursor и limit

- Request `history.window` — минуты. При отсутствии/нуле используется default.
- Response `history.window` — миллисекунды (`secAgo * 1000`), клиент firmware
  делит его на 60000; Android handler также трактует как milliseconds.
- `stats.return_window` — минуты. Нельзя задавать общую единицу всем полям `window`.
- Фильтр истории: `stored.time > now - seconds`, автор не равен requester,
  destination broadcast либо requester; обход в порядке хранения.
- `history_messages` в response ограничивается `historyReturnMax`.
- `lastRequest` — серверный cursor по node number. Переданный клиентом
  `history.last_request` в проверенном `CLIENT_HISTORY` handler не применяется.
  Response сообщает текущий cursor до выдачи. Это не per-recipient delivery receipt.
- Указанный клиентом ненулевой window не ограничивается явно
  `historyReturnWindow` в проверенном handler, несмотря на формулировки комментариев.
- Server cursor продвигается в `preparePayload` до доказанной доставки.
  Ни курсор, ни отсутствие ACK не подтверждают получение клиентом.

### Defaults и обнаруженные края

Из [StoreForwardModule.h][fw-sf-header]: максимум 25 сообщений,
window 240 минут, интервал пакетов 5000 ms, heartbeat 900 секунд,
heartbeat выключен по умолчанию. Retention 30 дней и window 1440 минут
в исходном ТЗ — пример конфигурации приложения, не эти upstream defaults.

`runOnce()` выдаёт только пока `requestCount < historyReturnMax`; при достижении
лимита в прочитанной ветке нет явного перехода обратно в idle. Это выглядит
как дефект state machine, а не контракт, который следует воспроизводить.
Нужны отдельные проверки ровно N и N+1 сообщений, busy/abort и завершения сессии.

## Каналы, время и payload

**Каналы.** Request отклоняется на `channels.isDefaultChannel(mp.channel)`.
Это проверка default name/PSK по [Channels.cpp][fw-channels], а не запрет
любого Primary channel. В `getNumAvailablePackets`/`preparePayload` нет
фильтра по каналу запроса; replay сохраняет канал каждого исходного сообщения.
Control `sendMessage` не копирует channel из request явно. Поэтому полноценную
изоляцию истории по каналам и discovery на Secondary нельзя объявить готовыми
по одному чтению протокола. Политика allowed channels должна применяться и
к сохранению, и к выборке, без выдачи истории другой конфигурации канала.

**Время.** Upstream хранит время приёма сервером, а не timestamp создания текста
на исходном устройстве. `MeshPacket.rx_time` — локальная metadata,
она не передаётся по радио; см. [mesh.proto][proto-mesh] и
[RadioInterface::beginSending][fw-radio]. USB путь также переставляет время
приёма. В S&F v1 text payload нет original timestamp. Поэтому точную исходную
дату на удалённом телефоне обещать нельзя; проверять нужно критерий ТЗ
«приемлемо соответствует штатному S&F» и порядок фактической выдачи.

**Размер.** `DATA_PAYLOAD_LEN=233` в текущей mesh.proto. Обёртка S&F добавляет
protobuf overhead к исходному тексту; сохранённый текст предельной длины не
обязательно помещается в replay. Нельзя молча обрезать или вводить собственную
фрагментацию. Это отдельный edge case и условие выбора поддержанного профиля.

**Идентичность хранения.** По mesh.proto ID уникален только в контексте sender
и ограниченного периода. `UNIQUE(packet_id)` недостаточен, как и безусловное
вечное подавление одинаковых sender/ID при unlimited retention. Нужно
проектировать channel scope/configuration epoch, collision handling и
idempotency отдельно от short-lived mesh duplicate cache.

## Что позволяет Python API

[SerialInterface][py-serial] реализует официальный serial transport;
собственный framing не требуется. [MeshInterface][py-mesh]:

- выдаёт события `meshtastic.receive...`, decoded payload и исходный protobuf
  в `packet["raw"]`; это подходит для приёма и сохранения channel history;
- `sendData` поддерживает port/channel и создаёт новый packet ID;
- `_sendPacket` сохраняет ненулевой ID, но это приватный метод, а firmware
  всё равно заменяет sender;
- отправка корректного control protobuf на port 65 возможна по формату API,
  но discovery/обратный ответ ещё требуют проверки на устройстве.

Не считать значение `from` в объекте, возвращённом Python, доказательством
того, что оно сохранилось в эфире. Проверять нужно входящий пакет на другой ноде.
Reconnect, жизненный цикл subscriptions и bounded очереди проектируются на
уровне приложения после решения основной архитектуры.

## Минимальные варианты дальнейшего решения

| Вариант | Что сохраняет | Что меняет / чего не решает |
| --- | --- | --- |
| Штатный S&F на поддерживаемой ноде, Linux как архив и админка | Официальный firmware путь формирования replay | Источником replay становится память ноды; Linux SQLite не заменяет её. Disk-backed S&F из ТЗ не выполнен, dedupe требует проверки версий |
| Ограниченное расширение firmware серверной USB-ноды | Возможность оставить мобильные клиенты штатными и хранить историю на Linux | Нужен согласованный firmware/API путь передачи replay с original sender; меняет ограничение «обычная немодифицированная USB-нода». Один патч sender не решает расхождение client IDs |
| Linux meshtasticd/Portduino с прямым поддерживаемым radio interface | Перенос native firmware пути на Linux | Меняет подключение оборудования; интеграция disk persistence и клиентская совместимость требуют отдельного исследования. Не заявляется готовым решением |
| Сохранить исходные ограничения и ждать подходящего upstream API/клиентов | Полностью сохраняет ТЗ | Реализация основного replay остаётся заблокирована |

Пользователем выбран вариант расширения firmware серверной USB-ноды; он пока
не реализован. Новый BBS,
S&F++, spoofing node configuration и изменения официальных мобильных приложений
не предлагаются как скрытая замена требованиям.

## Проверки и остающиеся ограничения

Прочитаны исходники пути USB → router → радио, native replay, protobuf,
Python send/receive и mobile text ingestion. Статический анализ устанавливает
блокер sender и различия ID; он не подтверждает радиодоставку и UI behaviour.

После первоначального исследования выполнено USB metadata чтение через
Python SDK 2.7.11: T-Beam S3 Core на firmware 2.7.26.54e0d8d.
Не выполнены: replay по LoRa, тесты A/B/C, проверка разных моделей радио,
сборка firmware/mobile apps и проверка patched binary.
Все replay hardware results пока **NOT RUN**. Процедура:
[hardware-acceptance.md](hardware-acceptance.md).

## Источники

Ссылки ведут на зафиксированные commits; копии upstream-кода в проект не включены.

[fw-usb]: https://github.com/meshtastic/firmware/blob/f90b48ea6cda35b5f6fdd4cd659498d28d8bd153/src/mesh/MeshService.cpp#L289-L338
[fw-usb-release]: https://github.com/meshtastic/firmware/blob/54e0d8d0ab2ff56b3a9ce967e53f79e49af560fb/src/mesh/MeshService.cpp#L179-L216
[fw-sf]: https://github.com/meshtastic/firmware/blob/f90b48ea6cda35b5f6fdd4cd659498d28d8bd153/src/modules/StoreForwardModule.cpp
[fw-sf-release]: https://github.com/meshtastic/firmware/blob/54e0d8d0ab2ff56b3a9ce967e53f79e49af560fb/src/modules/StoreForwardModule.cpp#L240-L297
[fw-sf-header]: https://github.com/meshtastic/firmware/blob/f90b48ea6cda35b5f6fdd4cd659498d28d8bd153/src/modules/StoreForwardModule.h
[fw-router]: https://github.com/meshtastic/firmware/blob/f90b48ea6cda35b5f6fdd4cd659498d28d8bd153/src/mesh/Router.cpp#L521-L525
[fw-history]: https://github.com/meshtastic/firmware/blob/f90b48ea6cda35b5f6fdd4cd659498d28d8bd153/src/mesh/PacketHistory.cpp#L65-L107
[fw-flood]: https://github.com/meshtastic/firmware/blob/f90b48ea6cda35b5f6fdd4cd659498d28d8bd153/src/mesh/FloodingRouter.cpp#L28-L60
[fw-channels]: https://github.com/meshtastic/firmware/blob/f90b48ea6cda35b5f6fdd4cd659498d28d8bd153/src/mesh/Channels.cpp#L442-L453
[fw-radio]: https://github.com/meshtastic/firmware/blob/f90b48ea6cda35b5f6fdd4cd659498d28d8bd153/src/mesh/RadioInterface.cpp#L1515-L1543
[proto-sf]: https://github.com/meshtastic/protobufs/blob/51028ca5a6945c76d3977c2bb803f9947d319ac5/meshtastic/storeforward.proto
[proto-ports]: https://github.com/meshtastic/protobufs/blob/51028ca5a6945c76d3977c2bb803f9947d319ac5/meshtastic/portnums.proto
[proto-mesh]: https://github.com/meshtastic/protobufs/blob/51028ca5a6945c76d3977c2bb803f9947d319ac5/meshtastic/mesh.proto#L1843-L1910
[py-mesh]: https://github.com/meshtastic/python/blob/be366660828b5a54469e703209a10aa954927791/meshtastic/mesh_interface.py
[py-serial]: https://github.com/meshtastic/python/blob/be366660828b5a54469e703209a10aa954927791/meshtastic/serial_interface.py
[ios-dispatch]: https://github.com/meshtastic/Meshtastic-Apple/blob/6f3ee55bc7c9ff9b2d6f0c64b23de05ddeeaae21/Meshtastic/Accessory/Accessory%20Manager/AccessoryManager%2BFromRadio.swift#L621-L642
[ios-text]: https://github.com/meshtastic/Meshtastic-Apple/blob/6f3ee55bc7c9ff9b2d6f0c64b23de05ddeeaae21/Meshtastic/Helpers/MeshPackets.swift#L1833-L1970
[ios-dispatch-release]: https://github.com/meshtastic/Meshtastic-Apple/blob/4ea817379c4d70075c3c5b8cc0cecee7938a23bd/Meshtastic/Accessory/Accessory%20Manager/AccessoryManager%2BFromRadio.swift#L540-L562
[ios-text-release]: https://github.com/meshtastic/Meshtastic-Apple/blob/4ea817379c4d70075c3c5b8cc0cecee7938a23bd/Meshtastic/Helpers/MeshPackets.swift#L1710-L1790
[android-sf]: https://github.com/meshtastic/Meshtastic-Android/blob/ecf0b1283b8dd21200d3083c930537fd52c92709/core/data/src/commonMain/kotlin/org/meshtastic/core/data/manager/StoreForwardPacketHandlerImpl.kt#L201-L216
[android-sf-release]: https://github.com/meshtastic/Meshtastic-Android/blob/7c6a6cc195a2248cd50ed7f2395451cabcd93fdc/core/data/src/commonMain/kotlin/org/meshtastic/core/data/manager/StoreForwardPacketHandlerImpl.kt#L201-L206
