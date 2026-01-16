# Инструкция по установке StealthNET Admin Panel на чистый сервер

## Содержание

1. [Требования](#требования)
2. [Установка Docker и Docker Compose](#установка-docker-и-docker-compose)
3. [Подготовка сервера](#подготовка-сервера)
4. [Настройка переменных окружения](#настройка-переменных-окружения)
   - [Основные настройки](#основные-настройки)
   - [Генерация ключей](#генерация-ключей)
   - [Настройка Telegram-бота](#настройка-telegram-бота)
   - [Настройка платёжных систем](#настройка-платёжных-систем)
5. [Настройка SSL-сертификата](#настройка-ssl-сертификата)
6. [Настройка Nginx](#настройка-nginx)
7. [Запуск проекта](#запуск-проекта)
8. [Проверка работы](#проверка-работы)
9. [Создание пользователя с правами администратора](#создание-пользователя-с-правами-администратора)
10. [Управление проектом](#управление-проектом)
11. [Обновление проекта](#обновление-проекта)
12. [Резервное копирование базы данных](#резервное-копирование-базы-данных)
13. [Решение проблем](#решение-проблем)
14. [Дополнительные настройки](#дополнительные-настройки)
15. [Чеклист после установки](#чеклист-после-установки)

## Требования

- **Операционная система**: Ubuntu 20.04+ / Debian 11+ / CentOS 8+
- **RAM**: минимум 2 GB (рекомендуется 4 GB+)
- **Диск**: минимум 10 GB свободного места
- **Доступ**: root или sudo-права
- **Домен**: рекомендуется (обязателен для SSL)

## Установка Docker и Docker Compose

### Ubuntu / Debian

Установите Docker:
```bash
sudo curl -fsSL https://get.docker.com | sh
```

Запустите Docker и добавьте его в автозапуск:
```bash
sudo systemctl start docker
sudo systemctl enable docker
```

Если Docker используется не от имени `root`, добавьте пользователя в группу `docker`:
```bash
sudo usermod -aG docker $USER
newgrp docker
```

Проверьте установку:
```bash
docker --version
docker compose version
```

### CentOS / RHEL

Установите Docker:
```bash
sudo curl -fsSL https://get.docker.com | sh
```

Запустите Docker и добавьте его в автозапуск:
```bash
sudo systemctl start docker
sudo systemctl enable docker
```

Если Docker используется не от имени `root`, добавьте пользователя в группу `docker`:
```bash
sudo usermod -aG docker $USER
newgrp docker
```

Проверьте установку:
```bash
docker --version
docker compose version
```

## Подготовка сервера

⚠️ **Важно**  
Проект должен быть установлен в следующую директорию:
```
/opt/remnawave-STEALTHNET-Panel
```

Клонируйте репозиторий:
```bash
cd /opt
git clone https://github.com/GOFONCK/remnawave-STEALTHNET-Panel.git
cd remnawave-STEALTHNET-Panel
```

Создайте необходимые директории:
```bash
mkdir -p instance cache logs nginx/ssl frontend/build
```

При использовании пользователя без прав `root` назначьте владельца и права доступа:
```bash
sudo chown -R $USER:$USER /opt/remnawave-STEALTHNET-Panel
chmod -R 755 /opt/remnawave-STEALTHNET-Panel
```

## Настройка переменных окружения

Создайте и отредактируйте файл `.env`:
```bash
cd /opt/remnawave-STEALTHNET-Panel

if [ -f .env.example ]; then
    cp .env.example .env
elif [ -f env.example ]; then
    cp env.example .env
else
    touch .env
fi

nano .env
```

### Основные настройки

```env
# Секретный ключ JWT
# Методы генерации ключей приведены ниже
JWT_SECRET_KEY=секретный_ключ_JWT

# URL панели Remnawave
API_URL=https://panel.yourdomain.com

# API-токен панели Remnawave
# Remnawave → Настройки → API-токены → Создать
ADMIN_TOKEN=токен_remnawave

# ID сквада по умолчанию
# Remnawave → Внутренние сквады → Скопировать UUID
DEFAULT_SQUAD_ID=id_сквада

# Домен или IP сервера (без https://),
# на котором развёртывается StealthNET Admin Panel
YOUR_SERVER_IP=stealthnet.yourdomain.com

# Название сервиса
SERVICE_NAME=StealthNET
```

### Генерация ключей

Вариант 1:
```bash
chmod +x generate_keys.sh
./generate_keys.sh
```

Вариант 2:

JWT:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

FERNET:
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Настройка Telegram-бота

```env
# Получите токен Telegram-бота через @BotFather
# (Open → Copy или командой /token)
CLIENT_BOT_TOKEN=токен_бота

# URL Flask API
# Внутри Docker используйте http://api:5000
FLASK_API_URL=http://api:5000

# URL Mini App (совпадает с адресом панели)
MINIAPP_URL=https://stealthnet.yourdomain.com
```

### Настройка платёжных систем

```env
# CrystalPay (пример)
CRYSTALPAY_API_KEY=api_key
CRYSTALPAY_API_SECRET=api_secret
```

Telegram Stars использует `CLIENT_BOT_TOKEN`  
Дополнительная настройка не требуется.

⚠️ **Важно**: Не все платежные системы обязательны. Настройте только те, которые вам нужны.

## Настройка SSL-сертификата

### Let's Encrypt (рекомендуется)

⚠️ Во время получения сертификата контейнер Nginx должен быть остановлен.

Проверьте доступность 80 порта:
```bash
ss -tulpn | grep ':80' && echo "❌ 80 порт занят" || echo "✅ 80 порт свободен"
```

Установите Certbot (Ubuntu/Debian):
```bash
sudo apt install -y certbot
```

Установите Certbot (CentOS/RHEL):
```bash
sudo yum install -y certbot
```

Получите сертификат (замените домен и email):
```bash
sudo certbot certonly --standalone -d stealthnet.yourdomain.com --agree-tos -m your@email.com
```

Скопируйте сертификаты:
```bash
mkdir -p nginx/ssl
cp /etc/letsencrypt/live/stealthnet.yourdomain.com/fullchain.pem nginx/ssl/
cp /etc/letsencrypt/live/stealthnet.yourdomain.com/privkey.pem nginx/ssl/
```

### Самоподписанный сертификат (для тестирования)

```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/ssl/privkey.pem \
  -out nginx/ssl/fullchain.pem
```

## Настройка Nginx

Замените stealthnet.yourdomain.com на ваш домен для реадктирования конфигурационного файла Nginx:
```bash
sed -i 's/you_domain/stealthnet.yourdomain.com/g' nginx/nginx.conf
```

## Запуск проекта

Подготовьте окружение:
```bash
cd /opt/remnawave-STEALTHNET-Panel
mkdir -p instance
```

### Запуск (рекомендуется)

```bash
chmod +x start.sh
./start.sh
```

### Ручной запуск

```bash
docker compose build
docker compose up -d
```

## Проверка работы

Проверьте статус контейнеров:
```bash
docker compose ps
```

Просмотрите логи проекта:
```bash
docker compose logs -f
```

Проверьте доступность API:
```bash
curl http://localhost:5000/api/public/health
```

Ожидаемый ответ:
```json
{"status":"ok"}
```

## Создание пользователя с правами администратора

Измените учётные данные администратора:

- Login: `admin@yourdomain.com`
- Password: `mypassword123`

Создайте пользователя командой:
```bash
docker exec stealthnet-api python3 /app/create_admin.py admin@yourdomain.com mypassword123
```

## Управление проектом

Запуск проекта:
```bash
docker compose up -d
```

Остановка проекта:
```bash
docker compose down
```

Перезапуск сервисов:
```bash
docker compose restart api
docker compose restart bot
docker compose restart nginx
```

Просмотр логов:
```bash
docker compose logs -f
```

## Обновление проекта

```bash
cd /opt/remnawave-STEALTHNET-Panel
docker compose down
git pull
docker compose build --no-cache
docker compose run --rm api python3 migration/migrate_all.py
docker compose up -d
```

## Резервное копирование базы данных

Создайте резервную копию:
```bash
docker compose cp api:/app/instance/stealthnet.db ./backup_stealthnet_$(date +%Y%m%d_%H%M%S).db
```

## Решение проблем

- Проверьте логи: `docker compose logs`
- Проверьте статус контейнеров: `docker compose ps`
- Проверьте конфигурацию: `docker compose config`
- Убедитесь, что файл `.env` заполнен корректно

## Дополнительные настройки

### Настройка Telegram Webhook

```bash
curl -X POST "https://api.telegram.org/botYOUR_BOT_TOKEN/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://panel.stealthnet.app/api/webhook/telegram"}'
```

## Чеклист после установки

- [ ] Docker и Docker Compose установлены
- [ ] `.env` заполнен
- [ ] Контейнеры запущены
- [ ] API доступен
- [ ] SSL настроен
- [ ] Telegram-бот отвечает

## Важные замечания

- Никогда не коммитьте файл `.env`
- Для продакшена рекомендуется PostgreSQL
- Регулярно обновляйте Docker-образы
- Настройте резервное копирование
---

# Готово! StealthNET Admin Panel установлена и готова к работе.











