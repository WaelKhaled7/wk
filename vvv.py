import telebot
import requests
import random
import re
import time
import logging
import threading
import os
import json
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, InlineQueryResultArticle, InlineQueryResultPhoto, InputTextMessageContent, BotCommand
from html import escape
from deep_translator import GoogleTranslator
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# 🟢 إعدادات البوت
API_KEY = "1624636642:AAG6xhQ3fno7_N6JID_6B_qlKGXddA4IuTQ"
bot = telebot.TeleBot(API_KEY)

# 🟢 المعرفات الثابتة
DEV_ID = "1622270145"
ALLOWED_GROUP_ID = -1002488472845
DEV_USERNAME = "@WaelKhaled3"
CHANNEL_USERNAME = "@techno_syria"
TECH_GROUP = "@techno_syria1"
MOVIES_CHANNEL = "@movies_techno"
ADMIN_IDS = {int(DEV_ID)}

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent"
GEMINI_API_KEY = "AIzaSyBg0JhMDyD1oXCQ23kGwy0XPxhr6btZqwg"
OMDB_API_KEY = "5dcfe76e"
OMDB_BASE_URL = "http://www.omdbapi.com/"

# 🟢 تفعيل السجل
logging.basicConfig(filename='bot_errors.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', encoding='utf-8')

# 🟢 ردود عشوائية
SYRIAN_RESPONSES = [
    "اي خيو، هاد أحلى ترشيح جبتلك ياه! 🎬😂",
    "حبيبيي انت، هاد على زوقك تمامًا! 🎬🔥",
    "حسيتك بتحب هالنوع، جرب هاد وادعيلي 🫡"
]
RANDOM_RESPONSES = [
    "جرب هاد، على مسؤوليتي! 🔥",
    "إذا ما عجبك هاد، رجعلي ياه! 😂",
    "هاد الترشيح نار، جربه ورح تندم إذا ما شفتو! 🤣🚀"
]
PRIVATE_RESPONSE = "اهليييين، أنا بشتغل بس في المجموعة الخاصة فيني 🥲"
INVALID_INPUT_RESPONSE = "🙎 ياحبيبي، هاد مو اسم فيلم أو مسلسل صحيح، جرب شي منطقي!"

# 🟢 ذاكرة مؤقتة
user_last_request = {}
user_request_times = {}
user_count = set()
banned_users = set()
muted_users = set()
enable_all_private = False
inline_cache = {}
omdb_cache = {}
RATE_LIMIT = 5  # افتراضي 5 ثوانٍ

# 🟢 التحقق من السماحية
def is_allowed(chat_id):
    return chat_id == int(DEV_ID) or chat_id == ALLOWED_GROUP_ID

# 🟢 التحقق من الأدمن
def is_admin(user_id):
    return user_id in ADMIN_IDS

# 🟢 فحص إدخال صالح
def is_valid_movie_input(text):
    text = text.strip()
    return len(text) >= 2 and not text.isdigit()

# 🟢 تنسيق الردود
def format_response(response, keep_english_titles=False):
    if not response:
        return "<b>⚡ السيرفر مشغول، جرب تاني!</b>"
    
    response = re.sub(r"[\*_\`\[\]]", "", response)
    lines = response.split("\n")
    formatted = []
    
    for line in lines:
        line = escape(line.strip())
        if re.match(r"^(فيلم|مسلسل|\".*\")", line) or (keep_english_titles and re.match(r"^\w.*$", line.strip())):
            title = re.search(r"\"(.*?)\"", line)
            title = title.group(1) if title else line
            formatted.append(f"<b>{title}</b>")
        elif re.match(r"^القصة:|^الوصف:", line):
            translated = GoogleTranslator(source='auto', target='ar').translate(line.replace("القصة:", "").replace("الوصف:", "").strip())
            formatted.append(f"<i>{translated}</i>")
        elif line.strip():
            formatted.append(line)
    
    return "\n".join(formatted)

# 🟢 الحصول على رد من Gemini (سريع بدون محاولات)
def get_gemini_response(user_input):
    headers = {"Content-Type": "application/json"}
    params = {"key": GEMINI_API_KEY}
    data = {
        "contents": [{"parts": [{"text": user_input}]}],
        "generationConfig": {"temperature": 1, "topP": 0.95, "topK": 40, "maxOutputTokens": 8192}
    }
    try:
        response = requests.post(GEMINI_API_URL, headers=headers, params=params, json=data, timeout=3)
        if response.status_code == 200:
            return response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        else:
            logging.error(f"⚠️ Gemini Error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logging.error(f"⚠️ Gemini Exception: {str(e)}")
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

# 🟢 البحث في OMDb (سريع)
def search_omdb(query):
    if query in omdb_cache:
        return omdb_cache[query]
    
    params = {"apikey": OMDB_API_KEY, "t": query, "plot": "short", "r": "json"}
    try:
        response = requests.get(OMDB_BASE_URL, params=params, timeout=3)
        result = response.json() if response.status_code == 200 else None
        omdb_cache[query] = result
        return result
    except Exception as e:
        logging.error(f"⚠️ OMDb Error: {str(e)}")
        return None

# 🟢 البحث في ElCinema (اختياري ومضمون)
def search_elcinema(query):
    headers = {"User-Agent": "Mozilla/5.0"}
    url = f"https://www.elcinema.com/search/?q={query.replace(' ', '+')}"
    try:
        response = requests.get(url, headers=headers, timeout=3)
        soup = BeautifulSoup(response.text, 'html.parser')
        result = soup.find("div", class_="media-block")
        if not result:
            return None
        
        title = result.find("h3").text.strip() if result.find("h3") else "غير متوفر"
        link = urljoin("https://www.elcinema.com", result.find("a")['href']) if result.find("a") else url
        details = result.find("p").text.strip() if result.find("p") else "غير متوفر"
        return {"title": title, "details": details, "link": link}
    except Exception as e:
        logging.error(f"⚠️ ElCinema Error: {str(e)}")
        return None

# 🟢 Inline Query
@bot.inline_handler(func=lambda query: len(query.query) > 0)
def handle_inline_query(query):
    query_text = query.query.strip()
    if query_text in inline_cache:
        bot.answer_inline_query(query.id, inline_cache[query_text], cache_time=60)
        return
    
    if len(query_text) < 2:
        result = InlineQueryResultArticle(
            id="short",
            title="اكتب المزيد",
            description="اكتب حرفين على الأقل!",
            input_message_content=InputTextMessageContent("<b>⚠️ اكتب اسم أطول!</b>", parse_mode="HTML")
        )
        bot.answer_inline_query(query.id, [result], cache_time=60)
        return
    
    results = []
    seen_ids = set()
    response = search_omdb(query_text)
    if response and response.get("Response") == "True":
        title = response.get("Title")
        plot = GoogleTranslator(source='auto', target='ar').translate(response.get("Plot", "غير متوفر"))
        year = response.get("Year", "غير معروف")
        rating = response.get("imdbRating", "غير معروف")
        genre = GoogleTranslator(source='auto', target='ar').translate(response.get("Genre", "غير معروف"))
        actors = response.get("Actors", "غير معروف")
        imdb_id = response.get("imdbID")
        poster_url = response.get("Poster", "N/A")
        
        if imdb_id not in seen_ids:
            seen_ids.add(imdb_id)
            reply_text = (
                f"<b>{title}</b>\n"
                f"<i>{plot[:150]}</i>\n"
                f"📅 السنة: {year}\n"
                f"⭐ التقييم: {rating}/10\n"
                f"🎭 النوع: {genre}\n"
                f"🌟 البطولة: {actors}"
            )
            if poster_url != "N/A":
                result = InlineQueryResultPhoto(
                    id=imdb_id,
                    photo_url=poster_url,
                    thumbnail_url=poster_url,
                    caption=reply_text[:1024],
                    parse_mode="HTML"
                )
            else:
                result = InlineQueryResultArticle(
                    id=imdb_id,
                    title=title,
                    description=plot[:100],
                    input_message_content=InputTextMessageContent(reply_text, parse_mode="HTML")
                )
            results.append(result)
    
    # نتايج قريبة
    movie_titles = ["The Godfather", "Inception", "The Matrix", "Vikings", "Breaking Bad", "Hannibal", "The Walking Dead", "Interstellar", "Fight Club", "Pulp Fiction"]
    for title in movie_titles:
        if len(results) >= 3:
            break
        if query_text.lower() in title.lower() and title not in [r.title for r in results]:
            response = search_omdb(title)
            if response and response.get("Response") == "True":
                title = response.get("Title")
                plot = GoogleTranslator(source='auto', target='ar').translate(response.get("Plot", "غير متوفر"))
                year = response.get("Year", "غير معروف")
                rating = response.get("imdbRating", "غير معروف")
                genre = GoogleTranslator(source='auto', target='ar').translate(response.get("Genre", "غير معروف"))
                actors = response.get("Actors", "غير معروف")
                imdb_id = response.get("imdbID")
                poster_url = response.get("Poster", "N/A")
                
                if imdb_id not in seen_ids:
                    seen_ids.add(imdb_id)
                    reply_text = (
                        f"<b>{title}</b>\n"
                        f"<i>{plot[:150]}</i>\n"
                        f"📅 السنة: {year}\n"
                        f"⭐ التقييم: {rating}/10\n"
                        f"🎭 النوع: {genre}\n"
                        f"🌟 البطولة: {actors}"
                    )
                    if poster_url != "N/A":
                        result = InlineQueryResultPhoto(
                            id=imdb_id,
                            photo_url=poster_url,
                            thumbnail_url=poster_url,
                            caption=reply_text[:1024],
                            parse_mode="HTML"
                        )
                    else:
                        result = InlineQueryResultArticle(
                            id=imdb_id,
                            title=title,
                            description=plot[:100],
                            input_message_content=InputTextMessageContent(reply_text, parse_mode="HTML")
                        )
                    results.append(result)
    
    inline_cache[query_text] = results
    bot.answer_inline_query(query.id, results[:3], cache_time=60)

# 🟢 /suggest
@bot.message_handler(commands=['suggest'])
def handle_suggest(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if user_id in banned_users or user_id in muted_users:
        bot.reply_to(message, "<b>⚠️ تم حظرك أو كتمك!</b>", parse_mode="HTML")
        return
    
    user_count.add(user_id)
    if not is_allowed(chat_id) and not is_admin(user_id):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🌟 جربني في المجموعة", url="https://t.me/wk_paid"))
        markup.add(InlineKeyboardButton("المطور", url=f"https://t.me/{DEV_USERNAME[1:]}"))
        markup.add(InlineKeyboardButton("قناة البوت", url=f"https://t.me/{CHANNEL_USERNAME[1:]}"))
        bot.reply_to(message, PRIVATE_RESPONSE, parse_mode="HTML", reply_markup=markup)
        return
    
    if is_rate_limited(user_id):
        bot.reply_to(message, f"<b>⚠️ انتظر {RATE_LIMIT} ثوانٍ!</b>", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1 or not is_valid_request(text[1]):
        bot.reply_to(message, "<b>⚠️ حدد نوع التوصية</b>\nمثال: <code>/suggest رعب</code>", parse_mode="HTML")
        return
    
    genre = text[1].strip()
    if not is_valid_movie_input(genre):
        bot.reply_to(message, INVALID_INPUT_RESPONSE, parse_mode="HTML")
        return
    
    response = get_gemini_response(f"أعطني توصية لفيلم ومسلسل من نوع {genre} مع قصة مختصرة لكل منهما")
    if not response:
        bot.reply_to(message, "<b>⚡ السيرفر مشغول، جرب تاني!</b>", parse_mode="HTML")
        return
    
    formatted_response = format_response(response, keep_english_titles=True)
    reply_text = f"{random.choice(SYRIAN_RESPONSES)}\n\n{formatted_response}\n\n{get_random_footer()}"
    bot.reply_to(message, reply_text, parse_mode="HTML")

# 🟢 /random
@bot.message_handler(commands=['random'])
def handle_random(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if user_id in banned_users or user_id in muted_users:
        bot.reply_to(message, "<b>⚠️ تم حظرك أو كتمك!</b>", parse_mode="HTML")
        return
    
    user_count.add(user_id)
    if not is_allowed(chat_id) and not is_admin(user_id):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🌟 جربني في المجموعة", url="https://t.me/wk_paid"))
        markup.add(InlineKeyboardButton("المطور", url=f"https://t.me/{DEV_USERNAME[1:]}"))
        markup.add(InlineKeyboardButton("قناة البوت", url=f"https://t.me/{CHANNEL_USERNAME[1:]}"))
        bot.reply_to(message, PRIVATE_RESPONSE, parse_mode="HTML", reply_markup=markup)
        return
    
    if is_rate_limited(user_id):
        bot.reply_to(message, f"<b>⚠️ انتظر {RATE_LIMIT} ثوانٍ!</b>", parse_mode="HTML")
        return
    
    movie_response = get_gemini_response("أعطني توصية لفيلم عشوائي مع قصة مختصرة")
    series_response = get_gemini_response("أعطني توصية لمسلسل عشوائي مع قصة مختصرة")
    if not movie_response or not series_response:
        bot.reply_to(message, "<b>⚡ السيرفر مشغول، جرب تاني!</b>", parse_mode="HTML")
        return
    
    formatted_movie = format_response(movie_response, keep_english_titles=True)
    formatted_series = format_response(series_response, keep_english_titles=True)
    reply_text = f"{random.choice(RANDOM_RESPONSES)}\n\n{formatted_movie}\n\n{formatted_series}\n\n{get_random_footer()}"
    bot.reply_to(message, reply_text, parse_mode="HTML")

# 🟢 /actor
@bot.message_handler(commands=['actor'])
def handle_actor(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if user_id in banned_users or user_id in muted_users:
        bot.reply_to(message, "<b>⚠️ تم حظرك أو كتمك!</b>", parse_mode="HTML")
        return
    
    user_count.add(user_id)
    if is_rate_limited(user_id):
        bot.reply_to(message, f"<b>⚠️ انتظر {RATE_LIMIT} ثوانٍ!</b>", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ حدد اسم الممثل</b>\nمثال: <code>/actor Tom Hanks</code>", parse_mode="HTML")
        return
    
    actor = text[1].strip()
    if not is_valid_movie_input(actor):
        bot.reply_to(message, INVALID_INPUT_RESPONSE, parse_mode="HTML")
        return
    
    response = get_gemini_response(f"أعطني قائمة بأفضل أفلام أو مسلسلات الممثل {actor} مع قصة مختصرة لكل منهما")
    if not response:
        bot.reply_to(message, "<b>⚡ السيرفر مشغول، جرب تاني!</b>", parse_mode="HTML")
        return
    
    formatted_response = format_response(response, keep_english_titles=True)
    bot.reply_to(message, f"<b>📌 أعمال {actor}:</b>\n\n{formatted_response}\n\n{get_random_footer()}", parse_mode="HTML")

# 🟢 /mindreader
@bot.message_handler(commands=['mindreader'])
def handle_mindreader(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if user_id in banned_users or user_id in muted_users:
        bot.reply_to(message, "<b>⚠️ تم حظرك أو كتمك!</b>", parse_mode="HTML")
        return
    
    user_count.add(user_id)
    if not is_allowed(chat_id) and not (is_admin(user_id) or enable_all_private):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🌟 جربني في المجموعة", url="https://t.me/wk_paid"))
        markup.add(InlineKeyboardButton("المطور", url=f"https://t.me/{DEV_USERNAME[1:]}"))
        markup.add(InlineKeyboardButton("قناة البوت", url=f"https://t.me/{CHANNEL_USERNAME[1:]}"))
        bot.reply_to(message, PRIVATE_RESPONSE, parse_mode="HTML", reply_markup=markup)
        return
    
    if is_rate_limited(user_id):
        bot.reply_to(message, f"<b>⚠️ انتظر {RATE_LIMIT} ثوانٍ!</b>", parse_mode="HTML")
        return
    
    questions = [
        "1. نوع الفيلم المفضل؟ (أكشن، كوميدي، رعب، إلخ)",
        "2. قصير أم طويل؟",
        "3. مزاجك اليوم؟ (سعيد، حزين، متحمس، إلخ)"
    ]
    waiting_message = bot.reply_to(message, "🧠 سأقرأ أفكارك!\n\n" + "\n".join(questions))
    bot.register_next_step_handler(waiting_message, process_mindreader_answers)

def process_mindreader_answers(message):
    answers = message.text.split("\n")
    if len(answers) != 3:
        bot.reply_to(message, "<b>⚠️ أجب على الثلاثة!</b>", parse_mode="HTML")
        return
    
    prompt = (
        f"Based on these:\n"
        f"1. Genre: {answers[0]}\n"
        f"2. Length: {answers[1]}\n"
        f"3. Mood: {answers[2]}\n"
        f"Recommend one movie with English title and Arabic plot summary."
    )
    response = get_gemini_response(prompt)
    if not response:
        bot.reply_to(message, "<b>⚡ السيرفر مشغول، جرب تاني!</b>", parse_mode="HTML")
        return
    
    formatted_response = format_response(response, keep_english_titles=True)
    bot.reply_to(message, f"<b>🧠 توقعت فيلمك:</b>\n\n{formatted_response}\n\n{get_random_footer()}", parse_mode="HTML")

# 🟢 /detective
@bot.message_handler(commands=['detective'])
def handle_detective(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if user_id in banned_users or user_id in muted_users:
        bot.reply_to(message, "<b>⚠️ تم حظرك أو كتمك!</b>", parse_mode="HTML")
        return
    
    user_count.add(user_id)
    if not is_allowed(chat_id) and not (is_admin(user_id) or enable_all_private):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🌟 جربني في المجموعة", url="https://t.me/wk_paid"))
        markup.add(InlineKeyboardButton("المطور", url=f"https://t.me/{DEV_USERNAME[1:]}"))
        markup.add(InlineKeyboardButton("قناة البوت", url=f"https://t.me/{CHANNEL_USERNAME[1:]}"))
        bot.reply_to(message, PRIVATE_RESPONSE, parse_mode="HTML", reply_markup=markup)
        return
    
    if is_rate_limited(user_id):
        bot.reply_to(message, f"<b>⚠️ انتظر {RATE_LIMIT} ثوانٍ!</b>", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ حدد اسم الفيلم</b>\nمثال: <code>/detective Inception</code>", parse_mode="HTML")
        return
    
    movie = text[1].strip()
    if not is_valid_movie_input(movie):
        bot.reply_to(message, INVALID_INPUT_RESPONSE, parse_mode="HTML")
        return
    
    response = get_gemini_response(f"اشرح نهاية الفيلم {movie} بطريقة عبقرية وساخرة")
    if not response:
        bot.reply_to(message, "<b>⚡ السيرفر مشغول، جرب تاني!</b>", parse_mode="HTML")
        return
    
    formatted_response = format_response(response, keep_english_titles=True)
    bot.reply_to(message, f"<b>🔍 تحليل نهاية {movie}:</b>\n\n{formatted_response}", parse_mode="HTML")

# 🟢 /plotwist
@bot.message_handler(commands=['plotwist'])
def handle_plotwist(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if user_id in banned_users or user_id in muted_users:
        bot.reply_to(message, "<b>⚠️ تم حظرك أو كتمك!</b>", parse_mode="HTML")
        return
    
    user_count.add(user_id)
    if not is_allowed(chat_id) and not (is_admin(user_id) or enable_all_private):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🌟 جربني في المجموعة", url="https://t.me/wk_paid"))
        markup.add(InlineKeyboardButton("المطور", url=f"https://t.me/{DEV_USERNAME[1:]}"))
        markup.add(InlineKeyboardButton("قناة البوت", url=f"https://t.me/{CHANNEL_USERNAME[1:]}"))
        bot.reply_to(message, PRIVATE_RESPONSE, parse_mode="HTML", reply_markup=markup)
        return
    
    if is_rate_limited(user_id):
        bot.reply_to(message, f"<b>⚠️ انتظر {RATE_LIMIT} ثوانٍ!</b>", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ حدد اسم الفيلم</b>\nمثال: <code>/plotwist The Dark Knight</code>", parse_mode="HTML")
        return
    
    movie = text[1].strip()
    if not is_valid_movie_input(movie):
        bot.reply_to(message, INVALID_INPUT_RESPONSE, parse_mode="HTML")
        return
    
    response = get_gemini_response(f"ضع نهاية مجنونة جديدة للفيلم {movie}")
    if not response:
        bot.reply_to(message, "<b>⚡ السيرفر مشغول، جرب تاني!</b>", parse_mode="HTML")
        return
    
    formatted_response = format_response(response, keep_english_titles=True)
    bot.reply_to(message, f"<b>🌀 حبكة جديدة لـ {movie}:</b>\n\n{formatted_response}", parse_mode="HTML")

# 🟢 /aiwriter
@bot.message_handler(commands=['aiwriter'])
def handle_aiwriter(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if user_id in banned_users or user_id in muted_users:
        bot.reply_to(message, "<b>⚠️ تم حظرك أو كتمك!</b>", parse_mode="HTML")
        return
    
    user_count.add(user_id)
    if not is_allowed(chat_id) and not (is_admin(user_id) or enable_all_private):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🌟 جربني في المجموعة", url="https://t.me/wk_paid"))
        markup.add(InlineKeyboardButton("المطور", url=f"https://t.me/{DEV_USERNAME[1:]}"))
        markup.add(InlineKeyboardButton("قناة البوت", url=f"https://t.me/{CHANNEL_USERNAME[1:]}"))
        bot.reply_to(message, PRIVATE_RESPONSE, parse_mode="HTML", reply_markup=markup)
        return
    
    if is_rate_limited(user_id):
        bot.reply_to(message, f"<b>⚠️ انتظر {RATE_LIMIT} ثوانٍ!</b>", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ حدد تفاصيل الفيلم</b>\nمثال: <code>/aiwriter أكشن مستقبلي</code>", parse_mode="HTML")
        return
    
    details = text[1].strip()
    if not is_valid_movie_input(details):
        bot.reply_to(message, INVALID_INPUT_RESPONSE, parse_mode="HTML")
        return
    
    response = get_gemini_response(f"أنشئ حبكة فيلم بناءً على: {details}")
    if not response:
        bot.reply_to(message, "<b>⚡ السيرفر مشغول، جرب تاني!</b>", parse_mode="HTML")
        return
    
    formatted_response = format_response(response, keep_english_titles=True)
    bot.reply_to(message, f"<b>🎬 حبكة الفيلم:</b>\n\n{formatted_response}", parse_mode="HTML")

# 🟢 /realityshift
@bot.message_handler(commands=['realityshift'])
def handle_realityshift(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if user_id in banned_users or user_id in muted_users:
        bot.reply_to(message, "<b>⚠️ تم حظرك أو كتمك!</b>", parse_mode="HTML")
        return
    
    user_count.add(user_id)
    if not is_allowed(chat_id) and not (is_admin(user_id) or enable_all_private):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🌟 جربني في المجموعة", url="https://t.me/wk_paid"))
        markup.add(InlineKeyboardButton("المطور", url=f"https://t.me/{DEV_USERNAME[1:]}"))
        markup.add(InlineKeyboardButton("قناة البوت", url=f"https://t.me/{CHANNEL_USERNAME[1:]}"))
        bot.reply_to(message, PRIVATE_RESPONSE, parse_mode="HTML", reply_markup=markup)
        return
    
    if is_rate_limited(user_id):
        bot.reply_to(message, f"<b>⚠️ انتظر {RATE_LIMIT} ثوانٍ!</b>", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ حدد حدثًا</b>\nمثال: <code>/realityshift تخاصمت مع صديق</code>", parse_mode="HTML")
        return
    
    event = text[1].strip()
    if not is_valid_movie_input(event):
        bot.reply_to(message, INVALID_INPUT_RESPONSE, parse_mode="HTML")
        return
    
    response = get_gemini_response(f"حول هذا الحدث إلى فيلم هوليوودي: {event}")
    if not response:
        bot.reply_to(message, "<b>⚡ السيرفر مشغول، جرب تاني!</b>", parse_mode="HTML")
        return
    
    formatted_response = format_response(response, keep_english_titles=True)
    bot.reply_to(message, f"<b>🎭 فيلمك الهوليوودي:</b>\n\n{formatted_response}", parse_mode="HTML")

# 🟢 /spoilermaster
@bot.message_handler(commands=['spoilermaster'])
def handle_spoilermaster(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if user_id in banned_users or user_id in muted_users:
        bot.reply_to(message, "<b>⚠️ تم حظرك أو كتمك!</b>", parse_mode="HTML")
        return
    
    user_count.add(user_id)
    if is_rate_limited(user_id):
        bot.reply_to(message, f"<b>⚠️ انتظر {RATE_LIMIT} ثوانٍ!</b>", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ حدد اسم الفيلم</b>\nمثال: <code>/spoilermaster Hannibal</code>", parse_mode="HTML")
        return
    
    movie = text[1].strip()
    if not is_valid_movie_input(movie):
        bot.reply_to(message, INVALID_INPUT_RESPONSE, parse_mode="HTML")
        return
    
    response = get_gemini_response(f"حرق الفيلم أو المسلسل {movie} بأسلوب عامي سوري")
    if not response:
        bot.reply_to(message, "<b>⚡ السيرفر مشغول، جرب تاني!</b>", parse_mode="HTML")
        return
    
    formatted_response = format_response(response, keep_english_titles=True)
    reply_text = f"<b>🔥 حرق {movie}:</b>\n\n{formatted_response}"
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
        bot.answer_callback_query(call.id, f"⚠️ انتظر {RATE_LIMIT} ثوانٍ!")
        return
    
    style, movie = call.data.split(":", 1)
    if style == "spoil_dramatic":
        prompt = f"حرق الفيلم أو المسلسل {movie} بأسلوب درامي مؤثر"
    elif style == "spoil_syrian":
        prompt = f"حرق الفيلم أو المسلسل {movie} بأسلوب عامي سوري"
    elif style == "spoil_sarcastic":
        prompt = f"حرق الفيلم أو المسلسل {movie} بأسلوب ساخر"
    
    response = get_gemini_response(prompt)
    if not response:
        bot.edit_message_text("<b>⚡ السيرفر مشغول، جرب تاني!</b>", chat_id, call.message.message_id, parse_mode="HTML")
        bot.answer_callback_query(call.id, "السيرفر مشغول!")
        return
    
    formatted_response = format_response(response, keep_english_titles=True)
    reply_text = f"<b>🔥 حرق {movie} ({style.split('_')[1]}):</b>\n\n{formatted_response}"
    bot.edit_message_text(reply_text, chat_id, call.message.message_id, parse_mode="HTML")
    bot.answer_callback_query(call.id, "تم تحديث الحرق!")

# 🟢 /imdb (بحث محسن)
@bot.message_handler(commands=['imdb'])
def handle_imdb(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if user_id in banned_users or user_id in muted_users:
        bot.reply_to(message, "<b>⚠️ تم حظرك أو كتمك!</b>", parse_mode="HTML")
        return
    
    user_count.add(user_id)
    if is_rate_limited(user_id):
        bot.reply_to(message, f"<b>⚠️ انتظر {RATE_LIMIT} ثوانٍ!</b>", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ حدد اسم الفيلم</b>\nمثال: <code>/imdb The Matrix</code>", parse_mode="HTML")
        return
    
    query = text[1].strip()
    if not is_valid_movie_input(query):
        bot.reply_to(message, INVALID_INPUT_RESPONSE, parse_mode="HTML")
        return
    
    response = search_omdb(query)
    if not response or response.get("Response") != "True":
        movie_titles = ["The Godfather", "Inception", "The Matrix", "Vikings", "Breaking Bad", "Hannibal", "The Walking Dead", "Interstellar", "Fight Club", "Pulp Fiction"]
        results = []
        for title in movie_titles:
            if query.lower() in title.lower():
                alt_response = search_omdb(title)
                if alt_response and alt_response.get("Response") == "True":
                    results.append(alt_response)
            if len(results) >= 3:
                break
        
        if not results:
            bot.reply_to(message, "<b>⚡ لم أجد نتائج، جرب اسم تاني!</b>", parse_mode="HTML")
            return
        
        reply_text = "<b>نتايج قريبة:</b>\n\n"
        for res in results:
            title = res.get("Title")
            plot = GoogleTranslator(source='auto', target='ar').translate(res.get("Plot", "غير متوفر"))
            year = res.get("Year", "غير معروف")
            reply_text += f"<b>{title}</b>\n<i>{plot[:150]}</i>\n📅 السنة: {year}\n\n"
        bot.reply_to(message, reply_text + get_random_footer(), parse_mode="HTML")
        return
    
    title = response.get("Title")
    plot = GoogleTranslator(source='auto', target='ar').translate(response.get("Plot", "غير متوفر"))
    year = response.get("Year", "غير معروف")
    rating = response.get("imdbRating", "غير معروف")
    genre = GoogleTranslator(source='auto', target='ar').translate(response.get("Genre", "غير معروف"))
    runtime = response.get("Runtime", "غير معروف")
    director = GoogleTranslator(source='auto', target='ar').translate(response.get("Director", "غير معروف"))
    actors = response.get("Actors", "غير معروف")
    poster_url = response.get("Poster", "N/A")
    
    reply_text = (
        f"<b>{title}</b>\n"
        f"<i>{plot}</i>\n"
        f"📅 السنة: {year}\n"
        f"⭐ التقييم: {rating}/10\n"
        f"🎭 النوع: {genre}\n"
        f"⏱️ المدة: {runtime}\n"
        f"🎥 الإخراج: {director}\n"
        f"🌟 البطولة: {actors}\n\n"
        f"{get_random_footer()}"
    )
    if poster_url != "N/A":
        bot.send_photo(chat_id, poster_url, caption=reply_text[:1024], parse_mode="HTML")
    else:
        bot.reply_to(message, reply_text, parse_mode="HTML")

# 🟢 /elcinema (مضمون 100%)
@bot.message_handler(commands=['elcinema'])
def handle_elcinema(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if user_id in banned_users or user_id in muted_users:
        bot.reply_to(message, "<b>⚠️ تم حظرك أو كتمك!</b>", parse_mode="HTML")
        return
    
    user_count.add(user_id)
    if is_rate_limited(user_id):
        bot.reply_to(message, f"<b>⚠️ انتظر {RATE_LIMIT} ثوانٍ!</b>", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ حدد اسم الفيلم</b>\nمثال: <code>/elcinema لعبة نيوتن</code>", parse_mode="HTML")
        return
    
    query = text[1].strip()
    if not is_valid_movie_input(query):
        bot.reply_to(message, INVALID_INPUT_RESPONSE, parse_mode="HTML")
        return
    
    result = search_elcinema(query)
    if not result:
        bot.reply_to(message, "<b>⚡ لم أجد نتائج في السينما كوم، جرب تاني!</b>", parse_mode="HTML")
        return
    
    reply_text = (
        f"<b>{result['title']}</b>\n"
        f"<i>{result['details']}</i>\n"
        f"<a href='{result['link']}'>رابط الصفحة</a>\n\n"
        f"{get_random_footer()}"
    )
    bot.reply_to(message, reply_text, parse_mode="HTML", disable_web_page_preview=True)

# 🟢 /wk (مع أوامر مطور مفيدة)
@bot.message_handler(commands=['wk'])
def handle_admin_panel(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "هذه لائحة لأوامر المطور، لا يمكنك استخدامها 🫡", parse_mode="HTML")
        return
    
    help_text = (
        "<b>أوامر المطور:</b>\n\n"
        "/broadcast [نص] - إرسال رسالة بث\n"
        "/stats - عرض إحصائيات البوت\n"
        "/clear - مسح الذاكرة\n"
        "/ban_user [user_id] - حظر مستخدم\n"
        "/unban_user [user_id] - رفع الحظر\n"
        "/mute [user_id] - كتم مستخدم\n"
        "/unmute [user_id] - رفع الكتم\n"
        "/check_user [user_id] - فحص حالة مستخدم\n"
        "/enable_all - تفعيل الأوامر في الخاص لساعة\n"
        "/restart - إعادة تشغيل البوت\n"
        "/log - عرض آخر 10 أخطاء\n"
        "/update_api_key [key] - تحديث مفتاح Gemini\n"
        "/test_speed - اختبار السرعة\n"
        "/add_admin [user_id] - إضافة مطور\n"
        "/remove_admin [user_id] - حذف مطور\n"
        "/export_users - تصدير المستخدمين\n"
        "/set_rate_limit [ثوانٍ] - ضبط حد التكرار\n"
        "/list_admins - قايمة المطورين\n"
        "/ping - فحص البوت\n"
        "/restart_server - إعادة تشغيل السيرفر\n"
        "/check_load - فحص تحميل السيرفر\n"
        "/toggle_private - تفعيل/تعطيل الخاص\n\n"
        f"{get_random_footer()}"
    )
    bot.reply_to(message, help_text, parse_mode="HTML")

# 🟢 أوامر المطور
@bot.message_handler(commands=['broadcast'])
def handle_broadcast(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "هذه لائحة لأوامر المطور، لا يمكنك استخدامها 🫡", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ أدخل نص البث</b>\nمثال: <code>/broadcast تحديث جديد!</code>", parse_mode="HTML")
        return
    
    broadcast_msg = text[1]
    for user in user_count:
        try:
            bot.send_message(user, f"<b>رسالة من المطور:</b>\n\n{broadcast_msg}", parse_mode="HTML")
        except Exception as e:
            logging.error(f"⚠️ Broadcast Error for {user}: {str(e)}")
    try:
        bot.send_message(ALLOWED_GROUP_ID, f"<b>رسالة من المطور:</b>\n\n{broadcast_msg}", parse_mode="HTML")
    except Exception as e:
        logging.error(f"⚠️ Broadcast Error for group: {str(e)}")
    bot.reply_to(message, "<b>✅ تم إرسال البث!</b>", parse_mode="HTML")

@bot.message_handler(commands=['stats'])
def handle_stats(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "هذه لائحة لأوامر المطور، لا يمكنك استخدامها 🫡", parse_mode="HTML")
        return
    
    stats_text = (
        f"<b>إحصائيات البوت:</b>\n\n"
        f"عدد المستخدمين: {len(user_count)}\n"
        f"عدد المحظورين: {len(banned_users)}\n"
        f"عدد المكتومين: {len(muted_users)}\n"
        f"عدد المطورين: {len(ADMIN_IDS)}\n"
        f"حد التكرار: {RATE_LIMIT} ث\n\n"
        f"{get_random_footer()}"
    )
    bot.reply_to(message, stats_text, parse_mode="HTML")

@bot.message_handler(commands=['clear'])
def handle_clear(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "هذه لائحة لأوامر المطور، لا يمكنك استخدامها 🫡", parse_mode="HTML")
        return
    
    user_last_request.clear()
    user_request_times.clear()
    inline_cache.clear()
    omdb_cache.clear()
    bot.reply_to(message, "<b>✅ تم مسح الذاكرة!</b>", parse_mode="HTML")

@bot.message_handler(commands=['ban_user'])
def handle_ban_user(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "هذه لائحة لأوامر المطور، لا يمكنك استخدامها 🫡", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ أدخل معرف المستخدم</b>\nمثال: <code>/ban_user 123456789</code>", parse_mode="HTML")
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
        bot.reply_to(message, "هذه لائحة لأوامر المطور، لا يمكنك استخدامها 🫡", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ أدخل معرف المستخدم</b>\nمثال: <code>/unban_user 123456789</code>", parse_mode="HTML")
        return
    
    try:
        target_id = int(text[1])
        banned_users.discard(target_id)
        bot.reply_to(message, f"<b>✅ تم رفع الحظر عن {target_id}!</b>", parse_mode="HTML")
    except ValueError:
        bot.reply_to(message, "<b>⚠️ معرف غير صالح!</b>", parse_mode="HTML")

@bot.message_handler(commands=['mute'])
def handle_mute(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "هذه لائحة لأوامر المطور، لا يمكنك استخدامها 🫡", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ أدخل معرف المستخدم</b>\nمثال: <code>/mute 123456789</code>", parse_mode="HTML")
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
        bot.reply_to(message, "هذه لائحة لأوامر المطور، لا يمكنك استخدامها 🫡", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ أدخل معرف المستخدم</b>\nمثال: <code>/unmute 123456789</code>", parse_mode="HTML")
        return
    
    try:
        target_id = int(text[1])
        muted_users.discard(target_id)
        bot.reply_to(message, f"<b>✅ تم رفع الكتم عن {target_id}!</b>", parse_mode="HTML")
    except ValueError:
        bot.reply_to(message, "<b>⚠️ معرف غير صالح!</b>", parse_mode="HTML")

@bot.message_handler(commands=['check_user'])
def handle_check_user(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "هذه لائحة لأوامر المطور، لا يمكنك استخدامها 🫡", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ أدخل معرف المستخدم</b>\nمثال: <code>/check_user 123456789</code>", parse_mode="HTML")
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
        bot.reply_to(message, f"<b>ℹ️ حالة {target_id}:</b> {status}", parse_mode="HTML")
    except ValueError:
        bot.reply_to(message, "<b>⚠️ معرف غير صالح!</b>", parse_mode="HTML")

@bot.message_handler(commands=['enable_all'])
def handle_enable_all(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "هذه لائحة لأوامر المطور، لا يمكنك استخدامها 🫡", parse_mode="HTML")
        return
    
    global enable_all_private
    enable_all_private = True
    bot.reply_to(message, "<b>✅ تم تفعيل الأوامر في الخاص لساعة!</b>", parse_mode="HTML")
    threading.Timer(3600, disable_all_private).start()

def disable_all_private():
    global enable_all_private
    enable_all_private = False
    for admin in ADMIN_IDS:
        try:
            bot.send_message(admin, "<b>⚠️ انتهت مدة تفعيل الأوامر في الخاص!</b>", parse_mode="HTML")
        except:
            pass

@bot.message_handler(commands=['restart'])
def handle_restart(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "هذه لائحة لأوامر المطور، لا يمكنك استخدامها 🫡", parse_mode="HTML")
        return
    
    bot.reply_to(message, "<b>🔄 جاري إعادة التشغيل...</b>", parse_mode="HTML")
    os._exit(0)

@bot.message_handler(commands=['log'])
def handle_log(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "هذه لائحة لأوامر المطور، لا يمكنك استخدامها 🫡", parse_mode="HTML")
        return
    
    try:
        with open('bot_errors.log', 'r', encoding='utf-8') as log_file:
            lines = log_file.readlines()[-10:]
            log_text = "\n".join(lines)
        bot.reply_to(message, f"<b>📜 آخر 10 أخطاء:</b>\n\n{log_text}", parse_mode="HTML")
    except Exception as e:
        logging.error(f"⚠️ Log Error: {str(e)}")
        bot.reply_to(message, "<b>⚠️ فشل جلب السجل!</b>", parse_mode="HTML")

@bot.message_handler(commands=['update_api_key'])
def handle_update_api_key(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "هذه لائحة لأوامر المطور، لا يمكنك استخدامها 🫡", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ أدخل مفتاح API</b>\nمثال: <code>/update_api_key new_key</code>", parse_mode="HTML")
        return
    
    global GEMINI_API_KEY
    GEMINI_API_KEY = text[1]
    bot.reply_to(message, "<b>✅ تم تحديث مفتاح Gemini!</b>", parse_mode="HTML")

@bot.message_handler(commands=['test_speed'])
def handle_test_speed(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "هذه لائحة لأوامر المطور، لا يمكنك استخدامها 🫡", parse_mode="HTML")
        return
    
    start_time = time.time()
    response = get_gemini_response("أعطني جملة اختبار")
    end_time = time.time()
    speed = end_time - start_time
    bot.reply_to(message, f"<b>⏱️ السرعة: {speed:.2f} ث</b>\n\n{get_random_footer()}", parse_mode="HTML")

@bot.message_handler(commands=['add_admin'])
def handle_add_admin(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "هذه لائحة لأوامر المطور، لا يمكنك استخدامها 🫡", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ أدخل معرف المطور</b>\nمثال: <code>/add_admin 123456789</code>", parse_mode="HTML")
        return
    
    try:
        new_admin_id = int(text[1])
        ADMIN_IDS.add(new_admin_id)
        bot.reply_to(message, f"<b>✅ تم إضافة المطور {new_admin_id}!</b>", parse_mode="HTML")
    except ValueError:
        bot.reply_to(message, "<b>⚠️ معرف غير صالح!</b>", parse_mode="HTML")

@bot.message_handler(commands=['remove_admin'])
def handle_remove_admin(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "هذه لائحة لأوامر المطور، لا يمكنك استخدامها 🫡", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ أدخل معرف المطور</b>\nمثال: <code>/remove_admin 123456789</code>", parse_mode="HTML")
        return
    
    try:
        admin_id = int(text[1])
        if admin_id == int(DEV_ID):
            bot.reply_to(message, "<b>⚠️ لا يمكن حذف المطور الأساسي!</b>", parse_mode="HTML")
            return
        ADMIN_IDS.discard(admin_id)
        bot.reply_to(message, f"<b>✅ تم حذف المطور {admin_id}!</b>", parse_mode="HTML")
    except ValueError:
        bot.reply_to(message, "<b>⚠️ معرف غير صالح!</b>", parse_mode="HTML")

@bot.message_handler(commands=['export_users'])
def handle_export_users(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "هذه لائحة لأوامر المطور، لا يمكنك استخدامها 🫡", parse_mode="HTML")
        return
    
    try:
        with open("users_export.txt", "w", encoding='utf-8') as f:
            f.write("\n".join(map(str, user_count)))
        with open("users_export.txt", "rb") as f:
            bot.send_document(user_id, f, caption="قايمة المستخدمين")
        os.remove("users_export.txt")
        bot.reply_to(message, "<b>✅ تم تصدير المستخدمين!</b>", parse_mode="HTML")
    except Exception as e:
        logging.error(f"⚠️ Export Users Error: {str(e)}")
        bot.reply_to(message, "<b>⚠️ فشل التصدير!</b>", parse_mode="HTML")

@bot.message_handler(commands=['set_rate_limit'])
def handle_set_rate_limit(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "هذه لائحة لأوامر المطور، لا يمكنك استخدامها 🫡", parse_mode="HTML")
        return
    
    text = message.text.strip().split(maxsplit=1)
    if len(text) == 1:
        bot.reply_to(message, "<b>⚠️ أدخل عدد الثواني</b>\nمثال: <code>/set_rate_limit 10</code>", parse_mode="HTML")
        return
    
    try:
        new_limit = int(text[1])
        if new_limit < 1:
            bot.reply_to(message, "<b>⚠️ الحد الأدنى 1 ثانية!</b>", parse_mode="HTML")
            return
        global RATE_LIMIT
        RATE_LIMIT = new_limit
        bot.reply_to(message, f"<b>✅ تم ضبط الحد على {new_limit} ث!</b>", parse_mode="HTML")
    except ValueError:
        bot.reply_to(message, "<b>⚠️ أدخل رقمًا صحيحًا!</b>", parse_mode="HTML")

@bot.message_handler(commands=['list_admins'])
def handle_list_admins(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "هذه لائحة لأوامر المطور، لا يمكنك استخدامها 🫡", parse_mode="HTML")
        return
    
    admins_list = "\n".join([f"- {admin}" for admin in ADMIN_IDS])
    bot.reply_to(message, f"<b>👨‍💻 قايمة المطورين:</b>\n{admins_list}", parse_mode="HTML")

@bot.message_handler(commands=['ping'])
def handle_ping(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "هذه لائحة لأوامر المطور، لا يمكنك استخدامها 🫡", parse_mode="HTML")
        return
    
    start_time = time.time()
    end_time = time.time()
    ping_time = (end_time - start_time) * 1000
    bot.reply_to(message, f"<b>🏓 البوت شغال!</b>\nPing: {ping_time:.2f} ms", parse_mode="HTML")

@bot.message_handler(commands=['restart_server'])
def handle_restart_server(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "هذه لائحة لأوامر المطور، لا يمكنك استخدامها 🫡", parse_mode="HTML")
        return
    
    bot.reply_to(message, "<b>🔄 جاري إعادة تشغيل السيرفر...</b>", parse_mode="HTML")
    os._exit(0)

@bot.message_handler(commands=['check_load'])
def handle_check_load(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "هذه لائحة لأوامر المطور، لا يمكنك استخدامها 🫡", parse_mode="HTML")
        return
    
    try:
        import psutil
        cpu_usage = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        bot.reply_to(message, f"<b>📊 حالة السيرفر:</b>\nCPU: {cpu_usage}%\nذاكرة: {memory.percent}% مستخدمة", parse_mode="HTML")
    except ImportError:
        bot.reply_to(message, "<b>⚠️ يلزم تثبيت psutil!</b>\n<code>pip install psutil</code>", parse_mode="HTML")
    except Exception as e:
        logging.error(f"⚠️ Check Load Error: {str(e)}")
        bot.reply_to(message, "<b>⚠️ فشل فحص الحمل!</b>", parse_mode="HTML")

@bot.message_handler(commands=['toggle_private'])
def handle_toggle_private(message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "هذه لائحة لأوامر المطور، لا يمكنك استخدامها 🫡", parse_mode="HTML")
        return
    
    global enable_all_private
    enable_all_private = not enable_all_private
    status = "مفعل" if enable_all_private else "معطل"
    bot.reply_to(message, f"<b>🔐 الأوامر في الخاص: {status}</b>", parse_mode="HTML")
    if enable_all_private:
        threading.Timer(3600, disable_all_private).start()

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
        "<b>🎬 قائمة الأوامر:</b>\n\n"
        "/suggest [النوع] - توصية بناءً على النوع\n"
        "/random - فيلم ومسلسل عشوائي\n"
        "/actor [اسم الممثل] - أفضل أعمال ممثل\n"
        "/mindreader - توقع فيلم مناسب\n"
        "/detective [اسم الفيلم] - تحليل النهاية\n"
        "/plotwist [اسم الفيلم] - نهاية مجنونة\n"
        "/aiwriter [تفاصيل] - حبكة فيلم جديد\n"
        "/realityshift [حدث] - حياتك كفيلم\n"
        "/spoilermaster [اسم الفيلم] - حرق بأساليب متعددة\n"
        "/imdb [اسم الفيلم] - تفاصيل من IMDb\n"
        "/elcinema [اسم] - معلومات من السينما كوم\n"
    )
    bot.reply_to(message, help_text, parse_mode="HTML", reply_markup=markup)

# 🟢 الرسائل في الخاص
@bot.message_handler(func=lambda message: not is_allowed(message.chat.id))
def handle_private(message):
    user_id = message.from_user.id
    if user_id in banned_users or user_id in muted_users:
        bot.reply_to(message, "<b>⚠️ تم حظرك أو كتمك!</b>", parse_mode="HTML")
        return
    
    user_count.add(user_id)
    command = message.text.strip().split()[0] if message.text else ""
    allowed_private = ["/imdb", "/spoilermaster", "/actor", "/elcinema"]
    if command not in allowed_private and not (is_admin(user_id) or enable_all_private):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🌟 جربني في المجموعة", url="https://t.me/wk_paid"))
        markup.add(InlineKeyboardButton("المطور", url=f"https://t.me/{DEV_USERNAME[1:]}"))
        markup.add(InlineKeyboardButton("قناة البوت", url=f"https://t.me/{CHANNEL_USERNAME[1:]}"))
        bot.reply_to(message, PRIVATE_RESPONSE, parse_mode="HTML", reply_markup=markup)

# 🟢 إعداد الأوامر في القائمة
def set_bot_commands():
    commands = [
        BotCommand("suggest", "توصية بناءً على النوع"),
        BotCommand("random", "فيلم ومسلسل عشوائي"),
        BotCommand("actor", "أفضل أعمال ممثل"),
        BotCommand("mindreader", "توقع فيلم مناسب"),
        BotCommand("detective", "تحليل النهاية"),
        BotCommand("plotwist", "نهاية مجنونة"),
        BotCommand("aiwriter", "حبكة فيلم جديد"),
        BotCommand("realityshift", "حياتك كفيلم"),
        BotCommand("spoilermaster", "حرق بأساليب متعددة"),
        BotCommand("imdb", "تفاصيل من IMDb"),
        BotCommand("elcinema", "معلومات من السينما كوم")
    ]
    bot.set_my_commands(commands)

# 🟢 تشغيل البوت
if __name__ == "__main__":
    print("🚀 البوت جاهز على Contabo VPS!")
    try:
        set_bot_commands()
        bot.polling(none_stop=True, interval=0, timeout=3)
    except Exception as e:
        logging.error(f"⚠️ Polling Error: {str(e)}")
        print(f"حدث خطأ: {str(e)}. إعادة المحاولة...")
        time.sleep(5)
        bot.polling(none_stop=True, interval=0, timeout=3)