# Remnawave Routing Auto Updater

Автономный микросервис на Python + Docker для автоматического обновления баз роутинга (`geoip`, `geosite`) для клиентов **Happ** и **INCY** в панели управления [Remnawave](https://github.com/remnawave).

Скрипт использует **официальный API Remnawave** для обновления настроек подписки, что делает его максимально безопасным (никаких доступов к базе данных напрямую!). Логирование автоматически ротируется встроенными средствами Docker.

## Особенности
* Легковесный образ на базе `Alpine Linux` (~30 МБ).
* Работа через официальный API Remnawave (по токену).
* Автоматическая генерация файла `routing.json` для функции `autorouting` в INCY.

## ⚙️ Требования и логика работы

* **Для клиентов HAPP:** Скрипт работает "из коробки". Он автоматически обновляет стандартное поле `Happ routing` в настройках подписки. Если у вас создано кастомное правило в "Правилах ответов" с именем `Happ`, скрипт обновит и его.
* **Для клиентов INCY:** Вам необходимо зайти в Remnawave → **Раздел "Подписка"** → **Правила ответов**, создать правило с именем `Incy` и добавить заголовки (Headers) с ключами `routing` и `autorouting`. Значения в эти ключи можно вписать любые — скрипт сам заменит их на актуальные ссылки.
  > 💡 **Готовый шаблон:** Чтобы не путаться с настройками интерфейса, вы можете посмотреть правильную структуру правил и заголовков в файле-примере [response_rules.example.json](./response_rules.example.json).
* В разделе **Настройки Remnawave** → **API токены** создайте новый токен (Права `Read/Write` в разделе *Subscription Template*) и скопируйте его в файл `.env`.

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
   *Вставьте ваш `API_TOKEN` и укажите ваш домен в `PANEL_URL`.*

3. Отредактируйте `template.json`, добавив свои правила (DirectSites, базы обхода и т.д.). **Внимание:** Поле `LastUpdated` добавлять не нужно, скрипт генерирует его автоматически.

4. Запустите сервис:
   ```bash
   docker compose up -d --build
   ```

5. Просмотр логов:
   ```bash
   docker logs -f remna-routing-updater
   ```

## 🌐 Настройка веб-сервера (Reverse Proxy) для INCY

**Зачем это нужно?** Функция `autorouting` в клиенте INCY работает путем периодического скачивания JSON-файла по прямой ссылке. Наш скрипт генерирует свежий файл и кладет его в локальную папку `./output`. Чтобы клиент мог получить к нему доступ из интернета (по ссылке `https://ваш-домен.com/routing.json`), вашему веб-серверу нужно явно указать, где лежит этот файл.

Выберите ваш веб-сервер и тип его установки (в качестве примера используется `субдомен подписки`):

### 🟢 Настройка Nginx

#### Вариант А: Nginx установлен на сервере (без Docker)
Добавьте этот блок *перед* основным `location /` в конфигурацию вашего домена:
```nginx
location /routing.json {
    # Укажите реальный путь до папки скрипта на сервере
    alias /opt/remnawave-routing-updater/output/routing.json;
    add_header Content-Type application/json;
}
```
*Примените настройки:* `systemctl reload nginx`

#### Вариант Б: Nginx работает в Docker
Поскольку Nginx изолирован, ему нужно прокинуть папку внутрь контейнера.
1. Откройте `docker-compose.yml` вашего Nginx и добавьте `volume`:
```yaml
    volumes:
      # Прокидываем папку внутрь Nginx (только для чтения - ro)
      - /opt/remnawave-routing-updater/output:/usr/share/nginx/routing_output:ro
```
*Пересоздайте контейнер:* `docker compose up -d`
2. В конфиге домена укажите внутренний путь Docker:
```nginx
location /routing.json {
    alias /usr/share/nginx/routing_output/routing.json;
    add_header Content-Type application/json;
}
```
*Примените настройки:* `docker exec ваш_контейнер_nginx nginx -s reload`

---

### 🔵 Настройка Caddy

> ⚠️ **Важно:** В Caddy нельзя просто использовать глобальный `reverse_proxy *` вместе с раздачей файлов. Необходимо разделить маршруты с помощью блоков `handle`, иначе Caddy отправит запрос на файл в панель, и вы получите ошибку 502.

#### Вариант А: Caddy установлен на сервере (без Docker)
Измените ваш `Caddyfile`, разделив трафик:
```caddyfile
https://sub.your-domain.com {
    # 1. Отдаем статический JSON
    handle /routing.json {
        root * /opt/remnawave-routing-updater/output
        file_server
        header Content-Type application/json
    }

    # 2. Весь остальной трафик идет в панель
    reverse_proxy * http://127.0.0.1:3010
}
```
*Примените настройки:* `systemctl reload caddy`

#### Вариант Б: Caddy работает в Docker
Поскольку Caddy изолирован, прокиньте ему папку с файлом.
1. Откройте `docker-compose.yml` вашего Caddy и добавьте `volume`:
```yaml
    volumes:
      # Прокидываем папку внутрь Caddy (только для чтения - ro)
      - /opt/remnawave-routing-updater/output:/usr/share/caddy/routing_output:ro
```
*Пересоздайте контейнер:* `docker compose up -d`

2. Настройте `Caddyfile`, указав внутренний путь Docker:
```caddyfile
https://sub.your-domain.com {
    # 1. Отдаем статический JSON
    handle /routing.json {
        root * /usr/share/caddy/routing_output
        file_server
        header Content-Type application/json
    }
    
    # 2. Весь остальной трафик идет в контейнер подписки
    reverse_proxy * http://remnawave-subscription-page:3010
}
```
*Примените настройки:* `docker exec -w /etc/caddy имя_контейнера_caddy caddy reload`
