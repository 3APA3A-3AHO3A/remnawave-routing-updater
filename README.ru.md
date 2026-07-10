# Remnawave Routing Auto Updater

🌐 [English](./README.md) | **Русский**

[![CI](https://github.com/3APA3A-3AHO3A/remnawave-routing-updater/actions/workflows/ci.yml/badge.svg)](https://github.com/3APA3A-3AHO3A/remnawave-routing-updater/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12-blue)
![Docker](https://img.shields.io/badge/docker-ready-2496ED)
![License](https://img.shields.io/badge/license-MIT-green)

Автономный микросервис на Python + Docker для автоматического обновления баз роутинга (`geoip`, `geosite`) для клиентов **Happ** и **INCY** в панели управления [Remnawave](https://github.com/remnawave).

Скрипт использует **официальный API Remnawave** для обновления настроек подписки, что делает его максимально безопасным (никаких доступов к базе данных напрямую!). Логирование автоматически ротируется встроенными средствами Docker.

## Особенности
* Легковесный образ на базе `Alpine Linux`.
* Работа через официальный API Remnawave (по токену).
* Независимые тумблеры поддержки Happ и INCY.
* Автосоздание дефолтного правила INCY, если его нет.
* Автоматическая генерация файла `routing.json` для функции `autorouting` в INCY.
* Автоматический перезапрос при сетевых сбоях и корректное завершение по `docker stop`.

## 🧠 Как это работает

Может показаться, что скрипт скачивает и хранит базы у себя — это не так, и в этом вся элегантность.

Ссылки на `geoip.dat` и `geosite.dat` (например, репозиторий Loyalsoldier) прописаны прямо в шаблоне и **обновляются на стороне GitHub каждый день**. Клиенты Happ/INCY скачивают эти базы сами по ссылке — но только тогда, когда «видят», что конфигурация роутинга изменилась.

Задача скрипта — раз в заданный интервал подменять в конфигурации метку времени `LastUpdated`. Из-за этого меняется итоговая Base64-строка, клиент считает роутинг обновлённым и заново тянет свежие базы по ссылкам. То есть сервис ничего не хранит и не качает сам — он лишь «пинает» клиентов, чтобы те подтянули актуальные базы. Поэтому и нагрузки, и рисков минимум.

## ⚙️ Поддержка клиентов

Каждый тип клиента управляется своим тумблером в `.env` — включаете только то, что нужно.

**Happ (`ENABLE_HAPP`, включён по умолчанию).** Работает «из коробки»: скрипт пишет встроенное верхнеуровневое поле `happRouting`, поэтому клиенты Happ покрыты без дополнительной настройки. Если у вас есть правило ответа, в имени которого встречается `Happ`, его заголовок `routing` тоже обновится.

**INCY (`ENABLE_INCY`, выключен по умолчанию).** При включении скрипт обновляет заголовки `routing` и `autorouting` у **всех** правил, чьё имя похоже на `Incy` (без учёта регистра). Если такого правила нет — **создаёт дефолтное автоматически**, так что ручная настройка в панели необязательна. Вновь созданное правило использует `responseType: XRAY_BASE64` (ближе всего к дефолту панели); у уже существующих правил `responseType` не трогается вообще — тип для создаваемого правила меняется через `INCY_RESPONSE_TYPE`. Также для INCY нужен `AUTOROUTING_URL`, указывающий на ваш раздаваемый `routing.json` (см. раздел про reverse proxy ниже).

> 💡 Вы всё ещё можете заранее создать правило `Incy` вручную, если нужны кастомные условия срабатывания — скрипт заполнит и будет поддерживать его заголовки в актуальном состоянии. Структуру смотрите в [response_rules.example.json](./response_rules.example.json).

Для работы с API создайте токен в разделе **Настройки Remnawave → API токены** с правами `Read/Write` в разделе *Subscription Template* и скопируйте его в файл `.env`.

## 🔧 Переменные окружения

Все параметры задаются в файле `.env` (создаётся из `.env.example`):

| Переменная | Назначение | По умолчанию |
| --- | --- | --- |
| `PANEL_URL` | URL вашей панели (с `https://`, без слеша в конце) | `http://remnawave:3000` |
| `API_TOKEN` | Токен API Remnawave (обязательно) | — |
| `ENABLE_HAPP` | Включить поддержку Happ | `true` |
| `ENABLE_INCY` | Включить поддержку INCY (обновляет или создаёт правило Incy) | `false` |
| `INCY_RESPONSE_TYPE` | `responseType` только для автосоздаваемого правила INCY | `XRAY_BASE64` |
| `AUTOROUTING_URL` | Ссылка, по которой веб-сервер отдаёт `routing.json` (нужна для INCY) | `https://sub.your-domain.com/routing.json` |
| `UPDATE_INTERVAL_SECONDS` | Интервал обновления в секундах | `21600` (6 часов) |
| `REQUEST_TIMEOUT_SECONDS` | Таймаут HTTP-запросов к API | `30` |
| `RETRY_ATTEMPTS` | Число попыток при сетевой ошибке | `3` |
| `GEO_MIRROR_ENABLED` | Качать `geoip.dat` / `geosite.dat` на этот сервер | `false` |
| `GEOIP_URL` / `GEOSITE_URL` | Публичные URL `.dat`, которые уходят клиентам (пусто = дефолт из шаблона) | — |
| `GEOIP_SOURCE_URL` / `GEOSITE_SOURCE_URL` | Откуда сервер берёт базы | GitHub Loyalsoldier |
| `STAMP_MODE` | Метка `LastUpdated`: `interval` или `on_geo_change` | `interval` |

## 🚀 Установка и запуск

1. Склонируйте репозиторий:
   ```bash
   git clone https://github.com/3APA3A-3AHO3A/remnawave-routing-updater.git
   cd remnawave-routing-updater
   ```

2. Настройте конфигурацию:
   ```bash
   cp .env.example .env
   nano .env
   ```
   *Вставьте ваш `API_TOKEN`, укажите `PANEL_URL` и включите нужных клиентов (`ENABLE_HAPP` / `ENABLE_INCY`). Для INCY также задайте `AUTOROUTING_URL`.*

3. Создайте свой шаблон роутинга из примера и отредактируйте его:
   ```bash
   cp template.json my-template.json
   nano my-template.json
   ```
   Добавьте свои правила (`DirectSites`, базы обхода и т.д.). **Внимание:** поле `LastUpdated` добавлять не нужно — скрипт генерирует его сам.
   > 💡 Работаем именно с `my-template.json` (он не отслеживается git), чтобы ваши правки не конфликтовали при обновлении проекта через `git pull`. Файл `template.json` остаётся эталоном.

4. Запустите сервис:
   ```bash
   docker compose up -d --build
   ```

5. Просмотр логов:
   ```bash
   docker logs -f remna-routing-updater
   ```

## ✅ Проверка, что всё работает

В логах при успешном запуске вы увидите строки вида (сообщения выводятся на английском):
```
Service started. Interval: 21600 sec. | API: https://panel.your-domain.com | Happ: on, Incy: off
File /app/output/routing.json saved successfully.
✅ Remnawave database updated successfully! Happ: field set, 1 rule(s) updated
```
Файл `./output/routing.json` должен появиться на диске, а по адресу `https://sub.your-domain.com/routing.json` (после настройки reverse proxy ниже) отдаваться валидный JSON.

## 🐞 Troubleshooting

* **`CRITICAL ERROR: API_TOKEN is not set`** — не заполнен `API_TOKEN` в `.env`.
* **`CRITICAL ERROR: both ENABLE_HAPP and ENABLE_INCY are disabled`** — включите хотя бы одного клиента в `.env`.
* **`AUTOROUTING_URL not changed (using example.com)`** — для INCY укажите реальную ссылку в `.env`.
* **`API error: 'response' object not found`** — неверный `PANEL_URL` или токен без нужных прав (`Subscription Template: Read/Write`).
* **По ссылке `/routing.json` отдаётся HTML вместо JSON** — reverse proxy перехватывает запрос; проверьте настройку ниже (в Caddy обязателен блок `handle`, в Traefik нужен более высокий приоритет роутера).

## 🌐 Настройка веб-сервера (Reverse Proxy) для INCY

**Зачем это нужно?** Функция `autorouting` в клиенте INCY периодически скачивает JSON-файл по прямой ссылке. Скрипт генерирует свежий файл в локальную папку `./output`; ваш веб-сервер должен отдавать его по публичному адресу.

Отдавайте его с **домена вашей подписки** — клиент и так обновляет подписку по этому домену, значит и роутинг логично отдавать с того же хоста. Во всех примерах используется `https://sub.your-domain.com/routing.json`.

> ⚠️ **Публичный адрес обязан в точности совпадать с `AUTOROUTING_URL` в вашем `.env`,** иначе autorouting молча не заработает.

Примеры дополняют официальные схемы reverse proxy от Remnawave ([docs.rw/install/reverse-proxies](https://docs.rw/install/reverse-proxies/)), где документированы **Caddy, Nginx, Traefik и Angie**. Сам Remnawave должен жить на корне домена/сабдомена (работа на суб-пути не поддерживается), но отдавать один свой статический файл по пути `/routing.json` рядом с подпиской это не запрещает — приложение остаётся на `/`, мы лишь выделяем один путь. В каждом примере выставлен `Cache-Control: no-store`, чтобы клиент всегда получал свежий файл, и предполагается официальный контейнер подписки `remnawave-subscription-page` на порту `3010`.

> Используете HAProxy впереди? Обычно это TCP/port-балансировщик, а не HTTP-прокси — терминируйте HTTPS на Nginx/Caddy/Angie позади него и отдавайте `/routing.json` там, по подходящему примеру ниже.

После настройки проверьте:
```bash
curl -I https://sub.your-domain.com/routing.json
# Ожидаем: HTTP/2 200, Content-Type: application/json, Cache-Control: no-store
```

### 🟢 Nginx и 🟣 Angie

Angie — форк Nginx, поэтому один и тот же блок подходит обоим. Добавьте его в `server { ... }`, который обслуживает ваш домен подписки, *перед* основным `location /`.

#### Вариант А: прокси на сервере (без Docker)
```nginx
location = /routing.json {
    alias /opt/remnawave-routing-updater/output/routing.json;
    types { } default_type application/json;
    add_header Cache-Control "no-store" always;
}
```
*Примените:* `nginx -s reload` (или `angie -s reload`)

#### Вариант Б: прокси работает в Docker
1. Прокиньте папку `output` внутрь контейнера прокси (его `docker-compose.yml`):
```yaml
    volumes:
      - /opt/remnawave-routing-updater/output:/usr/share/nginx/routing_output:ro
```
*Пересоздайте:* `docker compose up -d`
2. Укажите в location внутренний путь:
```nginx
location = /routing.json {
    alias /usr/share/nginx/routing_output/routing.json;
    types { } default_type application/json;
    add_header Cache-Control "no-store" always;
}
```
*Примените:* перезагрузите контейнер прокси (`docker exec <proxy> nginx -s reload`).

---

### 🔵 Caddy

> ⚠️ **Важно:** оберните раздачу файла в блок `handle`, иначе `reverse_proxy` перехватит запрос.

#### Вариант А: Caddy на сервере (без Docker)
```caddyfile
https://sub.your-domain.com {
    # 1. Отдаём статический JSON
    @routing path /routing.json
    handle @routing {
        root * /opt/remnawave-routing-updater/output
        file_server
        header Content-Type application/json
        header Cache-Control no-store
    }

    # 2. Весь остальной трафик идёт на страницу подписки
    reverse_proxy * http://127.0.0.1:3010
}
```
*Примените:* `systemctl reload caddy`

#### Вариант Б: Caddy в Docker
1. Прокиньте папку `output` внутрь контейнера Caddy:
```yaml
    volumes:
      - /opt/remnawave-routing-updater/output:/usr/share/caddy/routing_output:ro
```
*Пересоздайте:* `docker compose up -d`
2. Укажите в `root *` внутренний путь, а прокси — на контейнер подписки по имени:
```caddyfile
https://sub.your-domain.com {
    @routing path /routing.json
    handle @routing {
        root * /usr/share/caddy/routing_output
        file_server
        header Content-Type application/json
        header Cache-Control no-store
    }

    reverse_proxy * http://remnawave-subscription-page:3010
}
```
*Примените:* `docker exec -w /etc/caddy имя_контейнера_caddy caddy reload`

---

### 🟠 Traefik

Traefik — это прокси, а не файловый сервер, поэтому запустите крошечный контейнер для раздачи файла в той же сети `remnawave-network` и направьте на него `/routing.json`:
```yaml
  routing-file:
    image: nginx:alpine
    container_name: remna-routing-file
    restart: unless-stopped
    networks:
      - remnawave-network
    volumes:
      - /opt/remnawave-routing-updater/output:/usr/share/nginx/html:ro
```
Официальная схема Traefik у Remnawave использует **file-provider** (файл динамической конфигурации), поэтому добавьте роутер туда:
```yaml
http:
  routers:
    routing-json:
      rule: "Host(`sub.your-domain.com`) && Path(`/routing.json`)"
      entryPoints:
        - https
      service: routing-json
      priority: 1000          # выигрываем у роутера подписки на этом пути
      tls:
        certResolver: letsencrypt
      middlewares:
        - routing-nostore
  services:
    routing-json:
      loadBalancer:
        servers:
          - url: "http://remna-routing-file:80"
  middlewares:
    routing-nostore:
      headers:
        customResponseHeaders:
          Cache-Control: "no-store"
```
Подставьте свои `entryPoints`/`certResolver` из `traefik.yml`. *Пересоздайте:* `docker compose up -d`

> Если ваш Traefik использует провайдер Docker-лейблов, вместо YAML выше повесьте эквивалентные лейблы на сервис `routing-file`: `...routers.routing-json.rule`, `...priority=1000`, `...service=routing-json`, `...loadbalancer.server.port=80` и middleware `routing-nostore`.

## 🗺️ Зеркало гео-баз (для регионов, где заблокирован GitHub)

Клиенты Happ/INCY качают `geoip.dat` / `geosite.dat` по ссылкам из шаблона
(`Geoipurl` / `Geositeurl`) — по умолчанию с GitHub. В России эти загрузки с GitHub часто
не проходят, и роутинг на клиенте ломается. Сервис умеет зеркалить обе базы на ваш сервер
(рядом с `routing.json`) и отдавать клиентам ссылку на ваш домен.

**Как это работает.** Каждый цикл сервис скачивает базы из upstream (GitHub доступен с
большинства серверов) условным запросом — если файл не менялся, приходит `304` и скачивание
пропускается. Запись атомарная, поэтому реверс-прокси никогда не отдаст недописанный файл.
Клиент всё равно качает **полный** файл и режет его локально (`UseChunkFiles`), так что вам
нужно хостить всего **два статических файла** — без чанк-манифестов и особых имён.

**Включение** в `.env`:
```dotenv
GEO_MIRROR_ENABLED=true
GEOIP_URL=https://sub.your-domain.com/geoip.dat
GEOSITE_URL=https://sub.your-domain.com/geosite.dat
```
`GEOIP_URL` / `GEOSITE_URL` — это то, что получают клиенты; оставьте пустыми, чтобы сохранить
дефолт из шаблона (GitHub). `template.json` держите указывающим на GitHub, чтобы не-РУ
установки работали из коробки — переключение целиком в `.env`.

### Раздача `.dat`-файлов

Базы ложатся в тот же каталог `./output`, что и `routing.json`, поэтому вы просто дополняете
[настройку реверс-прокси выше](#-настройка-веб-сервера-reverse-proxy-для-incy) двумя файлами.
В отличие от `routing.json` они меняются редко, так что их можно кэшировать.

**Nginx и Angie** — рядом с location для `/routing.json`:
```nginx
location ~ ^/(geoip|geosite)\.dat$ {
    root /opt/remnawave-routing-updater/output;   # или смонтированный путь в Docker
    default_type application/octet-stream;
    add_header Cache-Control "public, max-age=86400";
    try_files $uri =404;
}
```

**Caddy** — ещё один `handle` в том же блоке сайта:
```caddyfile
@geo path /geoip.dat /geosite.dat
handle @geo {
    root * /opt/remnawave-routing-updater/output   # или смонтированный путь в Docker
    file_server
    header Content-Type application/octet-stream
    header Cache-Control "public, max-age=86400"
}
```

**Traefik** — контейнер `remna-routing-file` (nginx) уже отдаёт каталог `./output`, поэтому
достаточно расширить правило роутера, добавив базы:
```yaml
rule: "Host(`sub.your-domain.com`) && (Path(`/routing.json`) || Path(`/geoip.dat`) || Path(`/geosite.dat`))"
```

Проверка (лучше изнутри России):
```bash
curl -I https://sub.your-domain.com/geoip.dat
# Ожидаем: HTTP/2 200, Content-Type: application/octet-stream, Content-Length в несколько МБ
```

### Обновлять метку только при изменении базы (опционально)

По умолчанию (`STAMP_MODE=interval`) метка `LastUpdated` — которая говорит клиентам перекачать
гео-файлы — растёт каждый цикл. При включённом зеркале можно переключиться на
`STAMP_MODE=on_geo_change`: метка меняется (и панель патчится) **только когда база в upstream
реально обновилась**. Факт изменения определяется бесплатно из условного запроса зеркала,
поэтому можно снизить `UPDATE_INTERVAL_SECONDS` для более частой проверки, не переписывая
панель и не дёргая клиентов на каждом цикле. Один интервал покрывает обе задачи — отдельная
переменная для опроса не нужна.

## 📄 Лицензия

Проект распространяется под лицензией MIT — см. файл [LICENSE](./LICENSE).
