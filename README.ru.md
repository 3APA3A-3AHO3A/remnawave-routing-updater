# Remnawave Routing Auto Updater

🌐 [English](./README.md) | **Русский**

[![CI](https://github.com/3APA3A-3AHO3A/remnawave-routing-updater/actions/workflows/ci.yml/badge.svg)](https://github.com/3APA3A-3AHO3A/remnawave-routing-updater/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12-blue)
![Docker](https://img.shields.io/badge/docker-ready-2496ED)
![License](https://img.shields.io/badge/license-MIT-green)

Автономный микросервис на Python + Docker для автоматического обновления баз роутинга (`geoip`, `geosite`) для клиентов **Happ** и **INCY** в панели управления [Remnawave](https://github.com/remnawave).

Скрипт использует **официальный API Remnawave** для обновления настроек подписки, что делает его максимально безопасным (никаких доступов к базе данных напрямую!). Логирование автоматически ротируется встроенными средствами Docker.

## Оглавление

- [Особенности](#особенности)
- [Как это работает](#-как-это-работает)
- [Поддержка клиентов](#-поддержка-клиентов)
- [Переменные окружения](#-переменные-окружения)
- [Установка и запуск](#-установка-и-запуск)
- [Проверка, что всё работает](#-проверка-что-всё-работает)
- [Гео-базы (зеркало и обрезка)](#-гео-базы-зеркало-и-обрезка)
- [Настройка веб-сервера (Reverse Proxy)](#-настройка-веб-сервера-reverse-proxy)
- [Troubleshooting](#-troubleshooting)
- [Лицензия](#-лицензия)

## Особенности

**Ядро**
- Работает только через **официальный API Remnawave** (по токену) — без прямого доступа к БД.
- Легковесный образ на базе `Alpine Linux`; логи ротируются средствами Docker.
- Автоматический перезапрос при сетевых сбоях и корректное завершение по `docker stop`.
- Покрыт тестами `pytest` и CI на GitHub Actions (`ruff` + тесты).

**Поддержка клиентов**
- Независимые тумблеры **Happ** и **INCY** — включаете только нужное.
- Happ работает «из коробки» через встроенное поле `happRouting`.
- INCY: обновляет каждое правило с именем `Incy`, а если его нет — **создаёт автоматически**; генерирует `routing.json` для функции `autorouting`.

**Гео-базы (`geoip` / `geosite`)**
- По умолчанию ничего не хранит и не качает — лишь «пинает» клиентов подтянуть свежие базы по ссылкам из шаблона.
- **Своё зеркало** (`GEO_MIRROR_ENABLED`) — раздача баз с вашего домена для регионов, где заблокирован GitHub; условные `304`-запросы и атомарная запись.
- **Серверная обрезка** (`GEO_TRIM_ENABLED`) — в раздачу попадают только категории из шаблона, файлы ужимаются с ~10–17 МБ до КБ (серверный аналог `UseChunkFiles`).
- **Умная метка** (`STAMP_MODE=on_geo_change`) — бампить `LastUpdated` и патчить панель только когда база реально изменилась.

**Раздача**
- Готовые примеры reverse proxy для **Nginx / Angie, Caddy и Traefik** (варианты «на хосте» и «в Docker»).

## 🧠 Как это работает

По умолчанию скрипт не скачивает и не хранит базы у себя — и в этом вся элегантность.

Ссылки на `geoip.dat` и `geosite.dat` (например, репозиторий Loyalsoldier) прописаны прямо в шаблоне и **обновляются на стороне GitHub каждый день**. Клиенты Happ/INCY скачивают эти базы сами по ссылке — но только тогда, когда «видят», что конфигурация роутинга изменилась.

Задача скрипта — раз в заданный интервал подменять в конфигурации метку времени `LastUpdated`. Из-за этого меняется итоговая Base64-строка, клиент считает роутинг обновлённым и заново тянет свежие базы по ссылкам. То есть в этом режиме по умолчанию сервис ничего не качает и не хранит — он лишь «пинает» клиентов, чтобы те подтянули актуальные базы, а нагрузки и рисков минимум.

Это по умолчанию предполагает, что клиенты могут достучаться до ссылок с базами. Там, где GitHub заблокирован, — не могут; для этого случая сервис **опционально** может зеркалить базы у себя (и даже обрезать их), см. [Гео-базы](#-гео-базы-зеркало-и-обрезка).

## ⚙️ Поддержка клиентов

Каждый тип клиента управляется своим тумблером в `.env` — включаете только то, что нужно.

**Happ (`ENABLE_HAPP`, включён по умолчанию).** Работает «из коробки»: скрипт пишет встроенное верхнеуровневое поле `happRouting`, поэтому клиенты Happ покрыты без дополнительной настройки. Если у вас есть правило ответа, в имени которого встречается `Happ`, его заголовок `routing` тоже обновится.

**INCY (`ENABLE_INCY`, выключен по умолчанию).** При включении скрипт обновляет заголовки `routing` и `autorouting` у **всех** правил, чьё имя похоже на `Incy` (без учёта регистра). Если такого правила нет — **создаёт дефолтное автоматически**, так что ручная настройка в панели необязательна. Вновь созданное правило использует `responseType: XRAY_BASE64` (ближе всего к дефолту панели); у уже существующих правил `responseType` не трогается вообще — тип для создаваемого правила меняется через `INCY_RESPONSE_TYPE`. Для функции `autorouting` задайте `AUTOROUTING_URL`, указывающий на ваш раздаваемый `routing.json` (см. раздел про reverse proxy ниже). Он необязателен: если его не задать, INCY работает только на хэдере `routing` (как Happ) — хэдер `autorouting` вообще не добавляется, а не указывает на заглушку.

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
| `AUTOROUTING_URL` | Ссылка, по которой веб-сервер отдаёт `routing.json` (опционально; включает `autorouting` у INCY — без неё только `routing`) | `https://sub.your-domain.com/routing.json` |
| `UPDATE_INTERVAL_SECONDS` | Интервал обновления в секундах | `21600` (6 часов) |
| `REQUEST_TIMEOUT_SECONDS` | Таймаут HTTP-запросов к API | `30` |
| `RETRY_ATTEMPTS` | Число попыток при сетевой ошибке | `3` |
| `GEO_MIRROR_ENABLED` | Качать `geoip.dat` / `geosite.dat` на этот сервер | `false` |
| `GEOIP_URL` / `GEOSITE_URL` | Публичные URL `.dat`, которые уходят клиентам (пусто = дефолт из шаблона) | — |
| `GEOIP_SOURCE_URL` / `GEOSITE_SOURCE_URL` | Откуда сервер берёт базы | GitHub Loyalsoldier |
| `STAMP_MODE` | Метка `LastUpdated`: `interval` или `on_geo_change` | `interval` |
| `GEO_TRIM_ENABLED` | Отдавать только категории из шаблона (серверный `UseChunkFiles`) | `false` |

## 🚀 Установка и запуск

Сервис распространяется готовым образом в **GitHub Container Registry**, так что ничего клонировать и собирать не нужно — достаточно положить три файла в пустую папку и запустить.

1. Создайте папку и скачайте файлы:
   ```bash
   mkdir remnawave-routing-updater && cd remnawave-routing-updater
   curl -O https://raw.githubusercontent.com/3APA3A-3AHO3A/remnawave-routing-updater/master/docker-compose.yml
   curl -o .env https://raw.githubusercontent.com/3APA3A-3AHO3A/remnawave-routing-updater/master/.env.example
   curl -o my-template.json https://raw.githubusercontent.com/3APA3A-3AHO3A/remnawave-routing-updater/master/template.json
   ```

2. Настройте конфигурацию:
   ```bash
   nano .env
   ```
   *Вставьте ваш `API_TOKEN`, укажите `PANEL_URL` и включите нужных клиентов (`ENABLE_HAPP` / `ENABLE_INCY`). Для INCY также задайте `AUTOROUTING_URL`.*

3. Отредактируйте свой шаблон роутинга `my-template.json`:
   ```bash
   nano my-template.json
   ```
   Добавьте свои правила (`DirectSites`, базы обхода и т.д.). **Внимание:** поле `LastUpdated` добавлять не нужно — скрипт генерирует его сам.

4. Запустите сервис (образ скачается из GHCR):
   ```bash
   docker compose up -d
   ```

5. Просмотр логов:
   ```bash
   docker logs -f remna-routing-updater
   ```

Обновление в будущем — подтянуть свежий образ и пересоздать: `docker compose pull && docker compose up -d`.

<details>
<summary>Собрать из исходников (для разработки)</summary>

Если нужно править код — склонируйте репозиторий и собирайте локально. Замените строку `image:` в `docker-compose.yml` на `build: .`, затем:

```bash
git clone https://github.com/3APA3A-3AHO3A/remnawave-routing-updater.git
cd remnawave-routing-updater
cp .env.example .env && nano .env
cp template.json my-template.json && nano my-template.json
docker compose up -d --build
```
> 💡 Работаем именно с `my-template.json` (не отслеживается git), чтобы правки не конфликтовали при `git pull`; `template.json` остаётся эталоном.
</details>

## ✅ Проверка, что всё работает

В логах при успешном запуске вы увидите строки вида (сообщения выводятся на английском):
```
Service started. Interval: 21600 sec. | API: https://panel.your-domain.com | Happ: on, Incy: off | Geo mirror: off, Stamp: interval
File /app/output/routing.json saved successfully.
✅ Remnawave database updated successfully! Happ: field set, 1 rule(s) updated
```
Файл `./output/routing.json` должен появиться на диске, а по адресу `https://sub.your-domain.com/routing.json` (после настройки reverse proxy ниже) отдаваться валидный JSON.

## 🗺️ Гео-базы (зеркало и обрезка)

Там, где заблокирован GitHub, базы можно раздавать самому и даже ужать до того, что реально использует ваш шаблон.

Клиенты Happ/INCY качают `geoip.dat` / `geosite.dat` по ссылкам из шаблона
(`Geoipurl` / `Geositeurl`) — по умолчанию с GitHub. Там, где GitHub заблокирован, эти загрузки
часто не проходят и роутинг на клиенте ломается. Сервис умеет зеркалить обе базы на ваш сервер
(рядом с `routing.json`) и отдавать клиентам ссылку на ваш домен.

**Как это работает.** Каждый цикл сервис скачивает базы из upstream (GitHub доступен с
большинства серверов) условным запросом — если файл не менялся, приходит `304` и скачивание
пропускается — и записывает их атомарно, поэтому прокси никогда не отдаст недописанный файл.
Клиент всё равно качает **полный** файл и режет его локально (`UseChunkFiles`), так что вам
нужно хостить всего **два статических файла** — без чанк-манифестов и особых имён.

**Включение** в `.env`:
```dotenv
GEO_MIRROR_ENABLED=true
GEOIP_URL=https://sub.your-domain.com/geoip.dat
GEOSITE_URL=https://sub.your-domain.com/geosite.dat
```
`GEOIP_URL` / `GEOSITE_URL` — это то, что получают клиенты; оставьте пустыми, чтобы сохранить
дефолт из шаблона (GitHub). `template.json` держите указывающим на GitHub, чтобы установки там,
где GitHub доступен, работали из коробки — переключение целиком в `.env`. Базы ложатся в тот же каталог `./output`,
что и `routing.json`, поэтому примеры реверс-прокси ниже отдают все три файла сразу.

**Обрезать базы до категорий шаблона (опционально, `GEO_TRIM_ENABLED=true`).** Это серверный
аналог `UseChunkFiles`: вместо полных ~10–17 МБ сервис скачивает базы в приватный кэш и
пересобирает в раздаваемые `.dat` **только те категории, что реально упомянуты в шаблоне**
(записи `geosite:`/`geoip:` в `DirectSites`/`ProxySites`/`BlockSites` и IP-полях). Шаблон, где
используются лишь `geosite:private`, `geosite:category-ads-all` и `geoip:private`, ужимает `geosite.dat`
с ~10 МБ до сотен КБ, а `geoip.dat` с ~17 МБ до считанных КБ. Клиент тянет крошечный файл — большой
выигрыш на троттлящемся/DPI-канале. Обрезка идёт каждый цикл и сама ловит изменение, когда меняется
либо база в upstream, либо набор категорий в шаблоне. Требует `GEO_MIRROR_ENABLED`; полные файлы
лежат в `./output/.cache` и наружу не отдаются.

**Обновлять метку только при изменении базы (опционально).** По умолчанию (`STAMP_MODE=interval`)
метка `LastUpdated` — которая говорит клиентам перекачать гео-файлы — растёт каждый цикл. При
включённом зеркале можно переключиться на `STAMP_MODE=on_geo_change`: метка меняется (и панель
патчится) **только когда раздаваемая база реально изменилась**. Факт изменения определяется
бесплатно из условного запроса зеркала (а при обрезке — из самого обрезанного вывода), поэтому
можно снизить `UPDATE_INTERVAL_SECONDS` для более частой проверки, не переписывая панель и не дёргая
клиентов на каждом цикле. Один интервал покрывает обе задачи — отдельная переменная не нужна.

## 🌐 Настройка веб-сервера (Reverse Proxy)

**Зачем это нужно?** Функция `autorouting` в клиенте INCY периодически скачивает `routing.json` по прямой ссылке, а — если включено зеркало выше — клиенты так же качают `geoip.dat` / `geosite.dat`. Скрипт пишет все эти файлы в локальную папку `./output`; ваш веб-сервер отдаёт их по публичным адресам.

Отдавайте их с **домена вашей подписки** — клиент и так обновляет подписку по этому домену, значит эти файлы логично держать на том же хосте. В примерах используются `https://sub.your-domain.com/routing.json`, `…/geoip.dat` и `…/geosite.dat`.

> ⚠️ **Публичные адреса обязаны в точности совпадать с `AUTOROUTING_URL` / `GEOIP_URL` / `GEOSITE_URL` в вашем `.env`,** иначе клиент молча уйдёт на дефолт или не заработает.

Примеры дополняют официальные схемы reverse proxy от Remnawave ([docs.rw/install/reverse-proxies](https://docs.rw/install/reverse-proxies/)), где документированы **Caddy, Nginx, Traefik и Angie**. Сам Remnawave должен жить на корне домена/сабдомена (работа на суб-пути не поддерживается), но отдавать рядом несколько своих статических файлов это не запрещает — приложение остаётся на `/`, мы лишь выделяем `/routing.json` и два пути `.dat`. `routing.json` отдаётся с `Cache-Control: no-store` (всегда свежий), а редко меняющиеся `.dat` кэшируются. Во всех примерах предполагается официальный контейнер подписки `remnawave-subscription-page` на порту `3010`.

> Блоки `.dat` нужны **только если `GEO_MIRROR_ENABLED=true`**. Не используете зеркало? Пропустите их и отдавайте один `/routing.json`.

> ⚠️ **Ловите `geoip`/`geosite` широко, а не только `\.dat$`.** Клиент перед скачиванием ещё пробует `<файл>.dat.sha256`. Если location матчит только `.dat`, этот запрос проваливается в `location /` и проксируется на бэкенд подписки (порт `3010`) — поток таких запросов может его перегрузить и сломать реальное обновление подписок. Широкий матч `^/(geoip|geosite)\.` держит все гео-запросы на nginx и отдаёт **статический 404** на отсутствующую контрольную сумму (ровно как GitHub — сумма необязательна).

> Используете HAProxy впереди? Обычно это TCP/port-балансировщик, а не HTTP-прокси — терминируйте HTTPS на Nginx/Caddy/Angie позади него и отдавайте эти пути там, по подходящему примеру ниже.

После настройки проверьте:
```bash
curl -I https://sub.your-domain.com/routing.json   # 200, Content-Type: application/json, Cache-Control: no-store
curl -I https://sub.your-domain.com/geoip.dat      # 200, Content-Type: application/octet-stream  (только при зеркале)
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

# Гео-базы — только если GEO_MIRROR_ENABLED=true
location ~ ^/(geoip|geosite)\. {
    root /opt/remnawave-routing-updater/output;
    default_type application/octet-stream;
    add_header Cache-Control "public, max-age=86400";
    try_files $uri =404;
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

# Гео-базы — только если GEO_MIRROR_ENABLED=true
location ~ ^/(geoip|geosite)\. {
    root /usr/share/nginx/routing_output;
    default_type application/octet-stream;
    add_header Cache-Control "public, max-age=86400";
    try_files $uri =404;
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

    # 2. Гео-базы — только если GEO_MIRROR_ENABLED=true
    @geo path /geoip.dat* /geosite.dat*
    handle @geo {
        root * /opt/remnawave-routing-updater/output
        file_server
        header Content-Type application/octet-stream
        header Cache-Control "public, max-age=86400"
    }

    # 3. Весь остальной трафик идёт на страницу подписки
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

    # Гео-базы — только если GEO_MIRROR_ENABLED=true
    @geo path /geoip.dat* /geosite.dat*
    handle @geo {
        root * /usr/share/caddy/routing_output
        file_server
        header Content-Type application/octet-stream
        header Cache-Control "public, max-age=86400"
    }

    reverse_proxy * http://remnawave-subscription-page:3010
}
```
*Примените:* `docker exec -w /etc/caddy имя_контейнера_caddy caddy reload`

---

### 🟠 Traefik

Traefik — это прокси, а не файловый сервер, поэтому запустите крошечный контейнер для раздачи файлов в той же сети `remnawave-network` и направьте на него `/routing.json` (а при включённом зеркале — и гео-базы). Контейнер и так монтирует всю папку `./output`, так что доступны все три файла:
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
      service: routing-file
      priority: 1000          # выигрываем у роутера подписки на этом пути
      tls:
        certResolver: letsencrypt
      middlewares:
        - routing-nostore
    # Гео-базы — только если GEO_MIRROR_ENABLED=true (кэшируются, отдельный middleware)
    geo-files:
      rule: "Host(`sub.your-domain.com`) && (Path(`/geoip.dat`) || Path(`/geoip.dat.sha256`) || Path(`/geosite.dat`) || Path(`/geosite.dat.sha256`))"
      entryPoints:
        - https
      service: routing-file
      priority: 1000
      tls:
        certResolver: letsencrypt
      middlewares:
        - geo-cache
  services:
    routing-file:
      loadBalancer:
        servers:
          - url: "http://remna-routing-file:80"
  middlewares:
    routing-nostore:
      headers:
        customResponseHeaders:
          Cache-Control: "no-store"
    geo-cache:
      headers:
        customResponseHeaders:
          Cache-Control: "public, max-age=86400"
```
Подставьте свои `entryPoints`/`certResolver` из `traefik.yml`. *Пересоздайте:* `docker compose up -d`

> Если ваш Traefik использует провайдер Docker-лейблов, вместо YAML выше повесьте эквивалентные лейблы на сервис `routing-file`: роутер `routing-json` (`...rule=…Path(/routing.json)`, `...priority=1000`, `...service=routing-file`, `...loadbalancer.server.port=80`, middleware `routing-nostore`) и — при включённом зеркале — роутер `geo-files` (`...rule=…Path(/geoip.dat)||Path(/geoip.dat.sha256)||Path(/geosite.dat)||Path(/geosite.dat.sha256)`, тот же сервис, middleware `geo-cache`).

## 🐞 Troubleshooting

**Запуск / API**
- **`CRITICAL ERROR: API_TOKEN is not set`** — не заполнен `API_TOKEN` в `.env`.
- **`CRITICAL ERROR: both ENABLE_HAPP and ENABLE_INCY are disabled`** — включите хотя бы одного клиента.
- **`AUTOROUTING_URL not set … autorouting header is skipped`** — это не ошибка: INCY работает только на хэдере `routing`. Задайте реальную ссылку в `.env`, чтобы включить функцию `autorouting`.
- **`API error: 'response' object not found`** — неверный `PANEL_URL` или токен без прав `Subscription Template: Read/Write`.

**Правки конфига не применяются** — после изменения `.env` или `my-template.json` пересоздайте контейнер: `docker compose up -d --force-recreate`. Если образ устарел, сначала подтяните свежий: `docker compose pull && docker compose up -d`. (Собираете из исходников? Пересоберите: `docker compose up -d --build`.)

**По ссылке `/routing.json` отдаётся HTML вместо JSON** — reverse proxy перехватывает запрос; проверьте настройку выше (в Caddy обязателен блок `handle`, в Traefik нужен более высокий приоритет роутера).

**Гео-файлы / подписка «отваливается»** (актуально только при включённом зеркале):
- **`/geoip.dat` отдаётся 200, но не оттуда, либо `502`/`upstream prematurely closed` на `/geoip.dat.sha256`, `/sub/…`, `/assets/…`** — гео-запросы проксируются на бэкенд подписки (порт `3010`) вместо статики и могут его положить. Ловите `geoip`/`geosite` **широко** (`location ~ ^/(geoip|geosite)\.`), а не только `\.dat$`: клиент ещё пробует `<файл>.dat.sha256`, и он должен отдавать **статический 404**, а не идти на бэкенд. После правки перезагрузите nginx и один раз перезапустите контейнер подписки.
- **Обрезанный `.dat` выглядит пустым / в логах `categories not found in source`** — имена категорий в шаблоне не совпадают с базой-источником. Сверьте `geosite:`/`geoip:` в `my-template.json` с категориями upstream.
- **`geoip`/`geosite` помечается `invalid` в логе Happ, хотя файл не битый** (`Geo files validation failed … geoip=invalid (size=240 bytes)`) — обрезка до одной крошечной категории (например, только `geoip:private`, ~240 байт) даёт файл, который Happ бракует как слишком маленький (защита от недокачанного/битого файла); сам protobuf при этом структурно корректен. Лечение: держите в раздаче хотя бы одну «весомую» категорию — например, добавьте `geoip:google` (~126 КБ) или `geoip:cloudflare` (~9 КБ) в нужное IP-поле шаблона. Тогда `geoip.dat` станет сотни КБ и пройдёт валидацию, оставаясь крошечным против полных ~17 МБ. (Осторожно с мелкими категориями: например, `geoip:telegram` — всего ~181 байт, тоже не пройдёт.)

## 📄 Лицензия

Проект распространяется под лицензией MIT — см. файл [LICENSE](./LICENSE).
