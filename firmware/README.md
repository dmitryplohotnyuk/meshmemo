# Firmware серверной USB-ноды

Цель пользовательской сборки: T-Beam S3 Core с прежними UA22/Cyrillic изменениями
и USB bridge. Текущая установленная сборка — профиль 1/3. Выдача по умолчанию выключена;
на испытательном сервере оператор включил её для проверки `/history`.
Используется новый transport ID и `original_id`; ограничения описаны в
[выдаче истории](../docs/history-replay.md). Диагностический профиль 0 сохранён.

База, SHA-256 и исторические ограничения: [upstream.json](upstream.json).
Решение: [ADR 0001](../docs/adr/0001-patched-usb-node.md).
Проверенные прежние изменения: [отчёт](../docs/inherited-firmware-changes.md).

`patches/0001-inherited-ua22-cyrillic-windows.patch` — точная копия ранее
выпущенного combined patch. Применяется к чистому commit
`54e0d8d0ab2ff56b3a9ce967e53f79e49af560fb`, а не к уже изменённому checkout.
`protocol/0001-usb-sf-field.patch` применяется отдельно к pinned protobufs.
`patches/0002-usb-diagnostics.patch` применяется затем к firmware. Он содержит
generated bindings и USB-only handshake с кешированием ответа на повтор команды.
В диагностическом профиле 0 REPLAY всегда возвращает DISABLED и не обращается
к радио-очереди. Для выдачи истории нужен профиль 1: добавьте `--replay`
при подготовке checkout, как показано ниже.

Patch включает custom UA22 policy, OLED_UA и Windows build options; это
пользовательский профиль, не универсальный default публичного проекта.
Исходники Meshtastic и условия их распространения берутся из pinned upstream;
этот каталог не меняет лицензию upstream-кода.

Бинарники, backup flash, реальные настройки и ключи сюда не копировались.
При сборке проверять budget приложения под фактическую разметку:
в старой установке после UA22+Cyrillic оставалось 16 256 байт.
Перед обновлением заново проверить активный раздел и подготовить app-only artifact.
Стандартный factory image нельзя считать совместимым с сохранением старой разметки.

## Подготовка и сборка

```sh
python scripts/prepare-firmware.py --profile inherited-ua22 --replay
```

Профиль требуется указать явно: UA22 не является универсальным default.
Скрипт создаёт `.build/firmware`, фиксирует оба commit и проверяет патчи перед
применением. Существующие каталоги не заменяет. Для локальных зеркал доступны
`--firmware-source` и `--protobuf-source`.

На Windows используйте установленный PlatformIO:

```powershell
./scripts/build-firmware.ps1 -Python '<PlatformIO venv>/Scripts/python.exe' -PlatformioCore '<PlatformIO core directory>'
```

Скрипт временно использует свободные Q:/R: для коротких путей, сохраняет лог в
`.build/firmware-build.log` и проверяет app против исторического лимита 0x250000.
Это не заменяет проверку живой разметки перед прошивкой. App-only бинарник:
`.build/firmware/.pio/build/tbeam-s3-core/firmware-tbeam-s3-core-2.7.26.bin`.
Автоматически созданные factory/LittleFS образы не использовать для обновления
имеющегося устройства.

При нехватке app-раздела разрешено отдельным последующим патчем отключить OLED_UA.
Исходный inherited patch не менять; UTF-8 в данных сохраняется.

## Offline C++ тесты

Для нового кандидата replay подготовьте checkout с `--replay` (либо новый
`--destination`). Он применяет `0003-usb-replay.patch`, затем `0004-usb-poll.patch`
`0005-usb-screen-timeout.patch` и `0006-server-channels.patch`, после чего копирует `firmware/replay/UsbSf*`
в mesh sources. Профиль 1/revision 3 сохраняет новый
outer ID и original_id и добавляет шифрованные ответы серверных каналов; диагностический профиль 0 по-прежнему запрещает replay.
Патч 0004 сохраняет частый опрос активной TinyUSB protobuf-сессии: проверка
HWCDC иначе приводила к 20-секундным задержкам на native USB этой платы.
Предыдущий образ 1/2 был прошит app-only 2026-09-30, HELLO проверен. Его радиоприёмка
частично выполнена: команда `/history 6` и один текст получены клиентской
нодой по радио в нужном вторичном канале. Приёмка в приложении iOS, дубли
и многопереходная доставка остаются открытыми. Размер 2 410 288 байт, запас 14 544 байта в живом разделе
0x250000. SHA-256: `ef8215ecf986713763895224f079072745303cdf81abce65be7e378e0654c461`.
Каналы, ключи, local/module config и идентификатор ноды сохранены. Подробности:
[выдача истории](../docs/history-replay.md). Native harness для replay требует
checkout с этим патчем.

Windows с MSVC:

```powershell
./scripts/test-firmware-native.ps1 -VcVars '<Visual Studio>/VC/Auxiliary/Build/vcvars64.bat'
```

Linux:

```sh
g++ -std=c++17 -Wall -Wextra -Werror -I .build/firmware/src/mesh tests/native/bridge_harness.cpp .build/firmware/src/mesh/UsbSfBridge.cpp -o .build/bridge_harness
USF_BRIDGE_HARNESS=.build/bridge_harness python -m pytest
```

Обычный pytest без `USF_BRIDGE_HARNESS` пропускает C++ integration-тесты;
CI собирает harness и запускает их. Это не hardware acceptance.

## USB screen-timeout candidate

Кандидат от 2026-09-30 добавляет патч
[`0005-usb-screen-timeout.patch`](patches/0005-usb-screen-timeout.patch).
Он прошит app-only 2026-09-30 после полной резервной копии и проверки живой
разметки. Хеш записанных данных проверен, конфигурация и каналы совпали с копией
до обновления, USB HELLO профиля 1/2 прошёл. Оператор подтвердил работу экрана
после проверки таймаута и пробуждения кнопкой. USB HELLO проходил до 92-й секунды
проверки; затем оператор сам отключил кабель. Радио при погашенном экране после
этой прошивки повторно не проверялось.
Приведённые выше результаты радио относятся к предыдущему образу.
Новая сборка занимает 2 410 576 байт, запас в разделе 0x250000 — 14 256 байт.
Кириллица и прежний пользовательский профиль сохранены; USB-протокол остаётся 1/2.
Хеши и результаты проверок: `usb_screen_timeout_candidate` в
[upstream.json](upstream.json).

При активном USB экран использует `display.screen_on_secs`, оставаясь в состоянии
SERIAL: процессор продолжает обслуживать соединение. Heartbeat и пакеты API
не перезапускают таймер. Кнопка/локальный ввод включают экран и запускают таймер
заново. Значение 0 использует стандартный таймаут OLED; для E-Ink сохраняется
отключение таймера при 0. UINT32_MAX сохраняет постоянно включённый экран.

После сборки доступны проверки реального PowerFSM и его scheduler wrapper
с имитацией аппаратных вызовов. Требуется установленная сборкой библиотека
arduino-fsm. В Developer Command Prompt MSVC:

```sh
python scripts/check-screen-timeout.py --cxx cl
```

В Linux с подготовленными PlatformIO dependencies:

```sh
python scripts/check-screen-timeout.py --cxx g++
```

Проверяются таймаут, отсутствие сна CPU, USB heartbeat, однократное выключение,
кнопка/ввод, специальные значения, переполнение millis, отсутствие экрана,
отключение USB и shutdown. Оба варианта OLED/E-Ink прошли на хосте; применение
всей последовательности патчей к чистой базе воспроизводит собранный PowerFSM.
Это не проверка реального дисплея или передачи данных по USB.

Перед аппаратной приёмкой перепроверить модель и разметку подключённой ноды,
сохранить backup и обновить только app-раздел, без factory/LittleFS образов.
Затем с работающим сервером дождаться таймаута экрана, проверить пробуждение
кнопкой, приём/сохранение сообщения и выдачу истории при погашенном экране.
Готовый локальный app-only образ и manifest хранятся в игнорируемом
`dist/firmware/`; автоматической прошивки сборочный скрипт не выполняет.

## Server-channel firmware (profile 1/revision 3)

`prepare-firmware.py --replay` now also applies
[`0006-server-channels.patch`](patches/0006-server-channels.patch), then copies
the updated USB radio adapter. Operation 5 accepts bounded host-encrypted unicast
replies with a live LoRa configuration digest. Keys stay on the server. Unlike
operations 2/4, the firmware cannot inspect or independently restrict the encrypted
application payload: trust is placed in the attached host service. This operation
is USB-only and is not exposed to BLE/Wi-Fi/radio callers. Airtime and queue
checks still apply. See [server channels](../docs/server-channels.md).

The revision 3 image was flashed app-only on 2026-09-30 after a complete 8 MiB
backup and live partition/OTA checks. The write hash matched; local/module
configuration and all channels were preserved. USB profile 1/revision 3 HELLO
passed during a 75-second connection check. The display timeout remains 60 seconds;
the physical display was not observed in this check. Server-channel radio replay
and administrator DM acceptance remain pending. The previously accepted revision 2
screen-timeout binary is retained for rollback.
