#!/usr/bin/env bash
# PostgreSQL на VDS (Ubuntu) для бота на Railway. Запуск: sudo bash vds_postgres_setup.sh
# Опционально: export POSTGRES_DB=guard POSTGRES_USER=guard POSTGRES_PASSWORD='...'
# Пароль без символа ' (одинарной кавычки) или используй сгенерированный hex.

set -euo pipefail

if [[ "${EUID:-0}" -ne 0 ]]; then
  echo "Запусти от root: sudo bash $0"
  exit 1
fi

if [[ -n "${POSTGRES_PASSWORD:-}" ]] && [[ "$POSTGRES_PASSWORD" == *"'"* ]]; then
  echo "POSTGRES_PASSWORD не должен содержать одинарную кавычку, или убери переменную — сгенерирую сам."
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

DB_NAME="${POSTGRES_DB:-guard}"
DB_USER="${POSTGRES_USER:-guard}"
if ! [[ "$DB_NAME" =~ ^[a-zA-Z0-9_]+$ && "$DB_USER" =~ ^[a-zA-Z0-9_]+$ ]]; then
  echo "POSTGRES_DB и POSTGRES_USER: только буквы, цифры, подчёркивание."
  exit 1
fi

if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
  POSTGRES_PASSWORD="$(openssl rand -hex 24)"
  echo "=== Сгенерирован пароль (сохрани + вставь в Railway) ==="
  echo "${POSTGRES_PASSWORD}"
  echo "========================================================"
fi

apt-get update -qq
apt-get install -y -qq postgresql postgresql-contrib ufw openssl

PG_MAIN=$(find /etc/postgresql -name postgresql.conf 2>/dev/null | head -1)
PG_HBA=$(find /etc/postgresql -name pg_hba.conf 2>/dev/null | head -1)
if [[ -z "$PG_MAIN" || -z "$PG_HBA" ]]; then
  echo "Не найдены postgresql.conf / pg_hba.conf"
  exit 1
fi

sed -i "s/^#\\?listen_addresses.*/listen_addresses = '*'/" "$PG_MAIN"

# SSL на сервере можно включить позже; для первого коннекта с Railway надёжнее host + scram (не hostssl).
if [[ -f /etc/ssl/private/ssl-cert-snakeoil.key ]]; then
  grep -q '^ssl = on' "$PG_MAIN" || echo "ssl = on" >> "$PG_MAIN"
  grep -q '^ssl_cert_file' "$PG_MAIN" || echo "ssl_cert_file = '/etc/ssl/certs/ssl-cert-snakeoil.pem'" >> "$PG_MAIN"
  grep -q '^ssl_key_file' "$PG_MAIN" || echo "ssl_key_file = '/etc/ssl/private/ssl-cert-snakeoil.key'" >> "$PG_MAIN"
fi
HBA_LINE="host all ${DB_USER} 0.0.0.0/0 scram-sha-256"

if ! grep -qF "Railway bot ${DB_USER}" "$PG_HBA"; then
  echo "" >> "$PG_HBA"
  echo "# Railway bot ${DB_USER}" >> "$PG_HBA"
  echo "${HBA_LINE}" >> "$PG_HBA"
fi

pw_sql="${POSTGRES_PASSWORD//\'/\'\'}"
if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'" | grep -q 1; then
  sudo -u postgres psql -v ON_ERROR_STOP=1 -c "ALTER USER \"${DB_USER}\" WITH PASSWORD '${pw_sql}';"
else
  sudo -u postgres psql -v ON_ERROR_STOP=1 -c "CREATE USER \"${DB_USER}\" WITH PASSWORD '${pw_sql}';"
fi

if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1; then
  sudo -u postgres createdb -O "$DB_USER" "$DB_NAME"
else
  sudo -u postgres psql -c "ALTER DATABASE \"${DB_NAME}\" OWNER TO \"${DB_USER}\";"
fi

systemctl restart postgresql

ufw allow OpenSSH
ufw allow 5432/tcp comment 'PostgreSQL bot'
ufw --force enable || true

SERVER_IP="${PUBLIC_IP:-}"
echo ""
echo "=== Готово ==="
echo "База: ${DB_NAME}, пользователь: ${DB_USER}, порт: 5432"
echo ""
echo "В Railway → Variables добавь DATABASE_URL (подставь IP сервера и пароль):"
echo "postgresql://${DB_USER}:${POSTGRES_PASSWORD}@ВАШ_IP:5432/${DB_NAME}"
echo ""
echo "Если async ругается на SSL, попробуй в конце URL: ?ssl=true"
echo ""
echo "Локальная проверка на сервере:"
echo "  sudo -u postgres psql -h 127.0.0.1 -U ${DB_USER} -d ${DB_NAME} -c 'SELECT 1'"
