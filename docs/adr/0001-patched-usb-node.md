# ADR 0001 Патч серверной USB-ноды

> Историческое решение от 2026-09-25. Текущее состояние профиля 1, команды
> `/history` и аппаратных проверок см. в [контракте](../history-replay.md)
> и [статусе реализации](../implementation-status.md). Ниже сохранён ход решения.

Дата: 2026-09-25. Статус: **архитектурный вариант принят пользователем**.
Реализация патча и совместимость по радио пока не проверены.

Обновление: диагностическая часть USB-патча реализована, профиль 0 не передаёт
историю. Выявлен [криптографический блокер](../replay-security.md) прежнего
варианта с исходным outer ID. Решение о серверном патче сохраняется; этот
replay-профиль нельзя включать до разрешения блокера. При нехватке памяти
разрешено убрать только кириллицу с экрана, сохранив UTF-8 в данных.

## Решение и изменение ТЗ

Linux хранит историю в SQLite, обрабатывает S&F v1 и планирует выдачу.
Подключённая по USB серверная нода использует нашу сборку Meshtastic firmware
с ограниченным расширением локального API для replay. Официальные мобильные
приложения, клиентские ноды и промежуточные ноды остаются без модификаций.
На LoRa сохраняется штатный S&F v1, `STORE_FORWARD_APP` / port 65.

Уточнение после проверки iOS 2.7.22 (2395): пользователь требует **только App
Store**. Собственные мобильные сборки, TestFlight и изменения iOS-приложения
исключены. Приоритет — сначала iOS. Новый outer ID с original_id создаёт дубли
в проверенной версии; это остаётся блокером данного replay-профиля.

Это явное исключение из требования исходного ТЗ об обычной немодифицированной
серверной USB-ноде. Оно разрешено пользователем 2026-09-25. Остальные требования,
включая исходного отправителя, отсутствие дублей, disk persistence и hardware
acceptance, сохраняются. Исходный DOCX остаётся историческим документом;
при расхождении по серверной firmware действует этот ADR.

## База и оборудование

На подключённой ноде прочитаны через официальный API:

- `LILYGO_TBEAM_S3_CORE`, hardware model 12;
- firmware `2.7.26.54e0d8d`, роль `CLIENT`;
- встроенный S&F выключен, `is_server=false`.

Начальная база патча: upstream firmware tag `v2.7.26.54e0d8d`, commit
`54e0d8d0ab2ff56b3a9ce967e53f79e49af560fb`.
Дополнение после проверки прежнего проекта: поверх этой базы сохраняются
UA22, OLED_UA/исправление `Ґ/ґ` и Windows build workaround. Точная копия
baseline patch и hashes находятся в `firmware/`; подробности в
[inherited-firmware-changes.md](../inherited-firmware-changes.md).
Строка версии ноды не подтверждает отсутствие этих модификаций.
Цель PlatformIO: `tbeam-s3-core`. Она совпадает с model 12 в
[upstream platformio.ini][board]. Точную PCB revision и тип установленного
радиочипа metadata не подтвердили. Чтение устройства описано в
[hardware-inventory.md](../hardware-inventory.md).

## Граница патча

Расширение действует только на локальном serial API серверной сборки.
`SerialConsole` устанавливает `TYPE_SERIAL`; общий `PhoneAPI` обслуживает также
другие транспорты, поэтому простое удаление `p.from = 0` не является проектным
решением. См. [SerialConsole][serial] и [PhoneAPI][phone-header].

Предусмотреть отдельную явно включаемую возможность сборки, по умолчанию
выключенную. Для выбранной server build она включается явно. По BLE/TCP/HTTP,
по mesh и на обычных сборках расширение недоступно. `TYPE_SERIAL` различает
serial и сетевые API, но сам по себе не доказывает физический USB: для server
build проверить привязку к USB SerialConsole конкретной платы.

Локальный host имеет право предоставлять историю и исходного автора;
firmware не может криптографически доказать подлинность записи в Linux-БД.
Это часть модели доверия выделенного серверного устройства.

## Контракт локального API

До написания патча зафиксировать wire encoding расширения и generated bindings
в `firmware/protocol/`. Использовать существующий Meshtastic serial framing.
Названия операций ниже описывают контракт, а не уже существующие protobuf-поля.

1. **Capabilities:** host узнаёт версию расширения, build/base commit,
   доступный профиль replay, ограничения размера и состояние очереди.
   По одной строке firmware version наличие патча не угадывается.
2. **Submit replay:** отдельная локальная операция содержит исходные sender/ID,
   broadcast text, reply/emoji, локальный channel index, requester и request token.
   Wire field numbers/локальный discriminator должны быть проверены на коллизии
   с protobuf именно выбранной версии. Расширение не пересылается в mesh.
3. **Result:** accepted/rejected/queue-full с request token. Accepted означает
   принятие радио-очередью, а не доставку или создание bubble на телефоне.
4. **Cancel/session lifecycle:** host прекращает подачу при abort/disconnect;
   явно определить, как отменяются уже поставленные в очередь replay.

При отсутствии capabilities или несовместимой версии host не начинает replay.
Поддержка стандартных read/config операций и приёма пакетов сохраняется.
Адаптация Python API изолируется в transport adapter; не форкается всё приложение
и не пишется собственный serial framing. Точное место подключения generated
bindings к официальному SDK нужно проверить при реализации PoC.

## Проверка replay в firmware

Допустима только выдача channel history `ROUTER_TEXT_BROADCAST`. DM/PKI,
encrypted opaque injection, admin packets и произвольные application ports
не принимаются этой операцией.

Firmware проверяет валидность protobuf, размер, ненулевые original sender/ID,
unicast requester, активный разрешённый channel и допустимость параметров.
Параметры routing/priority/hop/ack нормализуются; host не задаёт произвольные
`relay_node`/`next_hop`. Control replies и heartbeat исходят от серверной ноды
через обычный путь. Встроенный S&F server остаётся выключенным, чтобы два
сервера не отвечали одновременно на один запрос.

Replay формируется в firmware и передаётся в штатный TX path, сохраняющий
исходного автора, как native StoreForwardModule. Он не инжектируется как
принятый по радио пакет. Airtime/региональные ограничения и bounded queue
сохраняются; pacing Linux не заменяет ограничения радио.

## Идентичность и повторные команды

Начальный профиль PoC — **release v1 с исходным outer packet ID**:
`from=original_sender`, `id=original_id`, `to=requester`, исходный канал,
port 65, `ROUTER_TEXT_BROADCAST`. Это соответствует проверенной release firmware
и обработке ID в проверенных iOS/Android releases. Это кандидат для испытаний,
не обещание совместимости. Новый outer ID с `original_id` не включать по умолчанию:
проверенные iOS и Android release не нормализуют его.

В [PhoneAPI release][phone-source] `wasSeenRecently` подавляет повтор по одному
`packet.id` ещё до `MeshService`. Новая операция должна иметь **собственный request
token**, отличный от identity сообщения. Повтор того же token в пределах
ограниченной session cache не создаёт вторую постановку; тот же token с иными
данными отклоняется. Новый token позволяет повторный запрос, включая выдачу
того же оригинала другому клиенту. Не отключать duplicate checks глобально.

Обычный SDK также ведёт очередь по packet ID; операция и подтверждение должны
коррелироваться по request token, не конфликтуя с исходными IDs истории.
После reconnect capability/session handshake повторяется. Exactly-once
радиодоставка через рестарт устройства не обещается.

## Нерешённый риск multi-hop

Исходный outer ID нужен проверенным приложениям для dedupe, но промежуточная
нода могла уже видеть этот sender/ID и отбросить replay. Патч только S не меняет
duplicate cache на промежуточных устройствах. Поэтому tests A/B выполняются
сначала напрямую, затем с промежуточной нодой, которая видела оригинал.

Если multi-hop не проходит, фиксируется ограничение; автоматического перехода
на новый ID, модификации клиентских нод или объявления direct-only MVP нет.
Потребуется отдельное решение о матрице версий либо изменении охвата ТЗ.
Timestamp по радио также остаётся ограничением S&F v1, описанным в исследовании.

## Хранение и сопровождение патча

В публичном репозитории выделить `firmware/`: pin upstream commit, patch series,
описание локального протокола, build profiles, проверки применения и инструкции
build/rollback. Python-код остаётся в `src/meshtastic_sf/`.
Не копировать весь upstream в Python package. Checkout/toolchains и бинарники
сборки — вне исходников; releases содержат версию патча и checksum.

## Порядок реализации

1. Зафиксировать локальный wire contract и capability handshake.
2. Создать применяемый к pinned commit патч и тесты ограничения входов,
   token idempotency, разных requesters и непатченного режима.
3. Собрать `tbeam-s3-core`, записать версии toolchain/submodules и checksum.
   Сборка должна сохранять inherited features и помещаться в фактический
   app partition; по прежнему отчёту доступный резерв всего 16 256 байт.
4. Подготовить отдельные backup/rollback инструкции для прошивки устройства.
   Перепроверить прежнюю нестандартную разметку и app-only update; сохранить
   GPS disabled, owner, channels, keys и остальные настройки.
5. Выполнить patched C, A/B и multi-hop; затем развивать сервер по плану.

Принятие ADR разрешает работу над патчем. Оно не означает, что патч написан,
бинарник собран, устройство перепрошито или hardware acceptance пройдена.

[board]: https://github.com/meshtastic/firmware/blob/54e0d8d0ab2ff56b3a9ce967e53f79e49af560fb/variants/esp32s3/tbeam-s3-core/platformio.ini
[serial]: https://github.com/meshtastic/firmware/blob/54e0d8d0ab2ff56b3a9ce967e53f79e49af560fb/src/SerialConsole.cpp#L53-L58
[phone-header]: https://github.com/meshtastic/firmware/blob/54e0d8d0ab2ff56b3a9ce967e53f79e49af560fb/src/mesh/PhoneAPI.h
[phone-source]: https://github.com/meshtastic/firmware/blob/54e0d8d0ab2ff56b3a9ce967e53f79e49af560fb/src/mesh/PhoneAPI.cpp#L795-L825
