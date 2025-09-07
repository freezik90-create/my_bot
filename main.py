# bot.py
import telebot
import requests
import random
import json
import os
import time
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify
from PIL import Image
import io

# === НАСТРОЙКИ (заполни в .env) ===
BOT_TOKEN = os.getenv("BOT_TOKEN", "ВАШ_ТОКЕН_ЗДЕСЬ")
OWNER_ID = int(os.getenv("OWNER_ID", 0))  # Ваш Telegram ID
CHANNEL_ID = os.getenv("CHANNEL_ID", "@ваш_канал")

HF_API_KEY = os.getenv("HF_API_KEY")
UNSPLASH_KEY = os.getenv("UNSPLASH_KEY")

# === Глобальные переменные ===
bot = telebot.TeleBot(BOT_TOKEN)
scheduler = BackgroundScheduler()
app = Flask(__name__)

# Файлы
HISTORY_FILE = "user_history.json"
QUEUE_FILE = "daily_queue.json"
CACHE_FILE = "image_cache.json"
POSTS_LOG_FILE = "published_posts.json"

# Загрузка данных
def load_json(filename, default):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

user_history = load_json(HISTORY_FILE, {})
daily_queue = load_json(QUEUE_FILE, [])
image_cache = load_json(CACHE_FILE, {})
published_posts = load_json(POSTS_LOG_FILE, [])

# === КНОПКИ ===
def get_source_keyboard():
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🖼 Unsplash", callback_data="src_unsplash"),
        InlineKeyboardButton("🤖 Сгенерировать через ИИ", callback_data="src_ai")
    )
    return markup

def get_suggestion_buttons():
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("✨ Реалистично", callback_data="suggest_realistic"),
        InlineKeyboardButton("🎨 Аниме", callback_data="suggest_anime")
    )
    markup.row(
        InlineKeyboardButton("🌌 В космосе", callback_data="suggest_space"),
        InlineKeyboardButton("🏰 В замке", callback_data="suggest_castle")
    )
    markup.add(InlineKeyboardButton("🔄 Случайное", callback_data="suggest_random"))
    return markup

def get_choose_photo_keyboard():
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🖼 №1", callback_data="choose_1"),
        InlineKeyboardButton("🖼 №2", callback_data="choose_2")
    )
    markup.row(
        InlineKeyboardButton("🖼 №3", callback_data="choose_3"),
        InlineKeyboardButton("🖼 №4", callback_data="choose_4")
    )
    return markup

def get_action_menu():
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🔁 Похожее", callback_data="action_similar"),
        InlineKeyboardButton("🎨 Стиль", callback_data="action_style")
    )
    markup.row(
        InlineKeyboardButton("✏️ Промпт", callback_data="action_prompt"),
        InlineKeyboardButton("📥 В ЛС", callback_data="action_save")
    )
    return markup

# === УЛУЧШЕНИЕ ПРОМПТА ===
def enhance_prompt(prompt, style=""):
    base = prompt
    if "реалистично" in style:
        base += ", фотореализм, 8K, детализировано"
    elif "аниме" in style:
        base += ", в стиле аниме, Studio Ghibli"
    elif "космосе" in style:
        base += ", в космосе, галактика, неон"
    elif "замке" in style:
        base += ", в старинном замке, магия, средневековье"
    elif "random" in style:
        extras = [", кинематографично", ", акварель", ", цифровая живопись", ", минимализм"]
        base += random.choice(extras)
    return base

# === ПОИСК ФОТО (ТОЛЬКО UNSPLASH) ===
def search_unsplash(query, page=1):
    if not UNSPLASH_KEY:
        return []
        
    url = "https://api.unsplash.com/search/photos"
    headers = {"Authorization": f"Client-ID {UNSPLASH_KEY}"}
    params = {"query": query, "per_page": 6, "page": page}
    r = requests.get(url, headers=headers, params=params)
    return r.json().get("results", []) if r.status_code == 200 else []

# === ГЕНЕРАЦИЯ ЧЕРЕЗ HUGGING FACE ===
def generate_hf_image(prompt):
    if not HF_API_KEY:
        return None
    if prompt in image_cache:
        return image_cache[prompt]

    API_URL = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0"
    headers = {"Authorization": f"Bearer {HF_API_KEY}"}

    try:
        print(f"Запрос к Hugging Face: {prompt}")
        response = requests.post(API_URL, headers=headers, json={"inputs": prompt})
        
        # Если модель "спит" — ждём 10 сек и пробуем снова
        if response.status_code == 503:
            print("Модель спит... ждём 10 сек")
            time.sleep(10)
            response = requests.post(API_URL, headers=headers, json={"inputs": prompt})
        
        if response.status_code == 200:
            # Конвертируем в JPEG и отправляем через Telegram
            img = Image.open(io.BytesIO(response.content))
            bio = io.BytesIO()
            bio.name = 'image.jpg'
            img.save(bio, 'JPEG')
            bio.seek(0)
            
            # Отправляем в Telegram для получения file_id
            sent = bot.send_photo(OWNER_ID, bio)
            file_id = sent.photo[-1].file_id
            url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_id}"
            
            # Сохраняем в кэш
            image_cache[prompt] = url
            save_json(CACHE_FILE, image_cache)
            return url
    except Exception as e:
        print("Ошибка Hugging Face:", e)
    
    return None

# === ОТПРАВКА 6 ФОТО (ТОЛЬКО UNSPLASH) ===
@bot.message_handler(commands=['start'])
def start(message):
    cid = message.chat.id
    bot.send_message(cid, "Отправь запрос, например: *кошки в очках*", parse_mode="Markdown")
    bot.send_message(cid, "Выбери источник:", reply_markup=get_source_keyboard())
    user_context[cid] = {"state": "awaiting_query"}

# === ОСНОВНОЙ ЦИКЛ ===
user_context = {}

@bot.message_handler(func=lambda m: True)
def handle_query(message):
    cid = message.chat.id
    query = message.text.strip()
    if len(query) < 2:
        return bot.send_message(cid, "Слишком коротко.")

    # Сохраняем
    if str(cid) not in user_history:
        user_history[str(cid)] = []
    user_history[str(cid)].append(query)
    save_json(HISTORY_FILE, user_history)

    # Показываем фото (только Unsplash)
    images = [(img, "unsplash") for img in search_unsplash(query)]
    
    if not images:
        bot.send_message(cid, "❌ Ничего не найдено. Попробуй другой запрос.")
        return

    for i, (img, src) in enumerate(images[:6]):
        url = img["urls"]["regular"]
        author = img["user"]["name"]
        bot.send_photo(cid, url, caption=f"🖼 {query}\nАвтор: {author}")

    # Меню
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🤖 Сгенерировать через ИИ", callback_data="ai_start"))
    bot.send_message(cid, "Что дальше?", reply_markup=markup)

    user_context[cid] = {"last_query": query}

# === ГЕНЕРАЦИЯ ИИ ===
@bot.callback_query_handler(func=lambda c: c.data == "ai_start")
def ai_start(call):
    cid = call.message.chat.id
    ctx = user_context.get(cid, {})
    query = ctx.get("last_query", "искусство")
    bot.edit_message_text(chat_id=cid, message_id=call.message.message_id, text=f"Текущий запрос:\n\n*{query}*", parse_mode="Markdown", reply_markup=get_suggestion_buttons())

@bot.callback_query_handler(func=lambda c: c.data.startswith("suggest_"))
def suggest(call):
    cid = call.message.chat.id
    style = call.data.split("_")[1]
    ctx = user_context.get(cid, {})
    query = ctx.get("last_query", "искусство")
    enhanced = enhance_prompt(query, style)
    user_context[cid]["ai_prompt"] = enhanced

    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("✅ Генерировать", callback_data="ai_gen"),
        InlineKeyboardButton("✏️ Свой", callback_data="ai_custom")
    )
    bot.edit_message_text(chat_id=cid, message_id=call.message.message_id, text=f"Улучшено:\n\n*{enhanced}*", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data == "ai_custom")
def ai_custom(call):
    cid = call.message.chat.id
    msg = bot.edit_message_text(chat_id=cid, message_id=call.message.message_id, text="Введите свой промпт:")
    bot.register_next_step_handler(msg, custom_prompt_step)

def custom_prompt_step(message):
    cid = message.chat.id
    user_context[cid]["ai_prompt"] = message.text.strip()
    ai_generate(cid)

def ai_generate(cid):
    prompt = user_context[cid]["ai_prompt"]
    bot.send_message(cid, "🎨 Генерирую 4 варианта...")

    results = []
    for _ in range(4):
        url = generate_hf_image(prompt)
        if url:
            results.append(url)
        if len(results) == 4:
            break

    if not results:
        return bot.send_message(cid, "❌ Не удалось сгенерировать.")

    # Отправляем
    media = [telebot.types.InputMediaPhoto(results[0], caption=f"🎨 Варианты по запросу:\n{prompt}\nВыбери лучшее:")]
    for url in results[1:]:
        media.append(telebot.types.InputMediaPhoto(url))
    sent = bot.send_media_group(cid, media)
    user_context[cid]["ai_images"] = results
    user_context[cid]["ai_media_ids"] = [m.message_id for m in sent]

    bot.send_message(cid, "Какое нравится?", reply_markup=get_choose_photo_keyboard())

@bot.callback_query_handler(func=lambda c: c.data.startswith("choose_"))
def choose_img(call):
    cid = call.message.chat.id
    num = int(call.data.split("_")[1])
    user_context[cid]["chosen"] = num - 1
    bot.edit_message_text(chat_id=cid, message_id=call.message.message_id, text=f"✅ Выбрано фото №{num}", reply_markup=None)
    bot.send_message(cid, "Действие:", reply_markup=get_action_menu())

# === ДЕЙСТВИЯ ПОСЛЕ ВЫБОРА ===
@bot.callback_query_handler(func=lambda c: c.data == "action_similar")
def similar(call):
    cid = call.message.chat.id
    num = user_context[cid]["chosen"]
    prompt = user_context[cid]["ai_prompt"]
    new_prompt = f"Похожее на предыдущее, но с другим ракурсом: {prompt}"
    user_context[cid]["ai_prompt"] = new_prompt
    ai_generate(cid)

@bot.callback_query_handler(func=lambda c: c.data == "action_save")
def save(call):
    cid = call.message.chat.id
    num = user_context[cid]["chosen"]
    url = user_context[cid]["ai_images"][num]
    bot.send_photo(OWNER_ID, url, caption=f"Сохранено пользователем {cid}")
    bot.answer_callback_query(call.id, "✅ В ЛС!")

# === АВТОПОСТИНГ В КАНАЛ (ТОЛЬКО UNSPLASH) ===
def generate_daily_queue():
    global daily_queue
    all_queries = [q for hist in user_history.values() for q in hist]
    if not all_queries:
        all_queries = ["природа", "кошки", "город"]
    top = [q for q, _ in sorted({q: all_queries.count(q) for q in set(all_queries)}.items(), key=lambda x: -x[1])[:5]]
    daily_queue = [{"query": random.choice(top), "src": "unsplash"} for _ in range(100)]
    save_json(QUEUE_FILE, daily_queue)

def post_one():
    global daily_queue
    if not daily_queue:
        return

    post = daily_queue.pop(0)
    query = post["query"]
    img_url = None
    caption = f"✨ {query}\n\n#авто #подборка"

    try:
        if UNSPLASH_KEY:
            images = search_unsplash(query)
            if images:
                img = random.choice(images)
                img_url = img["urls"]["regular"]
                author = img["user"]["name"]
                caption += f"\nАвтор: {author}"

        if img_url:
            # Отправляем в Telegram
            bot.send_photo(CHANNEL_ID, img_url, caption=caption)
            
            # Логируем для Instagram
            log_post(img_url, caption, "unsplash", query)
            
    except Exception as e:
        print("Ошибка поста:", e)
        daily_queue.append(post)  # Возвращаем в очередь

    save_json(QUEUE_FILE, daily_queue)

# === ФУНКЦИИ ДЛЯ INSTAGRAM ===
def log_post(image_url, caption, source, query):
    """Сохраняет данные для интеграции с Instagram"""
    post_data = {
        "image_url": image_url,
        "caption": caption,
        "source": source,
        "query": query,
        "published_at": datetime.now().isoformat(),
        "instagram_posted": False
    }
    published_posts.append(post_data)
    save_json(POSTS_LOG_FILE, published_posts)

# === ВЕБ-ИНТЕРФЕЙС ДЛЯ n8n ===
@app.route('/instagram-posts')
def get_instagram_posts():
    """Возвращает посты для Instagram (не опубликованные)"""
    pending = [p for p in published_posts if not p["instagram_posted"]]
    return jsonify(pending[:5])  # Только 5 последних

@app.route('/mark-instagram/<int:index>', methods=['POST'])
def mark_as_posted(index):
    """Отмечает пост как опубликованный в Instagram"""
    if 0 <= index < len(published_posts):
        published_posts[index]["instagram_posted"] = True
        save_json(POSTS_LOG_FILE, published_posts)
        return jsonify({"status": "ok"})
    return jsonify({"error": "invalid index"}), 400

# === ЗАПУСК ===
if __name__ == "__main__":
    if OWNER_ID == 0 or not UNSPLASH_KEY:
        print("❗ Установите OWNER_ID и UNSPLASH_KEY")
    else:
        scheduler.add_job(generate_daily_queue, 'cron', hour=0, minute=5)
        scheduler.add_job(post_one, 'interval', minutes=15)
        scheduler.start()

        from threading import Thread
        Thread(target=lambda: app.run(port=10000, debug=False, use_reloader=False)).start()

        print("✅ Бот запущен")
        bot.infinity_polling()
