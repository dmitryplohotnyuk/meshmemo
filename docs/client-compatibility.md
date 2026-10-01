# Клиентская совместимость: iOS в приоритете

Проверено 2026-09-25. Пользователь выбрал **сначала iOS**, целевая установленная
версия **2.7.22 (2395)**. Android-first не принят; возможность Android beta
зафиксирована только как результат исследования.

После TCP-проверки пользователь подтвердил: **только App Store**, без собственных
iOS-сборок, TestFlight и патчей приложения. Приоритет iOS сохраняется.

## Матрица

| Клиент | Наблюдение | Статус для нового outer ID + original_id |
| --- | --- | --- |
| Android v2.8.1, стабильный GitHub release | S&F handler сохраняет внешний ID | Не подходит по проверенным исходникам |
| Android v2.8.2-open.4, опубликованный prerelease от 23 сентября | Handler подставляет original_id; MeshDataHandler проверяет ID и отправителя | Кандидат; hardware NOT RUN, отложен |
| Android snapshot от 25 сентября | Та же нормализация | Development snapshot; не заменяет стабильную версию |
| iOS v2.7.21, последний найденный GitHub release/tag | Распаковка текста без подстановки original_id; запись/дедупликация по packet.id | Не подходит по проверенным исходникам |
| iOS main, commit 6f3ee55…, marketing version 2.7.23 | Такое же поведение ID | Не подходит по проверенному пути; не бинарник пользователя |
| **iOS 2.7.22 (2395)** | Пользователь проверил TCP-сценарий: LIVE 1→2→3, OFFLINE 1→2; автор и канал верны | **FAIL дедупликации на целевом бинарнике**; radio NOT RUN |

GitHub `releases/latest` не равен последнему App Store бинарнику. Поиск тега
v2.7.22 завершился HTTP 422; в списке тегов такого тега не найдено. Тег Current
указывает на апрельский commit и не идентифицирует сентябрьскую сборку. История
проекта содержит переход на marketing version 2.7.22 от 1 сентября, но это
само по себе не привязывает build 2395 к конкретному commit. Не переносить
результат анализа main или v2.7.21 на этот бинарник как доказанный факт.

## Доказательства и ограничения

- [Android опубликованный beta release](https://github.com/meshtastic/Meshtastic-Android/releases/tag/v2.8.2-open.4)
- [Android handler, строки 200–216](https://github.com/meshtastic/Meshtastic-Android/blob/7161b1bda118aa42c1034d190f0399b62b1441f7/core/data/src/commonMain/kotlin/org/meshtastic/core/data/manager/StoreForwardPacketHandlerImpl.kt#L200-L216)
- [Android проверка дублей, строки 476–482](https://github.com/meshtastic/Meshtastic-Android/blob/7161b1bda118aa42c1034d190f0399b62b1441f7/core/data/src/commonMain/kotlin/org/meshtastic/core/data/manager/MeshDataHandlerImpl.kt#L476-L482)
- [iOS main: распаковка, поиск и запись](https://github.com/meshtastic/Meshtastic-Apple/blob/6f3ee55bc7c9ff9b2d6f0c64b23de05ddeeaae21/Meshtastic/Helpers/MeshPackets.swift#L1856-L1916)
- [Apple Lookup API, Украина](https://itunes.apple.com/lookup?id=1586432531&country=ua)
- [Apple Lookup API, США](https://itunes.apple.com/lookup?id=1586432531&country=us)

Commit hashes, даты, URL и SHA-256 файлов сохранены в
[client-compatibility-snapshot.json](client-compatibility-snapshot.json).
Полные скачанные исходники остались в игнорируемом `.build/client-audit`.
Android upstream имеет тесты original_id; они прочитаны, но здесь не запускались.
Агент не устанавливал мобильные бинарники. Пользователь выполнил TCP-проверку
на своём iPhone с установленной версией 2.7.22 (2395).

## Следующее действие для iOS

Выполнен [изолированный TCP-тест](ios-client-probe.md) непосредственно на
2.7.22 (2395): при новых внешних ID появились дубли LIVE и OFFLINE. Он отделяет
поведение приложения от шифрования, радио и прошивки. Точный commit бинарника
по-прежнему не установлен, но отрицательный результат этого сценария наблюдался
непосредственно. Firmware остаётся в diagnostics profile 0, REPLAY выключен.

Выбранная безопасная схема не выполняет требование отсутствия дублей на этой
iOS-версии. Для неё нужна поддержка original_id в совместимом обновлении iOS
из App Store. Собственная тестовая сборка исключена пользователем. Патч одной серверной ноды
не меняет обработчик идентичности сообщений в уже установленном приложении.
Патчи мобильного клиента и клиентских нод не разрешены и не применялись.
Другая серверная схема может рассматриваться только с сохранением исходных
требований; её совместимость и безопасность пока не подтверждены.
