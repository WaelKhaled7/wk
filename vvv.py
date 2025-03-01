import telebot
import requests
import random
import re
import time
import logging
import threading
import os
import json
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, InlineQueryResultPhoto, InputTextMessageContent, BotCommand
from html import escape
from deep_translator import GoogleTranslator
from bs4 import BeautifulSoup
from functools import lru_cache
from urllib.parse import urljoin

# 🟢 إعدادات البوت
API_KEY = "1624636642:AAG6xhQ3fno7_N6JID_6B_qlKGXddA4IuTQ"
bot = telebot.TeleBot(API_KEY)

# 🟢 المعرفات الثابتة
DEV_ID = "1622270145"
ALLOWED_GROUP_ID = -1001797600488 
DEV_USERNAME = "@WaelKhaled3"
CHANNEL_USERNAME = "@techno_syria"
TECH_GROUP = "@techno_syria1"
MOVIES_CHANNEL = "@movies_techno"
ADMIN_IDS = {int(DEV_ID)}

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
GEMINI_API_KEY = "AIzaSyBg0JhMDyD1oXCQ23kGwy0XPxhr6btZqwg"
OMDB_API_KEY = "5dcfe76e"
OMDB_BASE_URL = "http://www.omdbapi.com/"

# 🟢 تفعيل السجل
logging.basicConfig(filename='bot_errors.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 🟢 قوائم الانتظار والردود العشوائية
WAITING_EMOJIS = ["🎬", "🍿", "🔍", "📝", "🔎", "📺", "💡"]
WAITING_SYRIAN_RESPONSES = [
    "طووول بالك، رح شفلك شي حلو!",
    "لحظة يا زلمة، رح جيبلك شي بجنن!",
    "خليك هون، جايبلك ترشيح بجنن!"
]
IMDB_WAITING = "🎥 طول بالك رح جبلك التفاصيل!"
SYRIAN_RESPONSES = [
    "جربو اذا ماعجبك رجعلي ياه",
    "شوف هاد و ادعيلي!",
    "هلق جبتلك شي بياخد العقل!"
]
RANDOM_RESPONSES = [
    "شوف هاد، بيستاهل تشوفو!",
    "جرب جرب، ما رح تندم!",
    "هاد طلع عشوائي بس بيجنن!"
]
PRIVATE_RESPONSE = "اهلييين، أنا هون للمجموعة بس، تعا جربني هناك!"
INVALID_INPUT_RESPONSE = "ياعيني، هاد مو اسم فيلم، جرب شي جدي!"
SMART_INVALID_RESPONSE = "ياعيني، هاد شي غريب! جرب شي عن الأفلام أو المسلسلات بدل هالكلام العجيب 😂"
INLINE_MIN_CHARS_RESPONSE = "يجب عليك كتابة امثر من 3 احرف لإظهار النتائج"
INLINE_MORE_CHARS_RESPONSE = "اكتب المزيد"
ONLY_PRIVATE_RESPONSE = "<b>هذا الأمر متاح فقط في الخاص</b>\n<i>بسبب الحرق والمصايب، تعا جربني! 🥲</i>"

# 🟢 ذاكرة مؤقتة وقوائم الأوامر المفعلة
user_last_request = {}
user_request_times = {}
suggested_movies = set()
suggested_series = set()
user_count = set()
banned_users = set()
muted_users = set()
enable_all_private = False
inline_cache = {}
omdb_cache = {}
RATE_LIMIT = 5
enabled_commands = {"/imdb", "/spoilermaster", "/actor", "/detective"}

# 🟢 قايمة أسماء شائعة للرفض
COMMON_NAMES = {"أحمد", "محمد", "علي", "حسن", "خالد", "مرحبا", "اسمي", "hello", "hi"}

# 🟢 قائمة أفلام ومسلسلات معروفة للتحقق الداخلي
KNOWN_TITLES = {
    "fight club", "inception", "the matrix", "vikings", "breaking bad", "hannibal", 
    "the walking dead", "interstellar", "pulp fiction", "fast x", "the dark knight", 
    "game of thrones", "stranger things", "dangerous dynasty house of assad"
}

# 🟢 نظام إدارة الذاكرة
def clean_old_messages():
    while True:
        time.sleep(86400)
        user_last_request.clear()
        user_request_times.clear()
        suggested_movies.clear()
        suggested_series.clear()
        inline_cache.clear()
        omdb_cache.clear()
        logging.info("تم تنظيف الذاكرة.")
threading.Thread(target=clean_old_messages, daemon=True).start()

# 🟢 التحقق من السماحية والأدمن
def is_allowed(chat_id):
    return chat_id == int(DEV_ID) or chat_id == ALLOWED_GROUP_ID

def is_admin(user_id):
    return user_id in ADMIN_IDS

# 🟢 فحص إدخال صالح
def is_valid_movie_input(text):
    text = text.strip().lower()
    if not text or text in COMMON_NAMES or len(text) < 3 or re.match(r"^[0-9]+$", text):
        return False
    return True

# 🟢 التحقق الذكي من صلاحية الإدخال
def smart_validate_input(input_text):
    if not is_valid_movie_input(input_text):
        return False
    input_lower = input_text.lower().replace(" ", "")
    if any(input_lower in title.replace(" ", "") for title in KNOWN_TITLES):
        return True
    response = get_gemini_response(f"هل '{input_text}' مرتبط بأفلام أو مسلسلات أو وثائقيات؟ أجب بـ 'نعم' أو 'لا' فقط.", retries=1)
    return response and response.strip().lower() == "نعم"

# 🟢 تنسيق الردود مع ترتيب ودمج <b> و<i>
def format_response(response, keep_english_titles=False):
    if not response:
        return "<b> السيرفر مشغول حالياً</b>"
    
    response = re.sub(r"[\*_\`\[\]#]", "", response)
    response = re.sub(r"^(بالطبع!|إليك\s+|.*أتمنى.*|Here is|Sure|Of course|Behold)", "", response, flags=re.IGNORECASE).strip()
    lines = response.split("\n")
    formatted = []
    current_title = None
    
    for line in lines:
        line = escape(line.strip())
        if re.match(r"^(فيلم|مسلسل|وثائقي|\".*\")", line) or (keep_english_titles and re.match(r"^\w.*$", line.strip())):
            title = re.search(r"\"(.*?)\"", line)
            title = title.group(1) if title else line
            translated_title = title if keep_english_titles else GoogleTranslator(source='auto', target='ar').translate(title)
            formatted.append(f"<b>{translated_title}</b>")
            current_title = translated_title
        else:
            translated = GoogleTranslator(source='auto', target='ar').translate(line) if line.strip() else line
            formatted.append(f"<i>{translated}</i>")
    
    output = []
    for i, line in enumerate(formatted):
        if line.startswith("<b>"):
            if i > 0:
                output.append("")
            output.append(line)
        else:
            output.append(line)
    
    return "\n".join(output)

# 🟢 التحقق من الاتصال
@lru_cache(maxsize=128)
def check_internet_connection():
    try:
        requests.get("https://www.google.com", timeout=10)
        return True
    except requests.RequestException:
        return False

# 🟢 الحصول على رد من Gemini
def get_gemini_response(user_input, retries=3, delay=2):
    if not check_internet_connection():
        logging.error("⚠️ لا يوجد اتصال بالإنترنت.")
        return None
    
    headers = {"Content-Type": "application/json"}
    params = {"key": GEMINI_API_KEY}
    data = {
        "contents": [{"parts": [{"text": user_input}]}],
        "generationConfig": {"temperature": 1, "topP": 0.95, "topK": 40, "maxOutputTokens": 8192}
    }
    
    for attempt in range(retries):
        try:
            response = requests.post(GEMINI_API_URL, headers=headers, params=params, json=data, timeout=10)
            if response.status_code == 200:
                return response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            elif response.status_code == 429:
                logging.error("⚠️ Gemini: الكثير من الطلبات.")
                time.sleep(delay * (attempt + 1))
            else:
                logging.error(f"⚠️ Gemini Error: {response.status_code} - {response.text}")
                time.sleep(delay)
        except Exception as e:
            logging.error(f"⚠️ Gemini Exception (Attempt {attempt + 1}): {e}")
            time.sleep(delay)
    return None

# 🟢 تذييل عشوائي
def get_random_footer():
    return random.choice([f"📢 {CHANNEL_USERNAME}", f"👨‍💻 {DEV_USERNAME}", f"💡 {TECH_GROUP}", f"🎬 {MOVIES_CHANNEL}"])

# 🟢 التحقق من صحة الطلب
def is_valid_request(text):
    keywords = ["فيلم", "مسلسل", "أفلام", "مسلسلات", "دراما", "أكشن", "كوميدي", "رعب", "خيال علمي", "وثائقي"]
    return any(keyword in text.lower() for keyword in keywords)

# 🟢 نظام منع التحايل
def is_rate_limited(user_id):
    current_time = time.time()
    if user_id in user_request_times and current_time - user_request_times[user_id] < RATE_LIMIT:
        return True
    user_request_times[user_id] = current_time
    return False

# 🟢 البحث في OMDb مع تصحيح متقدم
def search_omdb(query):
    corrected_query = correct_spelling(query)
    params = {"apikey": OMDB_API_KEY, "t": corrected_query, "plot": "short", "r": "json"}
    try:
        response = requests.get(OMDB_BASE_URL, params=params, timeout=5)
        result = response.json() if response.status_code == 200 else None
        if result and result.get("Response") == "True":
            omdb_cache[query] = result
            return result
        return None
    except Exception as e:
        logging.error(f"⚠️ OMDb Error: {e}")
        return None

# 🟢 تصحيح إملائي متقدم
def correct_spelling(query):
    movie_titles = [
        "The Godfather", "Inception", "The Matrix", "Vikings", "Breaking Bad", 
        "Hannibal", "The Walking Dead", "Interstellar", "Fight Club", "Pulp Fiction",
        "Fast X", "The Dark Knight", "Game of Thrones", "Stranger Things",
        "Dangerous Dynasty House of Assad"
    ]
    query_lower = query.lower().replace(" ", "")
    for title in movie_titles:
        title_lower = title.lower().replace(" ", "")
        if query_lower in title_lower or sum(c1 == c2 for c1, c2 in zip(query_lower, title_lower)) > len(query_lower) * 0.7:
            return title
    return query

# 🟢 Inline Query محسّنة (3 نتائج متقاربة مع بوسترات)
@bot.inline_handler(func=lambda query: True)
def handle_inline_query(query):
    query_text = query.query.strip()
    
    if len(query_text) < 2:
        result = InlineQueryResultPhoto(
            id=str(random.randint(1, 1000000)),
            photo_url="https://via.placeholder.com/150",
            thumbnail_url="https://via.placeholder.com/150",
            caption=f"<b>{INLINE_MIN_CHARS_RESPONSE}</b>",
            parse_mode="HTML"
        )
        bot.answer_inline_query(query.id, [result], cache_time=1)
        return
    elif len(query_text) == 2:
        result = InlineQueryResultPhoto(
            id=str(random.randint(1, 1000000)),
            photo_url="https://via.placeholder.com/150",
            thumbnail_url="https://via.placeholder.com/150",
            caption=f"<b>{INLINE_MORE_CHARS_RESPONSE}</b>",
            parse_mode="HTML"
        )
        bot.answer_inline_query(query.id, [result], cache_time=1)
        return
    
    query_text = correct_spelling(query_text)
    if not is_valid_movie_input(query_text):
        result = InlineQueryResultPhoto(
            id=str(random.randint(1, 1000000)),
            photo_url="https://via.placeholder.com/150",
            thumbnail_url="https://via.placeholder.com/150",
            caption=INVALID_INPUT_RESPONSE,
            parse_mode="HTML"
        )
        bot.answer_inline_query(query.id, [result], cache_time=1)
        return
    
    results = []
    seen_ids = set()
    
    # البحث الأساسي
    response = search_omdb(query_text)
    if response and response.get("Response") == "True":
        title = response.get("Title")
        imdb_id = response.get("imdbID")
        poster_url = response.get("Poster", "https://via.placeholder.com/150") if response.get("Poster") != "N/A" else "https://via.placeholder.com/150"
        imdb_url = f"https://www.imdb.com/title/{imdb_id}/"
        
        reply_text = f"<b>{title}</b>"
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("📄 IMDb", url=imdb_url))
        
        result = InlineQueryResultPhoto(
            id=imdb_id,
            photo_url=poster_url,
            thumbnail_url=poster_url,
            caption=reply_text[:1024],
            parse_mode="HTML",
            reply_markup=markup
        )
        results.append(result)
        seen_ids.add(imdb_id)
    
    # إضافة نتائج قريبة (حتى 3)
    movie_titles = [
        "The Godfather", "Inception", "The Matrix", "Vikings", "Breaking Bad", 
        "Hannibal", "The Walking Dead", "Interstellar", "Fight Club", "Pulp Fiction",
        "Fast X", "The Dark Knight", "Game of Thrones", "Stranger Things",
        "Dangerous Dynasty House of Assad"
    ]
    query_lower = query_text.lower().replace(" ", "")
    for title in movie_titles:
        if len(results) >= 3:
            break
        title_lower = title.lower().replace(" ", "")
        if query_lower in title_lower and title not in [r.caption.replace("<b>", "").replace("</b>", "") for r in results]:
            response = search_omdb(title)
            if response and response.get("Response") == "True":
                title = response.get("Title")
                imdb_id = response.get("imdbID")
                poster_url = response.get("Poster", "https://via.placeholder.com/150") if response.get("Poster") != "N/A" else "https://via.placeholder.com/150"
                imdb_url = f"https://www.imdb.com/title/{imdb_id}/"
                
                if imdb_id not in seen_ids:
                    reply_text = f"<b>{title}</b>"
                    markup = InlineKeyboardMarkup()
                    markup.add(InlineKeyboardButton("📄 IMDb", url=imdb_url))
                    
                    result = InlineQueryResultPhoto(
                        id=imdb_id,
                        photo_url=poster_url,
                        thumbnail_url=poster_url,
                        caption=reply_text[:1024],
                        parse_mode="HTML",
                        reply_markup=markup
                    )
                    results.append(result)
                    seen_ids.add(imdb_id)
    
    inline_cache[query_text] = results
    try:
        bot.answer_inline_query(query.id, results[:3], cache_time=1, is_personal=False)  # عرض 3 نتائج بشكل عرضي
    except Exception as e:
        logging.error(f"⚠️ Inline Query Error: {e}")

# 🟢 /random محسّن
@bot.message_handler(commands=['random'])
def handle_random(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if user_id in banned_users or user_id in muted_users:
        bot.reply_to(message, "<b>⚠️ تم حظرك أو كتمك!</b>", parse_mode="HTML")
        return
    
    user_count.add(user_id)
    if not is_allowed(chat_id) and "/random" not in enabled_commands and not is_admin(user_id):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🌟 جربني في المجموعة", url="https://t.me/wk_paid"))
        markup.add(InlineKeyboardButton("المطور", url=f"https://t.me/{DEV_USERNAME[1:]}"))
        markup.add(InlineKeyboardButton("قناة البوت", url=f"https://t.me/{CHANNEL_USERNAME[1:]}"))
        bot.reply_to(message, PRIVATE_RESPONSE, parse_mode="HTML", reply_markup=markup)
        return
    
    if is_rate_limited(user_id):
        bot.reply_to(message, f"<b>⚠️ استنى {RATE_LIMIT} 5 ثواني انتَ تُكسر مِن الطلبات 😒!</b>", parse_mode="HTML")
        return
    
    waiting_message = bot.reply_to(message, random.choice(WAITING_EMOJIS))
    movie_response = get_gemini_response(f"أعطني توصية لفيلم عشوائي مع قصة مختصرة (غير {list(suggested_movies)[-1] if suggested_movies else ''})")
    series_response = get_gemini_response(f"أعطني توصية لمسلسل عشوائي مع قصة مختصرة (غير {list(suggested_series)[-1] if suggested_series else ''})")
    bot.delete_message(chat_id, waiting_message.message_id)
    
    if not movie_response or not series_response:
        bot.reply_to(message, "<b>⚡ السيرفر مشغول حالياً</b>", parse_mode="HTML")
        return
    
    formatted_movie = format_response(movie_response, keep_english_titles=True)
    formatted_series = format_response(series_response, keep_english_titles=True)
    suggested_movies.add(movie_response.split("\n")[0])
    suggested_series.add(series_response.split("\n")[0])
    
    reply_text = (
        f"<b>{random.choice(RANDOM_RESPONSES)}</b>\n\n"
        f"{formatted_movie}\n\n"
        f"{formatted_series}\n\n"
        f"<i>{get_random_footer()}</i>"
    )
    bot.reply_to(message, reply_text, parse_mode="HTML")

# 🟢 /suggest محسّن مع التحقق الذكي
@bot.message_handler(commands=['suggest'])
def handle_suggest(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if user_id in banned_users or user_id in muted_users:
        bot.reply_to(message, "<b>⚠️ تم حظرك أو كتمك!</b>", parse_mode="HTML")
        return
    
    user_count.add(user_id)
    if not is_allowed(chat_id) and "/suggest" not in enabled_commands and not is_admin(user_id):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🌟 جربني في المجموعة", url="https://t.me/wk_paid"))
        markup.add(InlineKeyboardButton("المطور", url=f"https://t.me/{DEV_USERNAME[1:]}"))
        markup.add(InlineKeyboardButton("قناة البوت", url=f"https://t.me/{CHANNEL_USERNAME[1:]}"))
        bot.reply_to(message, PRIVATE_RESPONSE, parse_mode="HTML", reply_markup=markup)
        return
    
    if is_rate_limited(user_id):
        bot.reply_to(message, f"<b>⚠️ استنى {RATE_LIMIT} 5 ثواني انتَ تُكسر مِن الطلبات 😒!</b>", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1 or not is_valid_request(text[1]):
        bot.reply_to(message, "<b>⚠️ حدد نوع التوصية</b>\n<i>مثال: /suggest رعب</i>", parse_mode="HTML")
        return
    
    genre = text[1].strip()
    if not smart_validate_input(genre):
        bot.reply_to(message, SMART_INVALID_RESPONSE, parse_mode="HTML")
        return
    
    waiting_message = bot.reply_to(message, random.choice(WAITING_SYRIAN_RESPONSES))
    response = get_gemini_response(f"أعطني توصية لفيلم ومسلسل من نوع {genre} مع قصة مختصرة")
    bot.delete_message(chat_id, waiting_message.message_id)
    
    if not response:
        bot.reply_to(message, "<b>⚡ السيرفر مشغول حالياً</b>", parse_mode="HTML")
        return
    
    formatted_response = format_response(response, keep_english_titles=True)
    reply_text = f"<b>{random.choice(SYRIAN_RESPONSES)}</b>\n\n{formatted_response}\n\n<i>{get_random_footer()}</i>"
    bot.reply_to(message, reply_text, parse_mode="HTML")

# 🟢 /imdb محسّن
@bot.message_handler(commands=['imdb'])
def handle_imdb(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if user_id in banned_users or user_id in muted_users:
        bot.reply_to(message, "<b>⚠️ تم حظرك أو كتمك!</b>", parse_mode="HTML")
        return
    
    user_count.add(user_id)
    if is_rate_limited(user_id):
        bot.reply_to(message, f"<b>⚠️ استنى {RATE_LIMIT} 5 ثواني انتَ تُكسر مِن الطلبات 😒!</b>", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ حدد اسم الفيلم</b>\n<i>مثال: /imdb Fast X</i>", parse_mode="HTML")
        return
    
    query = text[1].strip()
    waiting_message = bot.reply_to(message, IMDB_WAITING)
    
    try:
        response = search_omdb(query)
        if not response or response.get("Response") != "True":
            movie_titles = [
                "The Godfather", "Inception", "The Matrix", "Vikings", "Breaking Bad", 
                "Hannibal", "The Walking Dead", "Interstellar", "Fight Club", "Pulp Fiction",
                "Fast X", "The Dark Knight", "Game of Thrones", "Stranger Things",
                "Dangerous Dynasty House of Assad"
            ]
            results = []
            query_lower = query.lower().replace(" ", "")
            for title in movie_titles:
                title_lower = title.lower().replace(" ", "")
                if query_lower in title_lower or sum(c1 == c2 for c1, c2 in zip(query_lower, title_lower)) > len(query_lower) * 0.7:
                    alt_response = search_omdb(title)
                    if alt_response and alt_response.get("Response") == "True":
                        results.append(alt_response)
                        break
            
            if not results:
                bot.delete_message(chat_id, waiting_message.message_id)
                bot.reply_to(message, "<b>⚡ ما لقيت شي، جرب اسم تاني!</b>", parse_mode="HTML")
                return
            
            response = results[0]
        
        title = response.get("Title")
        plot = GoogleTranslator(source='auto', target='ar').translate(response.get("Plot", "غير متوفر"))
        year = response.get("Year", "غير معروف")
        rating = response.get("imdbRating", "غير معروف")
        genre = GoogleTranslator(source='auto', target='ar').translate(response.get("Genre", "غير معروف"))
        runtime = response.get("Runtime", "غير معروف")
        director = GoogleTranslator(source='auto', target='ar').translate(response.get("Director", "غير معروف"))
        actors = response.get("Actors", "غير معروف")
        imdb_id = response.get("imdbID")
        poster_url = response.get("Poster", "https://via.placeholder.com/150") if response.get("Poster") != "N/A" else "https://via.placeholder.com/150"
        imdb_url = f"https://www.imdb.com/title/{imdb_id}/"
        
        reply_text = (
            f"<b>{title}</b>\n"
            f"<i>{plot}</i>\n"
            f"<i>📅 السنة: {year}</i>\n"
            f"<i>⭐ التقييم: {rating}/10</i>\n"
            f"<i>🎭 النوع: {genre}</i>\n"
            f"<i>⏱️ المدة: {runtime}</i>\n"
            f"<i>🎥 الإخراج: {director}</i>\n"
            f"<i>🌟 البطولة: {actors}</i>\n\n"
            f"<i>{get_random_footer()}</i>"
        )
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("📄 صفحة IMDb", url=imdb_url))
        
        bot.delete_message(chat_id, waiting_message.message_id)
        bot.send_photo(chat_id, poster_url, caption=reply_text[:1024], parse_mode="HTML", reply_markup=markup)
    except Exception as e:
        logging.error(f"⚠️ IMDb Error: {e}")
        bot.delete_message(chat_id, waiting_message.message_id)
        bot.reply_to(message, "<b>⚠️ خطأ، جرب لاحقاً!</b>", parse_mode="HTML")

# 🟢 أوامر Gemini مع التحقق الذكي
@bot.message_handler(commands=['actor'])
def handle_actor(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if user_id in banned_users or user_id in muted_users:
        bot.reply_to(message, "<b>⚠️ تم حظرك أو كتمك!</b>", parse_mode="HTML")
        return
    
    user_count.add(user_id)
    if not is_allowed(chat_id) and "/actor" not in enabled_commands and not is_admin(user_id):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🌟 جربني في المجموعة", url="https://t.me/wk_paid"))
        markup.add(InlineKeyboardButton("المطور", url=f"https://t.me/{DEV_USERNAME[1:]}"))
        markup.add(InlineKeyboardButton("قناة البوت", url=f"https://t.me/{CHANNEL_USERNAME[1:]}"))
        bot.reply_to(message, PRIVATE_RESPONSE, parse_mode="HTML", reply_markup=markup)
        return
    
    if is_rate_limited(user_id):
        bot.reply_to(message, f"<b>⚠️ استنى {RATE_LIMIT} 5 ثواني انتَ تُكسر مِن الطلبات 😒!</b>", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ حدد اسم الممثل</b>\n<i>مثال: /actor Tom Hanks</i>", parse_mode="HTML")
        return
    
    actor = text[1].strip()
    if not smart_validate_input(actor):
        bot.reply_to(message, SMART_INVALID_RESPONSE, parse_mode="HTML")
        return
    
    waiting_message = bot.reply_to(message, random.choice(WAITING_EMOJIS))
    response = get_gemini_response(f"أعطني قائمة بأفضل أفلام أو مسلسلات الممثل {actor} مع قصة مختصرة")
    bot.delete_message(chat_id, waiting_message.message_id)
    
    if not response:
        bot.reply_to(message, "<b>⚡ السيرفر مشغول أو الممثل غير موجود!</b>", parse_mode="HTML")
        return
    
    formatted_response = format_response(response, keep_english_titles=True)
    reply_text = f"<b>📌 أعمال {actor}:</b>\n\n{formatted_response}\n\n<i>{get_random_footer()}</i>"
    bot.reply_to(message, reply_text, parse_mode="HTML")

@bot.message_handler(commands=['mindreader'])
def handle_mindreader(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if user_id in banned_users or user_id in muted_users:
        bot.reply_to(message, "<b>⚠️ تم حظرك أو كتمك!</b>", parse_mode="HTML")
        return
    
    user_count.add(user_id)
    if not is_allowed(chat_id) and "/mindreader" not in enabled_commands and not is_admin(user_id):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🌟 جربني في المجموعة", url="https://t.me/wk_paid"))
        markup.add(InlineKeyboardButton("المطور", url=f"https://t.me/{DEV_USERNAME[1:]}"))
        markup.add(InlineKeyboardButton("قناة البوت", url=f"https://t.me/{CHANNEL_USERNAME[1:]}"))
        bot.reply_to(message, PRIVATE_RESPONSE, parse_mode="HTML", reply_markup=markup)
        return
    
    if is_rate_limited(user_id):
        bot.reply_to(message, f"<b>⚠️ استنى {RATE_LIMIT} 5 ثواني انتَ تُكسر مِن الطلبات 😒!</b>", parse_mode="HTML")
        return
    
    questions = [
        "<i>1. نوع الفيلم المفضل؟ (أكشن، كوميدي...)</i>",
        "<i>2. قصير أو طويل؟</i>",
        "<i>3. مزاجك اليوم؟ (سعيد، حزين...)</i>"
    ]
    waiting_message = bot.reply_to(message, "<b>🧠 بخمنلك فيلم!</b>\n\n" + "\n".join(questions), parse_mode="HTML")
    bot.register_next_step_handler(waiting_message, process_mindreader_answers)

def process_mindreader_answers(message):
    chat_id = message.chat.id
    answers = message.text.split("\n")
    if len(answers) != 3:
        bot.reply_to(message, "<b>⚠️ جاوب على كل الـ 3 أسئلة!</b>", parse_mode="HTML")
        return
    
    prompt = f"بناءً على:\n1. نوع الفيلم: {answers[0]}\n2. قصير/طويل: {answers[1]}\n3. المزاج: {answers[2]}\nأعطني توصية فيلم مع قصة مختصرة بالعربي."
    response = get_gemini_response(prompt)
    if not response:
        bot.reply_to(message, "<b>⚡ السيرفر مشغول حالياً</b>", parse_mode="HTML")
        return
    
    formatted_response = format_response(response, keep_english_titles=True)
    reply_text = f"<b>🧠 توقعتلك:</b>\n\n{formatted_response}\n\n<i>{get_random_footer()}</i>"
    bot.reply_to(message, reply_text, parse_mode="HTML")

@bot.message_handler(commands=['detective'])
def handle_detective(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if user_id in banned_users or user_id in muted_users:
        bot.reply_to(message, "<b>⚠️ تم حظرك أو كتمك!</b>", parse_mode="HTML")
        return
    
    user_count.add(user_id)
    
    # التحقق إذا كان في المجموعة
    if is_allowed(chat_id) and not is_admin(user_id):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🌟 جربني في الخاص", url=f"https://t.me/{bot.get_me().username}"))
        bot.reply_to(message, ONLY_PRIVATE_RESPONSE, parse_mode="HTML", reply_markup=markup)
        return
    
    if is_rate_limited(user_id):
        bot.reply_to(message, f"<b>⚠️ استنى {RATE_LIMIT} 5 ثواني انتَ تُكسر مِن الطلبات 😒!</b>", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ حدد اسم الفيلم</b>\n<i>مثال: /detective Inception</i>", parse_mode="HTML")
        return
    
    movie = text[1].strip()
    if not smart_validate_input(movie):
        bot.reply_to(message, SMART_INVALID_RESPONSE, parse_mode="HTML")
        return
    
    waiting_message = bot.reply_to(message, random.choice(WAITING_EMOJIS))
    response = get_gemini_response(f"اشرح نهاية الفيلم أو المسلسل أو الوثائقي {movie} بطريقة عبقرية وساخرة")
    bot.delete_message(chat_id, waiting_message.message_id)
    
    if not response:
        bot.reply_to(message, "<b>⚡ السيرفر مشغول أو العنوان غير موجود!</b>", parse_mode="HTML")
        return
    
    formatted_response = format_response(response, keep_english_titles=True)
    reply_text = f"<b>🔍 تحليل نهاية {movie}:</b>\n\n{formatted_response}\n\n<i>{get_random_footer()}</i>"
    bot.reply_to(message, reply_text, parse_mode="HTML")

@bot.message_handler(commands=['plotwist'])
def handle_plotwist(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if user_id in banned_users or user_id in muted_users:
        bot.reply_to(message, "<b>⚠️ تم حظرك أو كتمك!</b>", parse_mode="HTML")
        return
    
    user_count.add(user_id)
    if not is_allowed(chat_id) and "/plotwist" not in enabled_commands and not is_admin(user_id):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🌟 جربني في المجموعة", url="https://t.me/wk_paid"))
        markup.add(InlineKeyboardButton("المطور", url=f"https://t.me/{DEV_USERNAME[1:]}"))
        markup.add(InlineKeyboardButton("قناة البوت", url=f"https://t.me/{CHANNEL_USERNAME[1:]}"))
        bot.reply_to(message, PRIVATE_RESPONSE, parse_mode="HTML", reply_markup=markup)
        return
    
    if is_rate_limited(user_id):
        bot.reply_to(message, f"<b>⚠️ استنى {RATE_LIMIT} 5 ثواني انتَ تُكسر مِن الطلبات 😒!</b>", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ حدد اسم الفيلم</b>\n<i>مثال: /plotwist The Dark Knight</i>", parse_mode="HTML")
        return
    
    movie = text[1].strip()
    if not smart_validate_input(movie):
        bot.reply_to(message, SMART_INVALID_RESPONSE, parse_mode="HTML")
        return
    
    waiting_message = bot.reply_to(message, random.choice(WAITING_EMOJIS))
    response = get_gemini_response(f"ضع نهاية جديدة ومجنونة للفيلم أو المسلسل أو الوثائقي {movie}")
    bot.delete_message(chat_id, waiting_message.message_id)
    
    if not response:
        bot.reply_to(message, "<b>⚡ السيرفر مشغول أو العنوان غير موجود!</b>", parse_mode="HTML")
        return
    
    formatted_response = format_response(response, keep_english_titles=True)
    reply_text = f"<b>🌀 نهاية جديدة لـ {movie}:</b>\n\n{formatted_response}\n\n<i>{get_random_footer()}</i>"
    bot.reply_to(message, reply_text, parse_mode="HTML")

@bot.message_handler(commands=['aiwriter'])
def handle_aiwriter(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if user_id in banned_users or user_id in muted_users:
        bot.reply_to(message, "<b>⚠️ تم حظرك أو كتمك!</b>", parse_mode="HTML")
        return
    
    user_count.add(user_id)
    if not is_allowed(chat_id) and "/aiwriter" not in enabled_commands and not is_admin(user_id):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🌟 جربني في المجموعة", url="https://t.me/wk_paid"))
        markup.add(InlineKeyboardButton("المطور", url=f"https://t.me/{DEV_USERNAME[1:]}"))
        markup.add(InlineKeyboardButton("قناة البوت", url=f"https://t.me/{CHANNEL_USERNAME[1:]}"))
        bot.reply_to(message, PRIVATE_RESPONSE, parse_mode="HTML", reply_markup=markup)
        return
    
    if is_rate_limited(user_id):
        bot.reply_to(message, f"<b>⚠️ استنى {RATE_LIMIT} 5 ثواني انتَ تُكسر مِن الطلبات 😒!</b>", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ حدد تفاصيل الفيلم</b>\n<i>مثال: /aiwriter أكشن مستقبلي</i>", parse_mode="HTML")
        return
    
    details = text[1].strip()
    if not smart_validate_input(details):
        bot.reply_to(message, SMART_INVALID_RESPONSE, parse_mode="HTML")
        return
    
    waiting_message = bot.reply_to(message, random.choice(WAITING_EMOJIS))
    response = get_gemini_response(f"أنشئ حبكة فيلم بناءً على: {details}")
    bot.delete_message(chat_id, waiting_message.message_id)
    
    if not response:
        bot.reply_to(message, "<b>⚡ السيرفر مشغول حالياً</b>", parse_mode="HTML")
        return
    
    formatted_response = format_response(response, keep_english_titles=True)
    reply_text = f"<b>🎬 حبكة الفيلم:</b>\n\n{formatted_response}\n\n<i>{get_random_footer()}</i>"
    bot.reply_to(message, reply_text, parse_mode="HTML")

@bot.message_handler(commands=['realityshift'])
def handle_realityshift(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if user_id in banned_users or user_id in muted_users:
        bot.reply_to(message, "<b>⚠️ تم حظرك أو كتمك!</b>", parse_mode="HTML")
        return
    
    user_count.add(user_id)
    if not is_allowed(chat_id) and "/realityshift" not in enabled_commands and not is_admin(user_id):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🌟 جربني في المجموعة", url="https://t.me/wk_paid"))
        markup.add(InlineKeyboardButton("المطور", url=f"https://t.me/{DEV_USERNAME[1:]}"))
        markup.add(InlineKeyboardButton("قناة البوت", url=f"https://t.me/{CHANNEL_USERNAME[1:]}"))
        bot.reply_to(message, PRIVATE_RESPONSE, parse_mode="HTML", reply_markup=markup)
        return
    
    if is_rate_limited(user_id):
        bot.reply_to(message, f"<b>⚠️ استنى {RATE_LIMIT} 5 ثواني انتَ تُكسر مِن الطلبات 😒!</b>", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ حدد حدثاً</b>\n<i>مثال: /realityshift تخاصمت مع صديق</i>", parse_mode="HTML")
        return
    
    event = text[1].strip()
    if not smart_validate_input(event):
        bot.reply_to(message, SMART_INVALID_RESPONSE, parse_mode="HTML")
        return
    
    waiting_message = bot.reply_to(message, random.choice(WAITING_EMOJIS))
    response = get_gemini_response(f"حول هذا الحدث إلى فيلم هوليوودي: {event}")
    bot.delete_message(chat_id, waiting_message.message_id)
    
    if not response:
        bot.reply_to(message, "<b>⚡ السيرفر مشغول حالياً</b>", parse_mode="HTML")
        return
    
    formatted_response = format_response(response, keep_english_titles=True)
    reply_text = f"<b>🎭 فيلمك الهوليوودي:</b>\n\n{formatted_response}\n\n<i>{get_random_footer()}</i>"
    bot.reply_to(message, reply_text, parse_mode="HTML")

@bot.message_handler(commands=['spoilermaster'])
def handle_spoilermaster(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if user_id in banned_users or user_id in muted_users:
        bot.reply_to(message, "<b>⚠️ تم حظرك أو كتمك!</b>", parse_mode="HTML")
        return
    
    user_count.add(user_id)
    
    # التحقق إذا كان في المجموعة
    if is_allowed(chat_id) and not is_admin(user_id):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🌟 جربني في الخاص", url=f"https://t.me/{bot.get_me().username}"))
        bot.reply_to(message, ONLY_PRIVATE_RESPONSE, parse_mode="HTML", reply_markup=markup)
        return
    
    if is_rate_limited(user_id):
        bot.reply_to(message, f"<b>⚠️ استنى {RATE_LIMIT} 5 ثواني انتَ تُكسر مِن الطلبات 😒!</b>", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ حدد اسم الفيلم</b>\n<i>مثال: /spoilermaster Fight Club</i>", parse_mode="HTML")
        return
    
    movie = text[1].strip()
    if not smart_validate_input(movie):
        bot.reply_to(message, SMART_INVALID_RESPONSE, parse_mode="HTML")
        return
    
    waiting_message = bot.reply_to(message, random.choice(WAITING_EMOJIS))
    response = get_gemini_response(f"قم بحرق الفيلم أو المسلسل أو الوثائقي {movie} بأسلوب عامي سوري")
    bot.delete_message(chat_id, waiting_message.message_id)
    
    if not response:
        bot.reply_to(message, "<b>⚡ السيرفر مشغول أو العنوان غير موجود!</b>", parse_mode="HTML")
        return
    
    formatted_response = format_response(response, keep_english_titles=True)
    initial_response = f"<b>تم حرق {movie}:</b>\n\n<i>بالاسلوب الي طلبتو غيرو ياعيوني؟ </i>\n\n{formatted_response}"
    
    reply_text = f"{initial_response}\n\n<i>{get_random_footer()}</i>"
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("حرق درامي 🪄", callback_data=f"spoil_dramatic:{movie}"),
        InlineKeyboardButton("حرق سوري 😂", callback_data=f"spoil_syrian:{movie}"),
        InlineKeyboardButton("حرق ساخر 🤦🏻‍♂️", callback_data=f"spoil_sarcastic:{movie}")
    )
    bot.reply_to(message, reply_text, parse_mode="HTML", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("spoil_"))
def handle_spoiler_callback(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    if user_id in banned_users or user_id in muted_users:
        bot.answer_callback_query(call.id, "تم حظرك أو كتمك!")
        return
    
    if is_rate_limited(user_id):
        bot.answer_callback_query(call.id, f"استنى {RATE_LIMIT} 5 ثواني انتَ تُكسر مِن الطلبات 😒!")
        return
    
    style, movie = call.data.split(":", 1)
    if style == "spoil_dramatic":
        prompt = f"حرق الفيلم أو المسلسل أو الوثائقي {movie} بأسلوب درامي مؤثر"
    elif style == "spoil_syrian":
        prompt = f"حرق الفيلم أو المسلسل أو الوثائقي {movie} بأسلوب عامي سوري"
    elif style == "spoil_sarcastic":
        prompt = f"حرق الفيلم أو المسلسل أو الوثائقي {movie} بأسلوب ساخر"
    
    response = get_gemini_response(prompt)
    if not response:
        bot.edit_message_text("<b>⚡ السيرفر مشغول حالياً</b>", chat_id, call.message.message_id, parse_mode="HTML")
        bot.answer_callback_query(call.id, "السيرفر مشغول!")
        return
    
    formatted_response = format_response(response, keep_english_titles=True)
    reply_text = f"<b>🔥 حرق {movie} ({style.split('_')[1]}):</b>\n\n{formatted_response}\n\n<i>{get_random_footer()}</i>"
    bot.edit_message_text(reply_text, chat_id, call.message.message_id, parse_mode="HTML")
    bot.answer_callback_query(call.id, "تم تحديث الحرق!")

# 🟢 أمر خارق للمطور: /super_scan
@bot.message_handler(commands=['super_scan'])
def handle_super_scan(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "<b>⚠️ هذا للمطورين فقط!</b>", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ حدد النص أو الرابط</b>\n<i>مثال: /super_scan https://example.com أو /super_scan نص للتحليل</i>", parse_mode="HTML")
        return
    
    input_data = text[1].strip()
    waiting_message = bot.reply_to(message, "<b>🔬 جاري الفحص الخارق...</b>", parse_mode="HTML")
    
    try:
        if input_data.startswith("http"):
            # فحص رابط
            response = requests.get(input_data, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            title = soup.title.string if soup.title else "غير معروف"
            meta_desc = soup.find("meta", {"name": "description"})
            description = meta_desc["content"] if meta_desc else "غير متوفر"
            links = len(soup.find_all("a"))
            images = len(soup.find_all("img"))
            
            reply_text = (
                f"<b>🔗 فحص الرابط: {input_data}</b>\n\n"
                f"<i>العنوان: {title}</i>\n"
                f"<i>الوصف: {description}</i>\n"
                f"<i>عدد الروابط: {links}</i>\n"
                f"<i>عدد الصور: {images}</i>\n\n"
                f"<i>{get_random_footer()}</i>"
            )
        else:
            # تحليل نص
            response = get_gemini_response(f"قم بتحليل النص التالي واستخرج المعلومات المهمة: {input_data}")
            if not response:
                bot.delete_message(message.chat.id, waiting_message.message_id)
                bot.reply_to(message, "<b>⚡ فشل التحليل، جرب لاحقاً!</b>", parse_mode="HTML")
                return
            
            formatted_response = format_response(response)
            reply_text = (
                f"<b>📝 تحليل النص:</b>\n\n"
                f"{formatted_response}\n\n"
                f"<i>{get_random_footer()}</i>"
            )
        
        bot.delete_message(message.chat.id, waiting_message.message_id)
        bot.reply_to(message, reply_text, parse_mode="HTML")
    except Exception as e:
        logging.error(f"⚠️ Super Scan Error: {e}")
        bot.delete_message(message.chat.id, waiting_message.message_id)
        bot.reply_to(message, "<b>⚠️ خطأ في الفحص، جرب لاحقاً!</b>", parse_mode="HTML")

# 🟢 /wk (لوحة المطور مع الأمر الجديد)
@bot.message_handler(commands=['wk'])
def handle_admin_panel(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "<b>⚠️ هذا للمطورين فقط!</b>", parse_mode="HTML")
        return
    
    help_text = (
        "<b>أوامر المطور:</b>\n\n"
        "<i>/broadcast [نص]</i> - إرسال بث.\n"
        "<i>/stats</i> - إحصائيات البوت.\n"
        "<i>/clear</i> - مسح الذاكرة.\n"
        "<i>/ban_user [id]</i> - حظر مستخدم.\n"
        "<i>/unban_user [id]</i> - رفع الحظر.\n"
        "<i>/mute [id]</i> - كتم مستخدم.\n"
        "<i>/unmute [id]</i> - رفع الكتم.\n"
        "<i>/check_user [id]</i> - فحص حالة.\n"
        "<i>/enable_all</i> - تفعيل الأوامر في الخاص لساعة.\n"
        "<i>/restart</i> - إعادة تشغيل.\n"
        "<i>/log</i> - آخر 10 أخطاء.\n"
        "<i>/toggle_command [command] [enable/disable]</i> - تفعيل/إلغاء أمر.\n"
        "<i>/add_admin [id]</i> - إضافة مطور.\n"
        "<i>/super_scan [نص/رابط]</i> - فحص خارق للروابط أو النصوص.\n"
        f"<i>{get_random_footer()}</i>"
    )
    bot.reply_to(message, help_text, parse_mode="HTML")

# 🟢 أوامر المطور
@bot.message_handler(commands=['broadcast'])
def handle_broadcast(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "<b>⚠️ للمطورين فقط!</b>", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ أدخل نص البث</b>\n<i>مثال: /broadcast تحديث جديد</i>", parse_mode="HTML")
        return
    
    broadcast_msg = text[1]
    waiting_message = bot.reply_to(message, "<b>📢 جاري البث...</b>", parse_mode="HTML")
    for user in user_count:
        try:
            bot.send_message(user, f"<b>رسالة من المطور:</b>\n\n<i>{broadcast_msg}</i>", parse_mode="HTML")
        except Exception as e:
            logging.error(f"⚠️ Broadcast Error for {user}: {e}")
    try:
        bot.send_message(ALLOWED_GROUP_ID, f"<b>رسالة من المطور:</b>\n\n<i>{broadcast_msg}</i>", parse_mode="HTML")
    except Exception as e:
        logging.error(f"⚠️ Broadcast Error for group: {e}")
    
    bot.delete_message(message.chat.id, waiting_message.message_id)
    bot.reply_to(message, "<b>✅ تم البث!</b>", parse_mode="HTML")

@bot.message_handler(commands=['stats'])
def handle_stats(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "<b>⚠️ للمطورين فقط!</b>", parse_mode="HTML")
        return
    
    stats_text = (
        f"<b>إحصائيات البوت:</b>\n\n"
        f"<i>المستخدمين: {len(user_count)}</i>\n"
        f"<i>المحظورين: {len(banned_users)}</i>\n"
        f"<i>المكتومين: {len(muted_users)}</i>\n"
        f"<i>المطورين: {len(ADMIN_IDS)}</i>\n"
        f"<i>حد التكرار: {RATE_LIMIT} ث</i>\n"
        f"<i>الأوامر في الخاص: {'نعم' if enable_all_private else 'لا'}</i>\n\n"
        f"<i>{get_random_footer()}</i>"
    )
    bot.reply_to(message, stats_text, parse_mode="HTML")

@bot.message_handler(commands=['clear'])
def handle_clear(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "<b>⚠️ للمطورين فقط!</b>", parse_mode="HTML")
        return
    
    waiting_message = bot.reply_to(message, "<b>🧹 جاري المسح...</b>", parse_mode="HTML")
    user_last_request.clear()
    user_request_times.clear()
    inline_cache.clear()
    omdb_cache.clear()
    suggested_movies.clear()
    suggested_series.clear()
    bot.delete_message(message.chat.id, waiting_message.message_id)
    bot.reply_to(message, "<b>✅ تم المسح!</b>", parse_mode="HTML")

@bot.message_handler(commands=['ban_user'])
def handle_ban_user(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "<b>⚠️ للمطورين فقط!</b>", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ أدخل معرف</b>\n<i>مثال: /ban_user 123456789</i>", parse_mode="HTML")
        return
    
    try:
        target_id = int(text[1])
        banned_users.add(target_id)
        bot.reply_to(message, f"<b>✅ تم حظر {target_id}!</b>", parse_mode="HTML")
    except ValueError:
        bot.reply_to(message, "<b>⚠️ معرف غير صالح!</b>", parse_mode="HTML")

@bot.message_handler(commands=['unban_user'])
def handle_unban_user(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "<b>⚠️ للمطورين فقط!</b>", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ أدخل معرف</b>\n<i>مثال: /unban_user 123456789</i>", parse_mode="HTML")
        return
    
    try:
        target_id = int(text[1])
        banned_users.discard(target_id)
        bot.reply_to(message, f"<b>✅ تم رفع حظر {target_id}!</b>", parse_mode="HTML")
    except ValueError:
        bot.reply_to(message, "<b>⚠️ معرف غير صالح!</b>", parse_mode="HTML")

@bot.message_handler(commands=['mute'])
def handle_mute(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "<b>⚠️ للمطورين فقط!</b>", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ أدخل معرف</b>\n<i>مثال: /mute 123456789</i>", parse_mode="HTML")
        return
    
    try:
        target_id = int(text[1])
        muted_users.add(target_id)
        bot.reply_to(message, f"<b>✅ تم كتم {target_id}!</b>", parse_mode="HTML")
    except ValueError:
        bot.reply_to(message, "<b>⚠️ معرف غير صالح!</b>", parse_mode="HTML")

@bot.message_handler(commands=['unmute'])
def handle_unmute(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "<b>⚠️ للمطورين فقط!</b>", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ أدخل معرف</b>\n<i>مثال: /unmute 123456789</i>", parse_mode="HTML")
        return
    
    try:
        target_id = int(text[1])
        muted_users.discard(target_id)
        bot.reply_to(message, f"<b>✅ تم رفع كتم {target_id}!</b>", parse_mode="HTML")
    except ValueError:
        bot.reply_to(message, "<b>⚠️ معرف غير صالح!</b>", parse_mode="HTML")

@bot.message_handler(commands=['check_user'])
def handle_check_user(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "<b>⚠️ للمطورين فقط!</b>", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ أدخل معرف</b>\n<i>مثال: /check_user 123456789</i>", parse_mode="HTML")
        return
    
    try:
        target_id = int(text[1])
        status = "نشط"
        if target_id in banned_users:
            status = "محظور"
        elif target_id in muted_users:
            status = "مكتوم"
        elif target_id in ADMIN_IDS:
            status = "مطور"
        bot.reply_to(message, f"<b>ℹ️ حالة {target_id}:</b>\n<i>{status}</i>", parse_mode="HTML")
    except ValueError:
        bot.reply_to(message, "<b>⚠️ معرف غير صالح!</b>", parse_mode="HTML")

@bot.message_handler(commands=['enable_all'])
def handle_enable_all(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "<b>⚠️ للمطورين فقط!</b>", parse_mode="HTML")
        return
    
    waiting_message = bot.reply_to(message, "<b>🔓 جاري التفعيل...</b>", parse_mode="HTML")
    global enable_all_private
    enable_all_private = True
    bot.delete_message(message.chat.id, waiting_message.message_id)
    bot.reply_to(message, "<b>✅ الأوامر مفعلة في الخاص لساعة!</b>", parse_mode="HTML")
    threading.Timer(3600, disable_all_private).start()

def disable_all_private():
    global enable_all_private
    enable_all_private = False
    for admin in ADMIN_IDS:
        try:
            bot.send_message(admin, "<b>⚠️ انتهى تفعيل الأوامر في الخاص!</b>", parse_mode="HTML")
        except:
            pass

@bot.message_handler(commands=['restart'])
def handle_restart(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "<b>⚠️ للمطورين فقط!</b>", parse_mode="HTML")
        return
    
    waiting_message = bot.reply_to(message, "<b>🔄 جاري إعادة التشغيل...</b>", parse_mode="HTML")
    bot.delete_message(message.chat.id, waiting_message.message_id)
    bot.reply_to(message, "<b>🔄 البوت يعيد التشغيل...</b>", parse_mode="HTML")
    os._exit(0)

@bot.message_handler(commands=['log'])
def handle_log(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "<b>⚠️ للمطورين فقط!</b>", parse_mode="HTML")
        return
    
    waiting_message = bot.reply_to(message, "<b>📜 جاري جلب السجل...</b>", parse_mode="HTML")
    try:
        with open('bot_errors.log', 'r') as log_file:
            lines = log_file.readlines()[-10:]
            log_text = "\n".join(lines)
        bot.delete_message(message.chat.id, waiting_message.message_id)
        bot.reply_to(message, f"<b>📜 آخر 10 أخطاء:</b>\n\n<i>{log_text}</i>", parse_mode="HTML")
    except Exception as e:
        bot.delete_message(message.chat.id, waiting_message.message_id)
        bot.reply_to(message, "<b>⚠️ خطأ في جلب السجل!</b>", parse_mode="HTML")

@bot.message_handler(commands=['toggle_command'])
def handle_toggle_command(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "<b>⚠️ للمطورين فقط!</b>", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=2)
    if len(text) < 2:
        bot.reply_to(message, "<b>⚠️ حدد الأمر</b>\n<i>مثال: /toggle_command /random enable</i>", parse_mode="HTML")
        return
    
    command = text[1].strip()
    action = text[2].strip().lower() if len(text) > 2 else None
    valid_commands = ["/random", "/suggest", "/imdb", "/actor", "/mindreader", "/detective", 
                      "/plotwist", "/aiwriter", "/realityshift", "/spoilermaster"]
    
    if command not in valid_commands:
        bot.reply_to(message, "<b>⚠️ الأمر غير موجود!</b>", parse_mode="HTML")
        return
    
    if action not in ["enable", "disable"]:
        bot.reply_to(message, "<b>⚠️ استخدم 'enable' أو 'disable'</b>", parse_mode="HTML")
        return
    
    if action == "enable":
        enabled_commands.add(command)
        bot.reply_to(message, f"<b>✅ تم تفعيل {command} في الخاص!</b>", parse_mode="HTML")
    else:
        enabled_commands.discard(command)
        bot.reply_to(message, f"<b>✅ تم إلغاء تفعيل {command} في الخاص!</b>", parse_mode="HTML")

@bot.message_handler(commands=['add_admin'])
def handle_add_admin(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "<b>⚠️ للمطورين فقط!</b>", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ أدخل معرف المطور</b>\n<i>مثال: /add_admin 123456789</i>", parse_mode="HTML")
        return
    
    try:
        new_admin_id = int(text[1])
        waiting_message = bot.reply_to(message, "<b>👨‍💻 جاري إضافة المطور...</b>", parse_mode="HTML")
        ADMIN_IDS.add(new_admin_id)
        bot.delete_message(message.chat.id, waiting_message.message_id)
        bot.reply_to(message, f"<b>✅ تم إضافة المطور {new_admin_id}!</b>", parse_mode="HTML")
    except ValueError:
        bot.reply_to(message, "<b>⚠️ معرف غير صالح!</b>", parse_mode="HTML")

# 🟢 /help
@bot.message_handler(commands=['help'])
def handle_help(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if user_id in banned_users or user_id in muted_users:
        bot.reply_to(message, "<b>⚠️ تم حظرك أو كتمك!</b>", parse_mode="HTML")
        return
    
    user_count.add(user_id)
    markup = InlineKeyboardMarkup()
    
    if chat_id == ALLOWED_GROUP_ID:
        markup.add(InlineKeyboardButton("المطور", url=f"https://t.me/{DEV_USERNAME[1:]}"))
        markup.add(InlineKeyboardButton("قناة البوت", url=f"https://t.me/{CHANNEL_USERNAME[1:]}"))
        markup.add(InlineKeyboardButton("كروب التقنية", url=f"https://t.me/{TECH_GROUP[1:]}"))
    else:
        markup.add(InlineKeyboardButton("🌟 جربني في المجموعة", url="https://t.me/wk_paid"))
        markup.add(InlineKeyboardButton("المطور", url=f"https://t.me/{DEV_USERNAME[1:]}"))
        markup.add(InlineKeyboardButton("قناة البوت", url=f"https://t.me/{CHANNEL_USERNAME[1:]}"))
    
    help_text = (
        "<b>🎬 الأوامر:</b>\n\n"
        "<i>/suggest [نوع]</i> - توصية حسب النوع.\n"
        "<i>/random</i> - فيلم ومسلسل عشوائي.\n"
        "<i>/actor [اسم]</i> - أعمال ممثل.\n"
        "<i>/mindreader</i> - توقع فيلم.\n"
        "<i>/detective [فيلم]</i> - تحليل النهاية (خاص).\n"
        "<i>/plotwist [فيلم]</i> - نهاية جديدة.\n"
        "<i>/aiwriter [تفاصيل]</i> - حبكة فيلم.\n"
        "<i>/realityshift [حدث]</i> - حياتك فيلم.\n"
        "<i>/spoilermaster [فيلم]</i> - حرق بأساليب (خاص).\n"
        "<i>/imdb [فيلم]</i> - تفاصيل IMDb."
    )
    bot.reply_to(message, help_text, parse_mode="HTML", reply_markup=markup)

# 🟢 معالجة الرسائل في الخاص
@bot.message_handler(func=lambda message: not is_allowed(message.chat.id))
def handle_private(message):
    user_id = message.from_user.id
    if user_id in banned_users or user_id in muted_users:
        bot.reply_to(message, "<b>⚠️ تم حظرك أو كتمك!</b>", parse_mode="HTML")
        return
    
    user_count.add(user_id)
    command = message.text.strip().split()[0] if message.text else ""
    if command not in enabled_commands and not (is_admin(user_id) or enable_all_private):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🌟 جربني في المجموعة", url="https://t.me/wk_paid"))
        markup.add(InlineKeyboardButton("المطور", url=f"https://t.me/{DEV_USERNAME[1:]}"))
        markup.add(InlineKeyboardButton("قناة البوت", url=f"https://t.me/{CHANNEL_USERNAME[1:]}"))
        bot.reply_to(message, PRIVATE_RESPONSE, parse_mode="HTML", reply_markup=markup)

# 🟢 إعداد الأوامر في القائمة
def set_bot_commands():
    commands = [
        BotCommand("suggest", "توصية حسب النوع"),
        BotCommand("random", "فيلم ومسلسل عشوائي"),
        BotCommand("actor", "أعمال ممثل"),
        BotCommand("mindreader", "توقع فيلم"),
        BotCommand("detective", "تحليل النهاية (خاص)"),
        BotCommand("plotwist", "نهاية جديدة"),
        BotCommand("aiwriter", "حبكة فيلم"),
        BotCommand("realityshift", "حياتك فيلم"),
        BotCommand("spoilermaster", "حرق بأساليب (خاص)"),
        BotCommand("imdb", "تفاصيل IMDb")
    ]
    bot.set_my_commands(commands)

# 🟢 تشغيل البوت
if __name__ == "__main__":
    print("🚀 TechnoSyria Strat!")
    set_bot_commands()
    while True:
        try:
            bot.polling(none_stop=True, skip_pending=True)
        except Exception as e:
            logging.error(f"⚠️ Polling Error: {e}")
            time.sleep(5)
