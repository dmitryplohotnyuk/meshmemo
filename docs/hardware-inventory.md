# Проверенная серверная нода

Обновление 2026-09-30: установлен app-only профиль 1/2 с USB polling fix,
metadata version `2.7.26`. Живая разметка прочитана: app offset 0x10000,
размер 0x250000. Перед записью сохранена полная 8 MiB flash-копия в приватном
`data/`. Hash записи проверен esptool. HELLO со штатным таймаутом прошёл дважды
(2 и 1 секунда). Каналы/ключи, local/module config и node identity совпадают
с backup. Кириллица и UA22 сохранены. Radio replay не включался.
Ниже — исходное обследование до этой установки.

Дата: 2026-09-25. Устройство подключено к рабочему Windows ПК пользователя.
Модель получена от самой ноды, а не выведена только из USB VID/PID.

| Параметр | Наблюдаемое значение |
| --- | --- |
| Текущий serial port | `COM7` |
| Hardware model | `LILYGO_TBEAM_S3_CORE` |
| Hardware model number | `12` |
| Firmware | `2.7.26.54e0d8d` |
| Device role | `CLIENT` |
| Native S&F enabled | `false` |
| Native S&F is_server | `false` |
| Metadata Wi-Fi / Bluetooth | `true` / `true` |
| Metadata Ethernet | `false` |
| Точная PCB revision / радиочип | Не установлены через metadata |

Чтение выполнено официальным `meshtastic==2.7.11`, `SerialInterface`,
`noNodes=True`. SDK установлен в отдельную временную папку, не в окружение проекта.
Из handshake выведены только разрешённые поля модели, версии и состояния S&F.
Node IDs, PSK, private keys, channel URLs и содержимое сообщений в этот файл
не записывались. Соединение закрыто после чтения.

Первый диагностический скрипт завершился на неверном имени необязательного
metadata-поля; после исправления повторное чтение успешно. Настройки устройства
не менялись; прошивка, factory reset и тестовые радио-сообщения не выполнялись.
Это проверка USB-связи и metadata, не аппаратная приёмка replay.

Цель сборки `tbeam-s3-core` сверена с model 12 в
[upstream profile](https://github.com/meshtastic/firmware/blob/54e0d8d0ab2ff56b3a9ce967e53f79e49af560fb/variants/esp32s3/tbeam-s3-core/platformio.ini).
В upstream её display name — LILYGO T-Beam Supreme.
COM-номер относится к текущему ПК; Linux device path определяется отдельно.

## Уточнение по прежней пользовательской прошивке

Проверка the prior local firmware workspace выявила сборку на той же версии с UA22,
Cyrillic OLED и Windows build changes, а также отчёты её прежней установки.
Версия `2.7.26.54e0d8d` сохранялась в custom binary, поэтому metadata-чтение
выше не доказывает, что на ноде чистый upstream. Текущий app hash и partition
table в этой сессии не проверялись. Исторический app partition имеет размер
`0x250000`, а остаток после Cyrillic binary — 16 256 байт.
Подробнее: [учёт прежних изменений](inherited-firmware-changes.md).
