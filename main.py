import os
from flask import Flask, request
import telebot
from telebot import types  # Используем types.InlineKeyboardMarkup и types.InlineKeyboardButton
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from PIL import Image
import io
import json
import requests
import random

# === НАСТРОЙКИ (заполни в переменных окружения Render) ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Переменная окружения BOT_TOKEN не задана!")

OWNER_ID = os.getenv("OWNER_ID")
if OWNER_ID:
    try:
        OWNER_ID = int(OWNER_ID)
    except:
        raise ValueError("OWNER_ID должен быть числом (ваш Telegram ID)")

CHANNEL_ID = os.getenv("CHANNEL_ID", "@your_channel")  # Замените на ID канала

HF_API_KEY = os.getenv("HF_API_KEY")  # Для Hugging Face (если используется)
UNSPLASH_KEY = os.getenv("UNSPLASH_KEY")  # Для Unsplash (если используется)

# === Глобальные переменные ===
bot = telebot.TeleBot(BOT_TOKEN)
scheduler = BackgroundScheduler()
app = Flask(__name__)

# Файлы для хранения данных
HISTORY_FILE = "user_history.json"
QUEUE_FILE = "daily_queue.json"
CACHE_FILE = "image_cache.json"
POSTS_LOG_FILE = "published_posts.json"

# === Загрузка и сохранение данных ===
def load_json(filename, default):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# === Webhook: обработка входящих сообщений от Telegram ===
@app.route('/webhook', methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.get_json())
    bot.process_new_updates([update])
    return 'OK', 200

# === Главная страница: устанавливает webhook ===
@app.route('/')
def home():
    bot.remove_webhook()
    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/webhook"
    bot.set_webhook(url=webhook_url)
    return "<h1>✅ Бот запущен и готов к работе!</h1>", 200

# === Обработчик команды /start ===
@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.InlineKeyboardMarkup()
    btn1 = types.InlineKeyboardButton("О боте", callback_data="about")
    btn2 = types.InlineKeyboardButton("Помощь", callback_data="help")
    markup.add(btn1, btn2)
    
    bot.reply_to(
        message,
        "👋 Привет! Я — ваш Telegram-бот, запущенный на Render.\n\n"
        "Нажмите кнопку ниже, чтобы узнать больше.",
        reply_markup=markup
    )

# === Обработчик нажатий на кнопки ===
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.data == "about":
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="🤖 Этот бот работает на платформе Render с использованием webhook.\n\n"
                 "Он может публиковать посты, генерировать изображения и многое другое!"
        )
    elif call.data == "help":
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="💡 Помощь:\n\n"
                 "• /start — начать\n"
                 "• Кнопки работают через inline-меню\n"
                 "• Бот использует Flask + webhook"
        )

# === Пример задачи по расписанию (опционально) ===
def scheduled_task():
    try:
        bot.send_message(OWNER_ID, f"✅ Задача выполнена: {datetime.now().strftime('%H:%M:%S')}")
    except Exception as e:
        print(f"Ошибка при отправке владельцу: {e}")

# Запуск задачи каждые 5 минут (только если указан OWNER_ID)
if OWNER_ID:
    scheduler.add_job(scheduled_task, 'interval', minutes=5)
    scheduler.start()

# === Запуск Flask-сервера ===
if __name__ == '__main__':
    # Убедитесь, что используется порт от Render
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

