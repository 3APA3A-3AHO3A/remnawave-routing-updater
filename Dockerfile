FROM python:3.15-alpine

WORKDIR /app

COPY requirements.txt .
# pip нужен только на сборке. После установки зависимостей он удаляется вместе
# с ensurepip: в работе сервиса он не участвует, а во вложенных копиях библиотек
# (pip/_vendor: urllib3, msgpack, pkg_resources) сканеры находят уязвимости,
# которые обновлением requirements.txt не закрыть.
RUN pip install --no-cache-dir -r requirements.txt \
 && ENSUREPIP_DIR="$(python -c 'import ensurepip, os; print(os.path.dirname(ensurepip.__file__))')" \
 && pip uninstall -y pip \
 && rm -rf "$ENSUREPIP_DIR" /root/.cache

COPY . .

HEALTHCHECK --interval=5m --timeout=10s --start-period=3m --retries=3 \
    CMD ["python", "-m", "routing_updater.healthcheck"]

CMD ["python", "-u", "-m", "routing_updater"]
