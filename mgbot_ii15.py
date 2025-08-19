import asyncio
import json
import os
import re
from datetime import datetime, timedelta
import logging
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

# ------------------ ЗАГРУЗКА .ENV ------------------
load_dotenv()

# ------------------ КОНФИГУРАЦИЯ И НАСТРОЙКИ ------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
CACHE_FILE = "doctors_cache.json"
CACHE_EXPIRE_HOURS = 3
MAX_DOCTORS = 5
LOG_FILE = "logs.txt"

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN не найден. Добавь его в переменные окружения или .env")
if not YANDEX_FOLDER_ID:
    raise ValueError("❌ YANDEX_FOLDER_ID не найден. Добавь его в переменные окружения или .env")
if not YANDEX_API_KEY:
    raise ValueError("❌ YANDEX_API_KEY не найден. Добавь его в переменные окружения или .env")

# ------------------ ЛОГИРОВАНИЕ ------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def log_interaction(user: types.User, user_input: str, bot_response: str):
    """Записываем взаимодействие в файл"""
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                f"{user.full_name} (id={user.id})\n"
                f"  ➤ Запрос: {user_input}\n"
                f"  ➤ Ответ: {bot_response}\n\n")

# ------------------ СПЕЦИАЛИЗАЦИИ И СЛУЖЕБНЫЕ ФУНКЦИИ ------------------
SPECIALIZATIONS = {
    "Гинеколог": "ginekolog",
    "Офтальмолог": "oftalmolog",
    "Врач УЗИ": "ultrazvukovoy-diagnost",
    "Маммолог": "mammolog",
    "Уролог": "urolog",
    "Эндокринолог": "endokrinolog",
    "Терапевт": "terapevt",
    "Кардиолог": "kardiolog",
    "ЛОР": "otorinolaringolog",
    "Невролог": "nevrolog",
    "Дерматолог": "dermatolog",
    "Рентгенолог": "rentgenolog",
    "Пульмонолог": "pulmonolog",
    "Нутрициолог": "nutriciolog",
    "Травматолог": "travmatolog",
    "Психотерапевт": "psihoterapevt",
    "Ортопед": "ortoped",
    "Массажист": "massazhist",
    "Косметолог": "kosmetolog",
    "Онколог": "onkolog",
    "Нарколог": "narkolog",
    "Педиатр": "pediatr",
    "Психолог": "psiholog",
    "Флеболог": "flebolog",
    "Фтизиатр": "ftiziatr",
    "Эндоскопист": "endoskopist"
}

def get_main_keyboard():
    builder = ReplyKeyboardBuilder()
    for spec in SPECIALIZATIONS.keys():
        builder.add(KeyboardButton(text=spec))
    builder.add(KeyboardButton(text="Главное меню"))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

def get_start_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="🔵 Найти специалиста"))
    builder.add(KeyboardButton(text="🔴 Описать симптомы"))
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)

def get_back_to_menu_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="Главное меню"))
    return builder.as_markup(resize_keyboard=True)

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Ошибка чтения кэша: {e}")
            return {}
    return {}

def save_cache(cache):
    with open(CACHE_FILE, "w", encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

async def get_cached_doctors(spec_slug):
    cache = load_cache()
    if spec_slug in cache:
        cached_time = datetime.fromisoformat(cache[spec_slug]["time"])
        if datetime.now() - cached_time < timedelta(hours=CACHE_EXPIRE_HOURS):
            return cache[spec_slug]["data"]
    return None

def clean_phone(phone_text):
    if not phone_text or not isinstance(phone_text, str):
        return None
    cleaned = re.sub(r'[^0-9+]', '', phone_text)
    return cleaned if cleaned else None

async def update_progress(progress_msg, percent):
    try:
        await progress_msg.edit_text(f"🔍 Поиск врачей... {percent}%")
    except Exception:
        pass

async def ask_yandex_gpt(symptoms: str):
    """Запрос к YandexGPT для анализа симптомов"""
    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    headers = {
        "Authorization": f"Api-Key {YANDEX_API_KEY}",
        "Content-Type": "application/json"
    }
    prompt = f"""
Ты медицинский консультант. По описанию проблемы предложи 1-3 самых подходящих специалиста из доступных:
{", ".join(SPECIALIZATIONS.keys())}.
Также предложи краткий приблизительный диагноз.
"""
    payload = {
        "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt/latest",
        "completionOptions": {"stream": False, "temperature": 0.3, "maxTokens": 500},
        "messages": [{"role": "user", "text": prompt + "\n\n" + symptoms}]
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    return "Ошибка: Не удалось получить рекомендации."
                data = await resp.json()
                return data["result"]["alternatives"][0]["message"]["text"]
    except Exception as e:
        logger.error(f"Ошибка YandexGPT: {e}")
        return "Ошибка сервиса."

async def scrape_with_playwright(specialization_slug, chat_id, max_count=MAX_DOCTORS):
    base_url = "https://prodoctorov.ru"
    url = f"{base_url}/domodedovo/{specialization_slug}/"
    doctors = []
    progress_msg = None
    browser = None
    context = None
    page = None

    try:
        progress_msg = await bot.send_message(chat_id, "🔍 Поиск врачей... 0%")
        
        playwright = await async_playwright().start()
        await update_progress(progress_msg, 10)
        
        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--single-process"
            ]
        )
        await update_progress(progress_msg, 20)
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={'width': 1920, 'height': 1080},
            java_script_enabled=True
        )
        await update_progress(progress_msg, 30)
        
        page = await context.new_page()
        await update_progress(progress_msg, 40)
        
        # Блокируем ресурсы
        await page.route("**/*.{png,jpg,jpeg,webp,gif,svg}", lambda route: route.abort())
        await page.route("**/*.css", lambda route: route.abort())
        
        await update_progress(progress_msg, 50)
        await page.goto(url, timeout=60000, wait_until="domcontentloaded")
        await update_progress(progress_msg, 60)
        
        try:
            await page.wait_for_selector("div.b-doctor-card", timeout=15000)
            await update_progress(progress_msg, 70)
        except Exception as e:
            logger.warning(f"Не найдены карточки врачей: {e}")
            await update_progress(progress_msg, 100)
            await progress_msg.delete()
            return []
        
        content = await page.content()
        await update_progress(progress_msg, 80)
        
        soup = BeautifulSoup(content, "html.parser")
        cards = soup.select("div.b-doctor-card")[:max_count]
        
        if not cards:
            logger.warning("Карточки врачей не найдены")
            await update_progress(progress_msg, 100)
            await progress_msg.delete()
            return []

        for i, card in enumerate(cards):
            try:
                progress = 80 + int((i + 1) / len(cards) * 15)
                await update_progress(progress_msg, progress)
                
                name = card.select_one("span.b-doctor-card__name-surname")
                rating_el = card.select_one("div.b-stars-rate__progress")
                rating = "0.0"
                if rating_el and 'style' in rating_el.attrs:
                    try:
                        width_str = rating_el['style'].replace('width:', '').replace('em', '').strip()
                        rating = f"{round(float(width_str) / 1.28, 1)}"
                    except:
                        pass
                
                photo = card.select_one("img.b-profile-card__img")
                experience = card.select_one("div.b-doctor-card__experience .ui-text_subtitle-1")
                
                clinic = "Не указана"
                address = "Не указан"
                clinic_container = card.select_one("div.b-doctor-card__lpu-select")
                if clinic_container:
                    clinic_el = clinic_container.select_one("span.b-select__trigger-main-text")
                    address_el = clinic_container.select_one("span.b-select__trigger-adit-text")
                    if clinic_el:
                        clinic = clinic_el.get_text(strip=True)
                    if address_el:
                        address = address_el.get_text(strip=True)
                
                price = card.select_one(".b-doctor-card__price .ui-text_subtitle-1") or \
                        card.select_one(".b-doctor-card__tabs-wrapper_club fieldset .ui-text_subtitle-1")
                
                phone = card.select_one(".b-doctor-card__lpu-phone-container .b-doctor-card__lpu-phone") or \
                       card.select_one(".b-doctor-card__phone .ui-text_subtitle-1")
                
                phone_text = phone.get_text(strip=True) if phone else "Не указан"
                phone_clean = clean_phone(phone_text)

                doctor_data = {
                    "name": name.get_text(strip=True) if name else "Не указано",
                    "rating": rating,
                    "photo": base_url + photo["src"] if photo and photo.has_attr("src") else None,
                    "experience": experience.get_text(strip=True) if experience else "Не указан",
                    "clinic": clinic,
                    "address": address,
                    "price": price.get_text(strip=True).replace(u'\xa0', ' ') if price else "Не указана",
                    "phone": phone_text,
                    "phone_clean": phone_clean
                }
                doctors.append(doctor_data)
                
            except Exception as e:
                logger.error(f"Ошибка парсинга карточки: {e}")
                continue

        doctors.sort(key=lambda x: float(x['rating']), reverse=True)
        await update_progress(progress_msg, 100)
        await asyncio.sleep(1)
        if progress_msg:
            await progress_msg.delete()
        
        return doctors
        
    except Exception as e:
        logger.error(f"Ошибка парсинга: {e}")
        if progress_msg:
            try:
                await progress_msg.edit_text("⚠️ Ошибка при поиске врачей. Попробуйте позже.")
            except:
                pass
        return []
    finally:
        # Закрываем в правильном порядке
        try:
            if page:
                await page.close()
        except:
            pass
        try:
            if context:
                await context.close()
        except:
            pass
        try:
            if browser:
                await browser.close()
        except:
            pass
        try:
            if 'playwright' in locals():
                await playwright.stop()
        except:
            pass

# ------------------ FSM ------------------
class Form(StatesGroup):
    waiting_for_symptoms = State()
    waiting_for_choice = State()
    waiting_for_specialist_choice = State()

# ------------------ ОБРАБОТЧИКИ ------------------
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

@dp.message(F.text.in_(SPECIALIZATIONS.keys()), StateFilter(Form.waiting_for_specialist_choice))
async def handle_recommended_doctor_choice(message: types.Message, state: FSMContext):
    spec_name = message.text
    spec_slug = SPECIALIZATIONS[spec_name]
    user_data = await state.get_data()
    recommended_keyboard = user_data.get('recommended_keyboard')
    await send_doctors_list(message, spec_slug, spec_name, keyboard_to_keep=recommended_keyboard)

@dp.message(F.text.in_(SPECIALIZATIONS.keys()), StateFilter(None))
async def handle_direct_doctor_choice(message: types.Message, state: FSMContext):
    await state.clear()
    spec_name = message.text
    spec_slug = SPECIALIZATIONS[spec_name]
    await send_doctors_list(message, spec_slug, spec_name, keyboard_to_keep=get_back_to_menu_keyboard())

@dp.message(Command("start"))
@dp.message(F.text == "Главное меню")
async def start(message: types.Message, state: FSMContext):
    await state.clear()
    caption = (
        "👋 Добро пожаловать в <b>МедГид – Домодедово!</b> 🩺\n\n"
        "Что я умею:\n"
        "🔹 Найду лучших врачей по рейтингу\n"
        "🔹 Проанализирую симптомы и подскажу специалистов\n"
        "🔹 Покажу клиники, контакты и цены\n\n"
        "Выберите, как удобнее найти специалиста 👇"
    )
    try:
        with open("start.jpg", "rb") as img:
            await bot.send_photo(message.chat.id, photo=img, caption=caption, parse_mode="HTML", reply_markup=get_start_keyboard())
    except Exception:
        await message.answer(caption, parse_mode="HTML", reply_markup=get_start_keyboard())
    await state.set_state(Form.waiting_for_choice)

@dp.message(Form.waiting_for_choice, F.text == "🔵 Найти специалиста")
async def handle_find_specialist_choice(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Выберите специалиста из списка:", reply_markup=get_main_keyboard())

@dp.message(Form.waiting_for_choice, F.text == "🔴 Описать симптомы")
async def handle_describe_symptoms_choice(message: types.Message, state: FSMContext):
    await state.set_state(Form.waiting_for_symptoms)
    await message.answer("✍️ Опишите, что вас беспокоит:", reply_markup=get_back_to_menu_keyboard())

@dp.message(Form.waiting_for_symptoms)
async def handle_symptoms(message: types.Message, state: FSMContext):
    symptoms = message.text
    await message.answer("🔍 Анализирую симптомы...")
    yandex_response = await ask_yandex_gpt(symptoms)
    log_interaction(message.from_user, symptoms, yandex_response)

    if yandex_response.startswith("Ошибка"):
        await message.answer(yandex_response, reply_markup=get_back_to_menu_keyboard())
        await state.clear()
        return

    # Упрощенный парсинг ответа
    if "терапевт" in yandex_response.lower():
        specialists = ["Терапевт"]
    elif "невролог" in yandex_response.lower():
        specialists = ["Невролог"]
    else:
        specialists = ["Терапевт"]

    recommended_kb = ReplyKeyboardBuilder()
    for spec_name in specialists:
        recommended_kb.add(KeyboardButton(text=spec_name))
    recommended_kb.add(KeyboardButton(text="Главное меню"))
    recommended_kb.adjust(2)

    await state.update_data(recommended_keyboard=recommended_kb.as_markup(resize_keyboard=True))
    await message.answer(
        f"Рекомендую обратиться к: {', '.join(specialists)}\n\n"
        f"Нажмите на кнопку, чтобы увидеть список врачей.",
        reply_markup=recommended_kb.as_markup(resize_keyboard=True)
    )
    await state.set_state(Form.waiting_for_specialist_choice)

async def send_doctors_list(message, spec_slug, spec_name, keyboard_to_keep=None):
    doctors = await get_cached_doctors(spec_slug)
    from_cache = True
    
    if not doctors:
        from_cache = False
        doctors = await scrape_with_playwright(spec_slug, message.chat.id)

    if not doctors:
        await message.answer(f"😕 Не удалось найти врачей '{spec_name}'.", reply_markup=get_back_to_menu_keyboard())
        return

    if not from_cache and doctors:
        cache = load_cache()
        cache[spec_slug] = {
            "time": datetime.now().isoformat(),
            "data": doctors
        }
        save_cache(cache)

    await message.answer(f"⭐ **Врачи {spec_name}**", parse_mode="Markdown")

    for idx, doc in enumerate(doctors, 1):
        if doc.get('phone_clean'):
            phone_text = f'<a href="tel:{doc["phone_clean"]}">{doc["phone"]}</a>'
        else:
            phone_text = doc['phone']

        caption = (
            f"<b>{idx}. {doc['name']}</b> (⭐ {doc['rating']})\n"
            f"📅 Стаж: {doc['experience']}\n"
            f"🏥 Клиника: {doc['clinic']}\n"
            f"📍 Адрес: {doc['address']}\n"
            f"💰 Приём: {doc['price']}\n"
            f"📞 Телефон: {phone_text}"
        )

        try:
            if doc.get('photo'):
                await bot.send_photo(message.chat.id, photo=doc['photo'], caption=caption, parse_mode="HTML")
            else:
                await bot.send_message(message.chat.id, text=caption, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Ошибка отправки: {e}")
            plain_text = (
                f"{idx}. {doc['name']} (⭐ {doc['rating']})\n"
                f"Стаж: {doc['experience']}\n"
                f"Клиника: {doc['clinic']}\n"
                f"Адрес: {doc['address']}\n"
                f"Приём: {doc['price']}\n"
                f"Телефон: {doc['phone']}"
            )
            await bot.send_message(message.chat.id, text=plain_text)

    if keyboard_to_keep:
        await message.answer("✅ Готово!", reply_markup=keyboard_to_keep)
    else:
        await message.answer("✅ Готово!")

# ------------------ ЗАПУСК ------------------
async def main():
    logger.info("🚀 Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
