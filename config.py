"""
Конфигурационный файл
config.py
"""

import os
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Токен бота (получить у @BotFather)
TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# ID администратора для уведомлений (ваш Telegram ID)
ADMIN_ID = int(os.getenv("ADMIN_ID", "0")) if os.getenv("ADMIN_ID") else None

# Время отправки ежедневных напоминаний (час, минута)
REMINDER_TIME = (9, 0)  # 09:00

# Имя файла базы данных
DATABASE_NAME = "payments.db"

# Часовой пояс
TIMEZONE = "Europe/Moscow"