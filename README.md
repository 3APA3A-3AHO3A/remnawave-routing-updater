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

**Зачем это нужно?** Функция `autorouting` в клиенте INCY работает путем периодического скачивания JSON-файла по прямой ссылке. Наш скрипт генерирует свежий файл и кладет его в локальную папку `./output`. Чтобы клиент мог получить к нему доступ из интернета, нужно указать вашему веб-серверу отдавать этот файл.

Добавьте соответствующий блок в конфигурацию вашего домена:

### Вариант 1: Для Nginx
Добавьте этот блок *перед* основным `location /`:
```nginx
location /routing.json {
    alias /полный/путь/к/папке/remnawave-routing-updater/output/routing.json;
    add_header Content-Type application/json;
}
```
*Не забудьте перезапустить Nginx:* `systemctl reload nginx`

### Вариант 2: Для Caddy
Добавьте маршрут (handle) внутрь блока вашего домена:
```caddyfile
panel.your-domain.com {
    # ... ваши текущие настройки (reverse_proxy) ...

    handle /routing.json {
        root * /полный/путь/к/папке/remnawave-routing-updater/output
        file_server
        header Content-Type application/json
    }
}
```
*Не забудьте применить конфигурацию:* `caddy reload`

