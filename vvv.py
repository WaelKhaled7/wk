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
import asyncio
import aiohttp

# 🟢 إعدادات البوت
API_KEY = "1624636642:AAG6xhQ3fno7_N6JID_6B_qlKGXddA4IuTQ"
bot = telebot.TeleBot(API_KEY)
DEV_ID = "1622270145"
ALLOWED_GROUP_ID = -1002488472845
DEV_USERNAME = "@WaelKhaled3"
CHANNEL_USERNAME = "@techno_syria"
TECH_GROUP = "@techno_syria1"
MOVIES_CHANNEL = "@movies_techno"
ADMIN_IDS = {int(DEV_ID)}
ALLOWED_GROUPS = {ALLOWED_GROUP_ID}
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
GEMINI_API_KEY = "AIzaSyBg0JhMDyD1oXCQ23kGwy0XPxhr6btZqwg"
OMDB_API_KEY = "5dcfe76e"
OMDB_BASE_URL = "http://www.omdbapi.com/"

# 🟢 تفعيل السجل
logging.basicConfig(filename='bot_errors.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 🟢 قوائم الانتظار والردود العشوائية
WAITING_EMOJIS = ["🎬", "🍿", "🔍", "📝", "🔎", "📺", "💡"]
WAITING_SYRIAN_RESPONSES = ["طووول بالك، رح رشحلك طول بالك 😂❤️", "عد للخمسة وبكون خلصت 🥲!", "خليك هون، جايبلك شي بجنن!"]
IMDB_WAITING = "🎥 لحظة وبجبلك التفاصيل"
SYRIAN_RESPONSES = ["هاد اللي لقيتو ياغالي !", "شوف هاد، بضمنلك يعجبك !", "هلق جبتلك شي بياخد العقل!"]
RANDOM_RESPONSES = ["شوف هاد، بيستاهل وقتك!", "شوف هاد اذا ماعجبك رجعلي ياه 😂", "لعبتي العشوائية خود هاد 😂👇"]
PRIVATE_RESPONSE = "اهلييين، أنا هون للمجموعة بس، تعا جربني !"
INVALID_INPUT_RESPONSE = "ياعيني، هاد مو اسم فيلم، جرب شي منطقي!"
SMART_INVALID_RESPONSE = "ياعيني، هاد شي غريب! جرب شي عن الأفلام أو المسلسلات 😂"
INLINE_MIN_CHARS_RESPONSE = "اكتب ٣ أحرف على الأقل !"
ONLY_PRIVATE_RESPONSE = "<b>هذا الأمر متاح فقط في الخاص</b>\n<i>بسبب الحرق والمصايب، تعا خاص لحالنا 😂! 🥲</i>"

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
    "game of thrones", "stranger things", "dangerous dynasty house of assad", "see"
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
    return chat_id == int(DEV_ID) or chat_id in ALLOWED_GROUPS

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
    if re.search(r"فيلم|مسلسل|وثائقي|actor|movie|series", input_text.lower()):
        return True
    response = get_gemini_response(f"هل '{input_text}' مرتبط بأفلام أو مسلسلات أو وثائقيات؟ أجب بـ 'نعم' أو 'لا' فقط.", retries=1)
    return response and response.strip().lower() == "نعم"

# 🟢 تنسيق الردود مع ترتيب ودمج <b> و<i> (محسن لإزالة الفراغ)
def format_response(response, keep_english_titles=False):
    if not response:
        return "<b>⚡ السيرفر مشغول حالياً</b>"
    
    robotic_phrases = ["بالطبع!", "إليك", "أتمنى", "Here is", "Sure", "Of course", "Behold", "أوصي", "توصية", "استمتع بالمشاهدة", "لماذا", "أقترح", "ها هي"]
    for phrase in robotic_phrases:
        response = re.sub(rf"^{phrase}\s*|\s*{phrase}$", "", response, flags=re.IGNORECASE).strip()
    
    response = re.sub(r"[\*_\`\[\]#]", "", response).strip()
    lines = [line.strip() for line in response.split("\n") if line.strip()]
    formatted = []
    
    for line in lines:
        line = escape(line)
        if re.match(r"^(فيلم|مسلسل|وثائقي|\".*\")", line) or (keep_english_titles and re.match(r"^\w.*$", line)):
            title = re.search(r"\"(.*?)\"", line)
            title = title.group(1) if title else line
            translated_title = title if keep_english_titles else GoogleTranslator(source='auto', target='ar').translate(title)
            formatted.append(f"<b><i>{translated_title}</i></b>")
        else:
            translated = GoogleTranslator(source='auto', target='ar').translate(line) if line else line
            formatted.append(f"<b><i>{translated}</i></b>")
    
    output = []
    for i, line in enumerate(formatted):
        if i > 0 and line.startswith("<b><i>"):
            output.append("")
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
async def get_gemini_response_async(user_input, retries=3, delay=2):
    if not check_internet_connection():
        logging.error("⚠️ لا يوجد اتصال بالإنترنت.")
        return None
    
    headers = {"Content-Type": "application/json"}
    params = {"key": GEMINI_API_KEY}
    data = {"contents": [{"parts": [{"text": user_input}]}], "generationConfig": {"temperature": 1, "topP": 0.95, "topK": 40, "maxOutputTokens": 8192}}
    
    async with aiohttp.ClientSession() as session:
        for attempt in range(retries):
            try:
                async with session.post(GEMINI_API_URL, headers=headers, params=params, json=data, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result["candidates"][0]["content"]["parts"][0]["text"].strip()
                    elif response.status == 429:
                        logging.error("⚠️ Gemini: الكثير من الطلبات.")
                        await asyncio.sleep(delay * (attempt + 1))
                    else:
                        logging.error(f"⚠️ Gemini Error: {response.status} - {await response.text()}")
                        await asyncio.sleep(delay)
            except Exception as e:
                logging.error(f"⚠️ Gemini Exception (Attempt {attempt + 1}): {e}")
                await asyncio.sleep(delay)
    return None

def get_gemini_response(user_input, retries=3, delay=2):
    return asyncio.run(get_gemini_response_async(user_input, retries, delay))

# 🟢 تذييل عشوائي
def get_random_footer():
    return random.choice([f"📢 {CHANNEL_USERNAME}", f"👨‍💻 {DEV_USERNAME}", f"💡 {TECH_GROUP}", f"🎬 {MOVIES_CHANNEL}"])

# 🟢 التحقق من صحة الطلب
def is_valid_request(text):
    keywords = ["فيلم", "مسلسل", "أفلام", "مسلسلات", "دراما", "أكشن", "كوميدي", "رعب", "خيال علمي", "وثائقي", "فلم", "اكشن", "جريمة", "غموض"]
    return any(keyword in text.lower() for keyword in keywords)

# 🟢 نظام منع التحايل
def is_rate_limited(user_id):
    current_time = time.time()
    if user_id in user_request_times and current_time - user_request_times[user_id] < RATE_LIMIT:
        return True
    user_request_times[user_id] = current_time
    return False

# 🟢 البحث في OMDb
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
    movie_titles = ["The Godfather", "Inception", "The Matrix", "Vikings", "Breaking Bad", "Hannibal", 
                    "The Walking Dead", "Interstellar", "Fight Club", "Pulp Fiction", "Fast X", 
                    "The Dark Knight", "Game of Thrones", "Stranger Things", "Dangerous Dynasty House of Assad", "See"]
    query_lower = query.lower().replace(" ", "")
    for title in movie_titles:
        title_lower = title.lower().replace(" ", "")
        if query_lower in title_lower or sum(c1 == c2 for c1, c2 in zip(query_lower, title_lower)) > len(query_lower) * 0.7:
            return title
    return query

# 🟢 Inline Query محسّنة (3 نتائج مشابهة نفس رد /imdb)
@bot.inline_handler(func=lambda query: True)
def handle_inline_query(query):
    query_text = query.query.strip()
    
    if len(query_text) < 2:
        result = InlineQueryResultPhoto(
            id=str(random.randint(1, 1000000)),
            photo_url="https://via.placeholder.com/150",
            thumbnail_url="https://via.placeholder.com/150",
            caption="<b>اكتب اسم فيلم أو مسلسل (حرفين على الأقل)!</b>",
            parse_mode="HTML"
        )
        bot.answer_inline_query(query.id, [result], cache_time=1)
        return
    
    if len(query_text) < 3:
        result = InlineQueryResultPhoto(
            id=str(random.randint(1, 1000000)),
            photo_url="https://via.placeholder.com/150",
            thumbnail_url="https://via.placeholder.com/150",
            caption="<b>شوي كمان، اكتب 3 أحرف على الأقل لنتيجة أفضل!</b>",
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
            f"<i>🌟 البطولة: {actors}</i>"
        )
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("📄 صفحة IMDb", url=imdb_url))
        markup.add(InlineKeyboardButton("🎬 فيلم مشابه", callback_data=f"similar:{title}"))
        
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
    
    # إضافة نتائج مشابهة (حتى 3)
    movie_titles = ["The Godfather", "Inception", "The Matrix", "Vikings", "Breaking Bad", "Hannibal", 
                    "The Walking Dead", "Interstellar", "Fight Club", "Pulp Fiction", "Fast X", 
                    "The Dark Knight", "Game of Thrones", "Stranger Things", "Dangerous Dynasty House of Assad", "See"]
    query_lower = query_text.lower().replace(" ", "")
    for title in movie_titles:
        if len(results) >= 3:
            break
        title_lower = title.lower().replace(" ", "")
        if query_lower in title_lower and title not in [r.caption.split("\n")[0].replace("<b>", "").replace("</b>", "") for r in results]:
            response = search_omdb(title)
            if response and response.get("Response") == "True":
                imdb_id = response.get("imdbID")
                if imdb_id not in seen_ids:
                    plot = GoogleTranslator(source='auto', target='ar').translate(response.get("Plot", "غير متوفر"))
                    year = response.get("Year", "غير معروف")
                    rating = response.get("imdbRating", "غير معروف")
                    genre = GoogleTranslator(source='auto', target='ar').translate(response.get("Genre", "غير معروف"))
                    runtime = response.get("Runtime", "غير معروف")
                    director = GoogleTranslator(source='auto', target='ar').translate(response.get("Director", "غير معروف"))
                    actors = response.get("Actors", "غير معروف")
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
                        f"<i>🌟 البطولة: {actors}</i>"
                    )
                    markup = InlineKeyboardMarkup()
                    markup.add(InlineKeyboardButton("📄 صفحة IMDb", url=imdb_url))
                    markup.add(InlineKeyboardButton("🎬 فيلم مشابه", callback_data=f"similar:{title}"))
                    
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
        bot.answer_inline_query(query.id, results[:3], cache_time=1, is_personal=False)
    except Exception as e:
        logging.error(f"⚠️ Inline Query Error: {e}")

# 🟢 /random
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
        bot.reply_to(message, "<b>طول بالك شوي، إنت تُكسر مِن الطلبات 😂</b>", parse_mode="HTML")
        return
    
    waiting_message = bot.reply_to(message, random.choice(WAITING_EMOJIS))
    movie_response = get_gemini_response(f"فيلم عشوائي مع قصة مختصرة (غير {list(suggested_movies)[-1] if suggested_movies else ''})")
    series_response = get_gemini_response(f"مسلسل عشوائي مع قصة مختصرة (غير {list(suggested_series)[-1] if suggested_series else ''})")
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

# 🟢 /suggest
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
        bot.reply_to(message, "<b>طول بالك شوي، إنت تُكسر مِن الطلبات 😂</b>", parse_mode="HTML")
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
    response = get_gemini_response(f"فيلم ومسلسل من نوع {genre} مع قصة مختصرة")
    bot.delete_message(chat_id, waiting_message.message_id)
    
    if not response:
        bot.reply_to(message, "<b>⚡ السيرفر مشغول حالياً</b>", parse_mode="HTML")
        return
    
    formatted_response = format_response(response, keep_english_titles=True)
    reply_text = f"<b>{random.choice(SYRIAN_RESPONSES)}</b>\n\n{formatted_response}\n\n<i>{get_random_footer()}</i>"
    bot.reply_to(message, reply_text, parse_mode="HTML")

# 🟢 /imdb (عنوان بالإنجليزي)
@bot.message_handler(commands=['imdb'])
def handle_imdb(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if user_id in banned_users or user_id in muted_users:
        bot.reply_to(message, "<b>⚠️ تم حظرك أو كتمك!</b>", parse_mode="HTML")
        return
    
    user_count.add(user_id)
    if is_rate_limited(user_id):
        bot.reply_to(message, "<b>طول بالك شوي، إنت تُكسر مِن الطلبات 😂</b>", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ حدد اسم الفيلم</b>\n<code>مثال: /imdb Fast X</code>", parse_mode="HTML")
        return
    
    query = text[1].strip()
    waiting_message = bot.reply_to(message, IMDB_WAITING)
    
    try:
        response = search_omdb(query)
        if not response or response.get("Response") != "True":
            movie_titles = ["The Godfather", "Inception", "The Matrix", "Vikings", "Breaking Bad", 
                            "Hannibal", "The Walking Dead", "Interstellar", "Fight Club", "Pulp Fiction",
                            "Fast X", "The Dark Knight", "Game of Thrones", "Stranger Things",
                            "Dangerous Dynasty House of Assad", "See"]
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
        
        title = response.get("Title")  # العنوان بالإنجليزي
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
            f"<b>{title}</b>\n"  # العنوان بالإنجليزي
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
        markup.add(InlineKeyboardButton("🎬 فيلم مشابه", callback_data=f"similar:{title}"))
        
        bot.delete_message(chat_id, waiting_message.message_id)
        bot.send_photo(chat_id, poster_url, caption=reply_text[:1024], parse_mode="HTML", reply_markup=markup)
    except Exception as e:
        logging.error(f"⚠️ IMDb Error: {e}")
        bot.delete_message(chat_id, waiting_message.message_id)
        bot.reply_to(message, "<b>⚠️ خطأ، جرب لاحقاً!</b>", parse_mode="HTML")

# 🟢 معالجة زر "فيلم مشابه"
@bot.callback_query_handler(func=lambda call: call.data.startswith("similar:"))
def handle_similar_movie(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    if user_id in banned_users or user_id in muted_users:
        bot.answer_callback_query(call.id, "تم حظرك أو كتمك!")
        return
    
    if is_rate_limited(user_id):
        bot.answer_callback_query(call.id, "طول بالك شوي، إنت تُكسر مِن الطلبات 😂")
        return
    
    movie = call.data.split(":", 1)[1]
    response = get_gemini_response(f"اقترح فيلم مشابه لـ {movie} مع قصة مختصرة")
    
    if not response:
        bot.edit_message_caption("<b>⚡ السيرفر مشغول حالياً</b>", chat_id, call.message.message_id, parse_mode="HTML")
        bot.answer_callback_query(call.id, "السيرفر مشغول!")
        return
    
    formatted_response = format_response(response, keep_english_titles=True)
    reply_text = f"<b>🎬 فيلم مشابه لـ {movie}:</b>\n\n{formatted_response}\n\n<i>{get_random_footer()}</i>"
    bot.edit_message_caption(reply_text, chat_id, call.message.message_id, parse_mode="HTML")
    bot.answer_callback_query(call.id, "تم اقتراح فيلم مشابه!")

# 🟢 /actor
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
        bot.reply_to(message, "<b>طول بالك شوي، إنت تُكسر مِن الطلبات 😂</b>", parse_mode="HTML")
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
    response = get_gemini_response(f"قائمة بأفضل أفلام أو مسلسلات الممثل {actor} مع قصة مختصرة")
    bot.delete_message(chat_id, waiting_message.message_id)
    
    if not response:
        bot.reply_to(message, "<b>⚡ السيرفر مشغول أو الممثل غير موجود!</b>", parse_mode="HTML")
        return
    
    formatted_response = format_response(response, keep_english_titles=True)
    reply_text = f"<b>📌 أعمال {actor}:</b>\n\n{formatted_response}\n\n<i>{get_random_footer()}</i>"
    bot.reply_to(message, reply_text, parse_mode="HTML")

# 🟢 /mindreader
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
        bot.reply_to(message, "<b>طول بالك شوي، إنت تُكسر مِن الطلبات 😂</b>", parse_mode="HTML")
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
    
    prompt = f"فيلم بناءً على:\n1. نوع الفيلم: {answers[0]}\n2. قصير/طويل: {answers[1]}\n3. المزاج: {answers[2]}\nمع قصة مختصرة بالعربي."
    response = get_gemini_response(prompt)
    if not response:
        bot.reply_to(message, "<b>⚡ السيرفر مشغول حالياً</b>", parse_mode="HTML")
        return
    
    formatted_response = format_response(response, keep_english_titles=True)
    reply_text = f"<b>🧠 توقعتلك:</b>\n\n{formatted_response}\n\n<i>{get_random_footer()}</i>"
    bot.reply_to(message, reply_text, parse_mode="HTML")

# 🟢 /detective
@bot.message_handler(commands=['detective'])
def handle_detective(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if user_id in banned_users or user_id in muted_users:
        bot.reply_to(message, "<b>⚠️ تم حظرك أو كتمك!</b>", parse_mode="HTML")
        return
    
    user_count.add(user_id)
    
    if is_allowed(chat_id) and not is_admin(user_id):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🌟 جربني في الخاص", url=f"https://t.me/{bot.get_me().username}"))
        bot.reply_to(message, ONLY_PRIVATE_RESPONSE, parse_mode="HTML", reply_markup=markup)
        return
    
    if is_rate_limited(user_id):
        bot.reply_to(message, "<b>طول بالك شوي، إنت تُكسر مِن الطلبات 😂</b>", parse_mode="HTML")
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
    response = get_gemini_response(f"نهاية الفيلم أو المسلسل أو الوثائقي {movie} بطريقة عبقرية وساخرة")
    bot.delete_message(chat_id, waiting_message.message_id)
    
    if not response:
        bot.reply_to(message, "<b>⚡ السيرفر مشغول أو العنوان غير موجود!</b>", parse_mode="HTML")
        return
    
    formatted_response = format_response(response, keep_english_titles=True)
    reply_text = f"<b>🔍 تحليل نهاية {movie}:</b>\n\n{formatted_response}\n\n<i>{get_random_footer()}</i>"
    bot.reply_to(message, reply_text, parse_mode="HTML")

# 🟢 /plotwist
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
        bot.reply_to(message, "<b>طول بالك شوي، إنت تُكسر مِن الطلبات 😂</b>", parse_mode="HTML")
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
    response = get_gemini_response(f"نهاية جديدة ومجنونة للفيلم أو المسلسل أو الوثائقي {movie}")
    bot.delete_message(chat_id, waiting_message.message_id)
    
    if not response:
        bot.reply_to(message, "<b>⚡ السيرفر مشغول أو العنوان غير موجود!</b>", parse_mode="HTML")
        return
    
    formatted_response = format_response(response, keep_english_titles=True)
    reply_text = f"<b>🌀 نهاية جديدة لـ {movie}:</b>\n\n{formatted_response}\n\n<i>{get_random_footer()}</i>"
    bot.reply_to(message, reply_text, parse_mode="HTML")

# 🟢 /aiwriter
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
        bot.reply_to(message, "<b>طول بالك شوي، إنت تُكسر مِن الطلبات 😂</b>", parse_mode="HTML")
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
    response = get_gemini_response(f"حبكة فيلم بناءً على: {details}")
    bot.delete_message(chat_id, waiting_message.message_id)
    
    if not response:
        bot.reply_to(message, "<b>⚡ السيرفر مشغول حالياً</b>", parse_mode="HTML")
        return
    
    formatted_response = format_response(response, keep_english_titles=True)
    reply_text = f"<b>🎬 حبكة الفيلم:</b>\n\n{formatted_response}\n\n<i>{get_random_footer()}</i>"
    bot.reply_to(message, reply_text, parse_mode="HTML")

# 🟢 /realityshift
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
        bot.reply_to(message, "<b>طول بالك شوي، إنت تُكسر مِن الطلبات 😂</b>", parse_mode="HTML")
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
    response = get_gemini_response(f"فيلم هوليوودي بناءً على هذا الحدث: {event}")
    bot.delete_message(chat_id, waiting_message.message_id)
    
    if not response:
        bot.reply_to(message, "<b>⚡ السيرفر مشغول حالياً</b>", parse_mode="HTML")
        return
    
    formatted_response = format_response(response, keep_english_titles=True)
    reply_text = f"<b>🎭 فيلمك الهوليوودي:</b>\n\n{formatted_response}\n\n<i>{get_random_footer()}</i>"
    bot.reply_to(message, reply_text, parse_mode="HTML")

# 🟢 /spoilermaster
@bot.message_handler(commands=['spoilermaster'])
def handle_spoilermaster(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if user_id in banned_users or user_id in muted_users:
        bot.reply_to(message, "<b>⚠️ تم حظرك أو كتمك!</b>", parse_mode="HTML")
        return
    
    user_count.add(user_id)
    
    if is_allowed(chat_id) and not is_admin(user_id):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🌟 جربني في الخاص", url=f"https://t.me/{bot.get_me().username}"))
        bot.reply_to(message, ONLY_PRIVATE_RESPONSE, parse_mode="HTML", reply_markup=markup)
        return
    
    if is_rate_limited(user_id):
        bot.reply_to(message, "<b>طول بالك شوي، إنت تُكسر مِن الطلبات 😂</b>", parse_mode="HTML")
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
    response = get_gemini_response(f"حرق للفيلم أو المسلسل أو الوثائقي {movie} بأسلوب عامي سوري")
    bot.delete_message(chat_id, waiting_message.message_id)
    
    if not response:
        bot.reply_to(message, "<b>⚡ السيرفر مشغول أو العنوان غير موجود!</b>", parse_mode="HTML")
        return
    
    formatted_response = format_response(response, keep_english_titles=True)
    initial_response = f"<b>تم حرق {movie}:</b>\n\n<i>إليك وصفاً موجزاً لما حدث في النهاية بأسلوب عامي سوري:</i>\n\n{formatted_response}"
    
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
        bot.answer_callback_query(call.id, "طول بالك شوي، إنت تُكسر مِن الطلبات 😂")
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

# 🟢 أوامر خارقة للمطور
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
            response = get_gemini_response(f"تحليل النص التالي واستخراج المعلومات المهمة: {input_data}")
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

@bot.message_handler(commands=['server_status'])
def handle_server_status(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "<b>⚠️ للمطورين فقط!</b>", parse_mode="HTML")
        return
    
    try:
        cpu_usage = os.popen("top -bn1 | grep 'Cpu(s)' | awk '{print $2}'").read().strip()
        memory_usage = os.popen("free -m | grep 'Mem:' | awk '{print $3/$2 * 100.0}'").read().strip()
        uptime = os.popen("uptime -p").read().strip()
        
        reply_text = (
            f"<b>🖥️ حالة السيرفر:</b>\n\n"
            f"<i>استخدام المعالج: {cpu_usage}%</i>\n"
            f"<i>استخدام الذاكرة: {memory_usage}%</i>\n"
            f"<i>مدة التشغيل: {uptime}</i>\n\n"
            f"<i>{get_random_footer()}</i>"
        )
        bot.reply_to(message, reply_text, parse_mode="HTML")
    except Exception as e:
        logging.error(f"⚠️ Server Status Error: {e}")
        bot.reply_to(message, "<b>⚠️ خطأ في جلب الحالة!</b>", parse_mode="HTML")

@bot.message_handler(commands=['backup'])
def handle_backup(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "<b>⚠️ للمطورين فقط!</b>", parse_mode="HTML")
        return
    
    waiting_message = bot.reply_to(message, "<b>💾 جاري عمل نسخة احتياطية...</b>", parse_mode="HTML")
    try:
        backup_data = {
            "user_count": list(user_count),
            "banned_users": list(banned_users),
            "muted_users": list(muted_users),
            "suggested_movies": list(suggested_movies),
            "suggested_series": list(suggested_series),
            "inline_cache": {k: [r.to_json() for r in v] for k, v in inline_cache.items()},
            "omdb_cache": omdb_cache
        }
        with open("bot_backup.json", "w") as f:
            json.dump(backup_data, f)
        bot.delete_message(message.chat.id, waiting_message.message_id)
        bot.reply_to(message, "<b>✅ تم عمل النسخة الاحتياطية!</b>", parse_mode="HTML")
    except Exception as e:
        logging.error(f"⚠️ Backup Error: {e}")
        bot.delete_message(message.chat.id, waiting_message.message_id)
        bot.reply_to(message, "<b>⚠️ خطأ في النسخ!</b>", parse_mode="HTML")

@bot.message_handler(commands=['restore'])
def handle_restore(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "<b>⚠️ للمطورين فقط!</b>", parse_mode="HTML")
        return
    
    waiting_message = bot.reply_to(message, "<b>🔄 جاري استعادة النسخة...</b>", parse_mode="HTML")
    try:
        with open("bot_backup.json", "r") as f:
            backup_data = json.load(f)
        
        global user_count, banned_users, muted_users, suggested_movies, suggested_series, inline_cache, omdb_cache
        user_count = set(backup_data["user_count"])
        banned_users = set(backup_data["banned_users"])
        muted_users = set(backup_data["muted_users"])
        suggested_movies = set(backup_data["suggested_movies"])
        suggested_series = set(backup_data["suggested_series"])
        inline_cache = {k: [InlineQueryResultPhoto.parse_json(r) for r in v] for k, v in backup_data["inline_cache"].items()}
        omdb_cache = backup_data["omdb_cache"]
        
        bot.delete_message(message.chat.id, waiting_message.message_id)
        bot.reply_to(message, "<b>✅ تم استعادة النسخة!</b>", parse_mode="HTML")
    except Exception as e:
        logging.error(f"⚠️ Restore Error: {e}")
        bot.delete_message(message.chat.id, waiting_message.message_id)
        bot.reply_to(message, "<b>⚠️ خطأ في الاستعادة!</b>", parse_mode="HTML")

# 🟢 /broadcast محسن مع معالجة المجموعات المفقودة
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
    successful_users = 0
    
    for user in user_count:
        try:
            bot.send_message(user, broadcast_msg, parse_mode="HTML")
            successful_users += 1
            time.sleep(0.1)
        except Exception as e:
            logging.error(f"⚠️ Broadcast Error for {user}: {e}")
    
    for group_id in ALLOWED_GROUPS.copy():
        try:
            bot.send_message(group_id, broadcast_msg, parse_mode="HTML")
            successful_users += 1
        except telebot.apihelper.ApiTelegramException as e:
            if "chat not found" in str(e):
                logging.warning(f"⚠️ المجموعة {group_id} غير موجودة، تم تجاهلها.")
            else:
                logging.error(f"⚠️ Broadcast Error for group {group_id}: {e}")
    
    bot.delete_message(message.chat.id, waiting_message.message_id)
    bot.reply_to(message, f"<b>✅ تم البث لـ {successful_users} مستخدم ومجموعة!</b>", parse_mode="HTML")

# 🟢 أمر جديد /set_groups للمطور
@bot.message_handler(commands=['set_groups'])
def handle_set_groups(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "<b>⚠️ للمطورين فقط!</b>", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ أدخل الأمر والمجموعة</b>\n<i>مثال: /set_groups add -100123456789 أو /set_groups remove -100123456789</i>", parse_mode="HTML")
        return
    
    args = text[1].split()
    if len(args) < 2 or args[0] not in ["add", "remove"]:
        bot.reply_to(message, "<b>⚠️ استخدم add أو remove ثم رقم المجموعة</b>", parse_mode="HTML")
        return
    
    action, group_id = args[0], args[1]
    try:
        group_id = int(group_id)
        if action == "add":
            ALLOWED_GROUPS.add(group_id)
            bot.reply_to(message, f"<b>✅ تم إضافة المجموعة {group_id} للمسموحة!</b>", parse_mode="HTML")
        elif action == "remove":
            ALLOWED_GROUPS.discard(group_id)
            bot.reply_to(message, f"<b>✅ تم حذف المجموعة {group_id} من المسموحة!</b>", parse_mode="HTML")
    except ValueError:
        bot.reply_to(message, "<b>⚠️ رقم المجموعة غير صالح!</b>", parse_mode="HTML")

# 🟢 /wk (لوحة المطور مع الأوامر الجديدة)
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
        "<i>/super_scan [نص/رابط]</i> - فحص خارق.\n"
        "<i>/server_status</i> - حالة السيرفر.\n"
        "<i>/backup</i> - نسخة احتياطية.\n"
        "<i>/restore</i> - استعادة النسخة.\n"
        "<i>/set_groups [add/remove] [id]</i> - تعيين مجموعات مسموحة.\n"
        f"<i>{get_random_footer()}</i>"
    )
    bot.reply_to(message, help_text, parse_mode="HTML")

# 🟢 أوامر المطور القديمة
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
        f"<i>الأوامر في الخاص: {'نعم' if enable_all_private else 'لا'}</i>\n"
        f"<i>المجموعات المسموحة: {len(ALLOWED_GROUPS)}</i>\n\n"
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
    if not is_admin(userid):
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
    
    if chat_id in ALLOWED_GROUPS:
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
        "<i>/imdb [فيلم]</i> - تفاصيل IMDb مع فيلم مشابه."
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

# 🟢 تشغيل البوت مع تحسين الأداء وحل مشكلات Contabo
if __name__ == "__main__":
    print("🚀هبد")
    set_bot_commands()
    while True:
        try:
            bot.polling(none_stop=True, skip_pending=True, timeout=30, long_polling_timeout=30)
        except requests.exceptions.ReadTimeout:
            logging.error("⚠️ Read Timeout: زاد وقت الاستجابة، جاري إعادة المحاولة...")
            time.sleep(10)
        except requests.exceptions.ConnectionError:
            logging.error("⚠️ Connection Error: مشكلة في الاتصال، جاري إعادة المحاولة...")
            time.sleep(10)
        except Exception as e:
            logging.error(f"⚠️ Polling Error: {e}")
            time.sleep(10)
