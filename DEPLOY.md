# Деплой Literary Haven — публичный сайт

Этот гайд выводит сайт в интернет, чтобы любой мог зайти с телефона или ПК
по адресу `https://ваш-домен.com`.

---

## Что поднимается автоматически

| Сервис | Что делает |
|--------|-----------|
| **PostgreSQL** | База данных |
| **Redis** | Общий state для rate-limiting между воркерами |
| **FastAPI app** | Само приложение (за реверс-прокси) |
| **Caddy** | HTTPS-терминация, SSL от Let's Encrypt, раздача статики |

Caddy **автоматически** получает и обновляет SSL-сертификат — ничего дополнительно настраивать не нужно.

---

## Требования к серверу

- VPS/выделенный сервер с Ubuntu 22.04 / Debian 12 (или любой Linux)
- Публичный IP-адрес
- Docker ≥ 24 + Docker Compose plugin
- Порты **80** и **443** открыты в файрволе
- Зарегистрированное доменное имя

---

## Шаг 1 — Купите домен и настройте DNS

1. Купите домен (REG.RU, Timeweb, Namecheap и т.д.)
2. В панели DNS-провайдера создайте **A-запись**:
   ```
   Тип:  A
   Имя:  @  (или yoursite.com)
   IP:   <IP вашего сервера>
   TTL:  300
   ```
3. Проверьте что запись работает (может занять до 1 часа):
   ```bash
   nslookup yourdomain.com
   # должен вернуть IP вашего сервера
   ```

---

## Шаг 2 — Установите Docker на сервер

```bash
# Ubuntu / Debian
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Проверка
docker --version
docker compose version
```

---

## Шаг 3 — Загрузите проект на сервер

```bash
# Вариант А — git clone (если есть репозиторий)
git clone https://your-repo-url.git literaryhaven
cd literaryhaven

# Вариант Б — загрузить архив через scp
scp -r ./literaryhaven user@YOUR_SERVER_IP:~/literaryhaven
ssh user@YOUR_SERVER_IP
cd ~/literaryhaven
```

---

## Шаг 4 — Создайте `.env` и заполните переменные

```bash
cp .env.example .env
nano .env
```

**Обязательно заполнить:**

```env
# Ваш домен (без https://)
DOMAIN=yourdomain.com

# Пароль БД — придумайте сложный
POSTGRES_PASSWORD=придумайте_сложный_пароль

# Генерируйте каждый ключ отдельно:
# python3 -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=сгенерируйте_64_символьный_ключ
REFRESH_SECRET_KEY=сгенерируйте_другой_64_символьный_ключ
```

> **OAuth** (Google, GitHub, VK): если не нужен — оставьте пустыми.
> Настройте позже в панелях разработчика каждого провайдера,
> указав redirect URI: `https://yourdomain.com/api/v1/auth/google/callback`

---

## Шаг 5 — Запустите

```bash
# Первый запуск: сборка образа + миграции + сидирование БД
docker compose up -d --build

# Следим за логами (первый старт занимает 5-20 минут — идёт заполнение БД)
docker compose logs -f app
```

**Что происходит автоматически:**
1. PostgreSQL запускается и проходит healthcheck
2. `entrypoint.sh` ждёт БД, запускает `alembic upgrade head` (миграции)
3. Проверяет флаг `data_seeded` — если нет, запускает `seed_real_books.py`
4. Uvicorn стартует с `--proxy-headers` (принимает реальный IP от Caddy)
5. Caddy запрашивает SSL-сертификат у Let's Encrypt для вашего домена
6. Сайт доступен по `https://yourdomain.com` 🎉

---

## Шаг 6 — Проверьте что всё работает

```bash
# Статус контейнеров
docker compose ps

# Проверка health endpoint
curl https://yourdomain.com/health
# → {"status":"ok"}

# Проверка SSL
curl -I https://yourdomain.com
# → HTTP/2 200
```

---

## Последующие перезапуски (без пересева)

```bash
docker compose restart        # перезапустить все сервисы
docker compose restart app    # только приложение
```

---

## Обновление кода

```bash
git pull
docker compose up -d --build
# entrypoint.sh применит только новые миграции, сидирование пропустит
```

---

## Открытые порты на сервере

Убедитесь что в файрволе открыты только нужные порты:

```bash
# Ubuntu UFW
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP (Caddy редиректит на HTTPS)
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable

# Порт 8000 НЕ открываем — приложение доступно только через Caddy
```

---

## Полезные команды

```bash
# Логи
docker compose logs app --tail=100 -f
docker compose logs caddy --tail=50

# Войти в контейнер приложения
docker compose exec app bash

# Применить миграции вручную
docker compose exec app alembic upgrade head

# Проверить статус сидирования
docker compose exec app python app/utils/check_data_loaded.py

# Перезагрузить Caddy без даунтайма (после изменения Caddyfile)
docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile
```

---

## Мониторинг и бэкапы

**Бэкап базы данных:**
```bash
# Создать дамп
docker compose exec db pg_dump -U lhuser literaryhaven > backup_$(date +%Y%m%d).sql

# Восстановить
docker compose exec -T db psql -U lhuser literaryhaven < backup_20250101.sql
```

**Бэкап загруженных файлов (аватары):**
```bash
tar czf uploads_$(date +%Y%m%d).tar.gz app/static/uploads/
```

---

## Принудительный пересев (после очистки БД)

```bash
# Сбросить флаг сидирования
docker compose exec app python - <<'EOF'
import asyncio
from app.db.base import AsyncSessionLocal
from sqlalchemy import text
async def clear():
    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM app_state WHERE key = 'data_seeded'"))
        await db.commit()
        print("Флаг сброшен — при следующем restart запустится пересев.")
asyncio.run(clear())
EOF

docker compose restart app
```

---

## Частые проблемы

| Проблема | Причина | Решение |
|----------|---------|---------|
| Caddy не получает сертификат | DNS ещё не обновился | Подождите до 1 часа после создания A-записи |
| Caddy не получает сертификат | Порт 80/443 закрыт файрволом | `sudo ufw allow 80 && sudo ufw allow 443` |
| Caddy не получает сертификат | Let's Encrypt rate limit | Подождите 1 час, не перезапускайте часто |
| 502 Bad Gateway | app ещё не запустился | `docker compose logs app` — ждите завершения seed |
| Куки не работают после HTTPS | APP_ENV не production | Проверьте env: `docker compose exec app env \| grep APP_ENV` |
| OAuth redirect_uri mismatch | Неверный домен в OAuth app | В консоли провайдера укажите `https://yourdomain.com/api/v1/auth/PROVIDER/callback` |
