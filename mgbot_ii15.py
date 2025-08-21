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
from bs4 import BeautifulSoup
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

# ------------------ ЗАГРУЗКА .ENV ------------------
load_dotenv()

# ------------------ КОНФИГУРАЦИЯ И НАСТРОЙКИ ------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
CACHE_FILE = "doctors_cache.json"
USERS_FILE = "bot_users.json"
CACHE_EXPIRE_HOURS = 3
MAX_DOCTORS = 5
LOG_FILE = "logs.txt"
ADMIN_ID = 461119006  # Ваш CHAT_ID

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

# ------------------ УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ ------------------
def load_users():
    """Загружаем список пользователей"""
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []

def save_user(user_id: int, username: str, first_name: str, last_name: str = ""):
    """Сохраняем пользователя"""
    users = load_users()
    
    # Проверяем, есть ли уже пользователь
    user_exists = any(user['id'] == user_id for user in users)
    
    if not user_exists:
        users.append({
            "id": user_id,
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "joined_date": datetime.now().isoformat()
        })
        
        with open(USERS_FILE, "w", encoding='utf-8') as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
        logger.info(f"Новый пользователь: {username} (id={user_id})")

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
        if datetime.now() - cached_time < timedelta(hours=CACHE_EXpiRE_HOURS):
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
Ты опытный медицинский консультант. Проанализируй симптомы и предложи наиболее подходящих специалистов из этого списка:
{", ".join(SPECIALIZATIONS.keys())}

Формат ответа ДОЛЖЕН БЫТЬ ТОЧНО ТАКИМ:
Диагноз: [краткое описание возможного заболевания]. Специалисты: [Специалист1], [Специалист2]

Симптомы: {symptoms}
"""
    
    payload = {
        "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt/latest",
        "completionOptions": {"stream": False, "temperature": 0.7, "maxTokens": 500},
        "messages": [{"role": "user", "text": prompt}]
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=30) as resp:
                if resp.status != 200:
                    return "Ошибка: Не удалось получить рекомендации."
                
                data = await resp.json()
                return data["result"]["alternatives"][0]["message"]["text"]
                
    except Exception as e:
        logger.error(f"Ошибка YandexGPT: {e}")
        return "Ошибка сервиса."

async def scrape_doctors(specialization_slug, chat_id, max_count=MAX_DOCTORS):
    base_url = "https://prodoctorov.ru"
    url = f"{base_url}/domodedovo/{specialization_slug}/"
    doctors = []
    progress_msg = None

    try:
        progress_msg = await bot.send_message(chat_id, "🔍 Поиск врачей... 0%")
        await update_progress(progress_msg, 10)

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }

        await update_progress(progress_msg, 20)

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers, timeout=30) as response:
                    if response.status != 200:
                        await update_progress(progress_msg, 100)
                        await progress_msg.edit_text("⚠️ Не удалось загрузить страницу с врачами")
                        return []

                    html = await response.text()
                    await update_progress(progress_msg, 40)

            except Exception as e:
                logger.error(f"Ошибка HTTP запроса: {e}")
                await update_progress(progress_msg, 100)
                await progress_msg.edit_text("⚠️ Ошибка подключения")
                return []

        await update_progress(progress_msg, 60)

        soup = BeautifulSoup(html, 'html.parser')
        await update_progress(progress_msg, 70)
        
        cards = soup.select('div.b-doctor-card')
        
        if not cards:
            await update_progress(progress_msg, 100)
            await progress_msg.edit_text("😕 Врачи не найдены")
            return []

        await update_progress(progress_msg, 80)

        for i, card in enumerate(cards[:max_count]):
            try:
                progress = 80 + int((i + 1) / min(len(cards), max_count) * 15)
                await update_progress(progress_msg, progress)
                await asyncio.sleep(0.1)

                name_elem = card.select_one('span.b-doctor-card__name-surname')
                name = name_elem.get_text(strip=True) if name_elem else "Не указано"

                doctor_link = None
                link_selectors = [
                    'a.b-doctor-card__name',
                    'a[href*="/doctor/"]',
                    'a.b-doctor-card__link',
                ]
                
                for selector in link_selectors:
                    link_elem = card.select_one(selector)
                    if link_elem and link_elem.get('href'):
                        href = link_elem['href']
                        if href.startswith('/'):
                            doctor_link = base_url + href
                        elif href.startswith('http'):
                            doctor_link = href
                        break
                
                if not doctor_link:
                    any_link = card.select_one('a[href]')
                    if any_link and any_link.get('href'):
                        href = any_link['href']
                        if href.startswith('/'):
                            doctor_link = base_url + href
                        elif href.startswith('http'):
                            doctor_link = href

                rating_elem = card.select_one('div.b-stars-rate__progress')
                rating = "0.0"
                if rating_elem and rating_elem.get('style'):
                    try:
                        width_str = rating_elem['style'].replace('width:', '').replace('em', '').strip()
                        rating = f"{round(float(width_str) / 1.28, 1)}"
                    except:
                        pass

                photo_elem = card.select_one('img.b-profile-card__img')
                photo = None
                if photo_elem and photo_elem.get('src'):
                    photo_url = photo_elem['src']
                    photo = photo_url if photo_url.startswith('http') else base_url + photo_url

                experience_elem = card.select_one('div.b-doctor-card__experience .ui-text_subtitle-1')
                experience = experience_elem.get_text(strip=True) if experience_elem else "Не указан"

                clinic = "Не указана"
                address = "Не указан"
                clinic_container = card.select_one('div.b-doctor-card__lpu-select')
                if clinic_container:
                    clinic_elem = clinic_container.select_one('span.b-select__trigger-main-text')
                    address_elem = clinic_container.select_one('span.b-select__trigger-adit-text')
                    clinic = clinic_elem.get_text(strip=True) if clinic_elem else "Не указана"
                    address = address_elem.get_text(strip=True) if address_elem else "Не указан"

                price = "Не указана"
                price_elems = [
                    '.b-doctor-card__price .ui-text_subtitle-1',
                    '.b-doctor-card__tabs-wrapper_club fieldset .ui-text_subtitle-1',
                ]
                for selector in price_elems:
                    price_elem = card.select_one(selector)
                    if price_elem and price_elem.get_text(strip=True):
                        price = price_elem.get_text(strip=True).replace(u'\xa0', ' ')
                        break

                phone = "Не указан"
                phone_clean = None
                phone_elems = [
                    '.b-doctor-card__lpu-phone-container .b-doctor-card__lpu-phone',
                    '.b-doctor-card__phone .ui-text_subtitle-1',
                ]
                for selector in phone_elems:
                    phone_elem = card.select_one(selector)
                    if phone_elem and phone_elem.get_text(strip=True):
                        phone = phone_elem.get_text(strip=True)
                        phone_clean = clean_phone(phone)
                        break

                doctors.append({
                    'name': name,
                    'link': doctor_link,
                    'rating': rating,
                    'photo': photo,
                    'experience': experience,
                    'clinic': clinic,
                    'address': address,
                    'price': price,
                    'phone': phone,
                    'phone_clean': phone_clean
                })

            except Exception as e:
                logger.error(f"Ошибка парсинга карточки {i}: {e}")
                continue

        await update_progress(progress_msg, 95)
        doctors.sort(key=lambda x: float(x['rating']), reverse=True)
        await update_progress(progress_msg, 100)
        await asyncio.sleep(1)
        
        if progress_msg:
            await progress_msg.delete()

        logger.info(f"Найдено {len(doctors)} врачей для {specialization_slug}")
        return doctors

    except Exception as e:
        logger.error(f"Общая ошибка парсинга: {e}")
        if progress_msg:
            try:
                await progress_msg.edit_text("⚠️ Ошибка при поиске врачей")
            except:
                pass
        return []

# ------------------ FSM ------------------
class Form(StatesGroup):
    waiting_for_symptoms = State()
    waiting_for_choice = State()
    waiting_for_specialist_choice = State()

# ------------------ ОБРАБОТЧИКИ ------------------
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# ------------------ РАССЫЛКА ------------------
async def broadcast_message(message_text: str, photo_path: str = None, document_path: str = None):
    """Отправка рассылки всем пользователям с поддержкой фото и файлов"""
    users = load_users()
    successful = 0
    failed = 0
    
    for user in users:
        try:
            # Если есть документ - отправляем документ
            if document_path and os.path.exists(document_path):
                with open(document_path, "rb") as doc:
                    await bot.send_document(
                        chat_id=user['id'],
                        document=doc,
                        caption=message_text,
                        parse_mode="HTML"
                    )
            
            # Если есть фото - отправляем фото
            elif photo_path and os.path.exists(photo_path):
                with open(photo_path, "rb") as photo:
                    await bot.send_photo(
                        chat_id=user['id'],
                        photo=photo,
                        caption=message_text,
                        parse_mode="HTML"
                    )
            
            # Если нет файлов - отправляем просто текст
            else:
                await bot.send_message(
                    chat_id=user['id'],
                    text=message_text,
                    parse_mode="HTML"
                )
            
            successful += 1
            await asyncio.sleep(0.1)
            
        except Exception as e:
            logger.error(f"Ошибка отправки пользователю {user['id']}: {e}")
            failed += 1
            continue
    
    return successful, failed

@dp.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message):
    """Команда для рассылки (только для админа)"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Эта команда только для администратора")
        return
    
    if len(message.text.split()) < 2:
        await message.answer("❌ Формат: /broadcast текст сообщения")
        return
    
    broadcast_text = message.text.split(maxsplit=1)[1]
    users_count = len(load_users())
    
    await message.answer(f"📤 Начинаю рассылку для {users_count} пользователей...")
    
    successful, failed = await broadcast_message(broadcast_text)
    
    await message.answer(
        f"✅ Рассылка завершена!\n"
        f"✔️ Успешно: {successful}\n"
        f"❌ Не удалось: {failed}"
    )

@dp.message(Command("broadcast_photo"))
async def cmd_broadcast_photo(message: types.Message):
    """Рассылка с фото (только для админа)"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Эта команда только для администратора")
        return
    
    # Проверяем, есть ли фото и текст
    if not message.reply_to_message or not message.reply_to_message.photo:
        await message.answer(
            "❌ Формат команды:\n"
            "1. Отправьте фото с подписью\n"
            "2. Ответьте на фото командой /broadcast_photo"
        )
        return
    
    # Скачиваем фото
    photo = message.reply_to_message.photo[-1]
    photo_file = await bot.get_file(photo.file_id)
    photo_path = f"broadcast_photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    
    await bot.download_file(photo_file.file_path, photo_path)
    
    # Текст из подписи к фото или из сообщения
    caption = message.reply_to_message.caption or "📸"
    users_count = len(load_users())
    
    await message.answer(f"📸 Начинаю рассылку фото для {users_count} пользователей...")
    
    successful, failed = await broadcast_message(caption, photo_path=photo_path)
    
    # Удаляем временный файл
    if os.path.exists(photo_path):
        os.remove(photo_path)
    
    await message.answer(
        f"✅ Рассылка с фото завершена!\n"
        f"✔️ Успешно: {successful}\n"
        f"❌ Не удалось: {failed}"
    )

@dp.message(Command("broadcast_file"))
async def cmd_broadcast_file(message: types.Message):
    """Рассылка с файлом (только для админа)"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Эта команда только для администратора")
        return
    
    if not message.reply_to_message or not message.reply_to_message.document:
        await message.answer(
            "❌ Формат команды:\n"
            "1. Отправьте файл с подписью\n"
            "2. Ответьте на файл командой /broadcast_file"
        )
        return
    
    # Скачиваем документ
    document = message.reply_to_message.document
    document_file = await bot.get_file(document.file_id)
    document_path = f"broadcast_{document.file_name}"
    
    await bot.download_file(document_file.file_path, document_path)
    
    caption = message.reply_to_message.caption or "📎"
    users_count = len(load_users())
    
    await message.answer(f"📎 Начинаю рассылку файла для {users_count} пользователей...")
    
    successful, failed = await broadcast_message(caption, document_path=document_path)
    
    # Удаляем временный файл
    if os.path.exists(document_path):
        os.remove(document_path)
    
    await message.answer(
        f"✅ Рассылка с файлом завершена!\n"
        f"✔️ Успешно: {successful}\n"
        f"❌ Не удалось: {failed}"
    )

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Статистика пользователей"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Эта команда только для администратора")
        return
    
    users = load_users()
    await message.answer(
        f"📊 Статистика бота:\n"
        f"👥 Всего пользователей: {len(users)}\n"
        f"📅 Последние 7 дней: {len([u for u in users if datetime.fromisoformat(u['joined_date']) > datetime.now() - timedelta(days=7)])}\n"
        f"🆕 Сегодня: {len([u for u in users if datetime.fromisoformat(u['joined_date']).date() == datetime.now().date()])}"
    )

@dp.message(Command("help_admin"))
async def cmd_help_admin(message: types.Message):
    """Помощь по админ-командам"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Эта команда только для администратора")
        return
    
    help_text = """
🤖 <b>Админ-команды:</b>

📊 <b>/stats</b> - Статистика пользователей
📤 <b>/broadcast текст</b> - Текстовая рассылка
📸 <b>/broadcast_photo</b> - Рассылка с фото (ответьте на фото)
📎 <b>/broadcast_file</b> - Рассылка с файлом (ответьте на файл)
🆘 <b>/help_admin</b> - Эта справка

<b>Как делать рассылку с фото:</b>
1. Отправьте фото с подписью
2. Ответьте на фото командой /broadcast_photo

<b>Как делать рассылку с файлом:</b>
1. Отправьте файл с подписью
2. Ответьте на файл командой /broadcast_file
"""
    await message.answer(help_text, parse_mode="HTML")

# ------------------ ОСНОВНЫЕ ОБРАБОТЧИКИ ------------------
@dp.message(F.text.in_(SPECIALIZATIONS.keys()))
async def handle_doctor_choice(message: types.Message, state: FSMContext):
    logger.info(f"Выбор специалиста: {message.text}")
    spec_name = message.text
    spec_slug = SPECIALIZATIONS[spec_name]
    
    current_state = await state.get_state()
    if current_state == Form.waiting_for_specialist_choice:
        user_data = await state.get_data()
        recommended_keyboard = user_data.get('recommended_keyboard')
        await send_doctors_list(message, spec_slug, spec_name, keyboard_to_keep=recommended_keyboard)
    else:
        await state.clear()
        await send_doctors_list(message, spec_slug, spec_name, keyboard_to_keep=get_back_to_menu_keyboard())

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    
    # Сохраняем пользователя
    save_user(
        user_id=message.from_user.id,
        username=message.from_user.username or "",
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name or ""
    )
    
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

@dp.message(F.text == "Главное меню")
async def handle_main_menu(message: types.Message, state: FSMContext):
    await cmd_start(message, state)

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
    symptoms = message.text.strip()
    if not symptoms:
        await message.answer("Пожалуйста, опишите ваши симптомы.")
        return
        
    await message.answer("🔍 Анализирую симптомы...")
    yandex_response = await ask_yandex_gpt(symptoms)
    log_interaction(message.from_user, symptoms, yandex_response)

    if yandex_response.startswith("Ошибка"):
        await message.answer(yandex_response, reply_markup=get_back_to_menu_keyboard())
        await state.clear()
        return

    diagnosis = "неопределенное состояние"
    specialists = ["Терапевт"]
    
    try:
        if "Диагноз:" in yandex_response and "Специалисты:" in yandex_response:
            parts = yandex_response.split("Специалисты:")
            if len(parts) >= 2:
                diagnosis_part = parts[0].replace("Диагноз:", "").strip()
                specialists_part = parts[1].strip()
                
                diagnosis = diagnosis_part.split(".")[0] if diagnosis_part else "неопределенное состояние"
                
                specialists = []
                for spec in SPECIALIZATIONS.keys():
                    if spec.lower() in specialists_part.lower():
                        specialists.append(spec)
                
                if not specialists:
                    specialists = ["Терапевт"]
        else:
            for spec in SPECIALIZATIONS.keys():
                if spec.lower() in yandex_response.lower():
                    specialists.append(spec)
            
            if len(specialists) > 2:
                specialists = specialists[:2]
                
    except Exception as e:
        logger.error(f"Ошибка парсинга ответа YandexGPT: {e}")
        specialists = ["Терапевт"]

    recommended_kb = ReplyKeyboardBuilder()
    for spec_name in specialists:
        recommended_kb.add(KeyboardButton(text=spec_name))
    recommended_kb.add(KeyboardButton(text="Главное меню"))
    recommended_kb.adjust(2)

    await state.update_data(recommended_keyboard=recommended_kb.as_markup(resize_keyboard=True))
    await message.answer(
        f"<b>Возможный диагноз:</b> {diagnosis}\n\n"
        f"<b>Рекомендую обратиться к:</b> {', '.join(specialists)}\n\n"
        f"Нажмите на кнопку, чтобы увидеть список врачей.",
        parse_mode="HTML",
        reply_markup=recommended_kb.as_markup(resize_keyboard=True)
    )
    await state.set_state(Form.waiting_for_specialist_choice)

# Обработчик любого другого текста
@dp.message()
async def handle_unknown_message(message: types.Message):
    await message.answer("Пожалуйста, используйте кнопки меню ниже, для навигации.", reply_markup=get_start_keyboard())

async def send_doctors_list(message, spec_slug, spec_name, keyboard_to_keep=None):
    doctors = await get_cached_doctors(spec_slug)
    from_cache = True
    
    if not doctors:
        from_cache = False
        doctors = await scrape_doctors(spec_slug, message.chat.id)

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

    await message.answer(f"⭐ <b>Врачи {spec_name}</b>", parse_mode="HTML")

    for idx, doc in enumerate(doctors, 1):
        if doc.get('phone_clean'):
            phone_text = f'<a href="tel:{doc["phone_clean"]}">{doc["phone"]}</a>'
        else:
            phone_text = doc['phone']

        keyboard = None
        if doc.get('link'):
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="📋 Открыть карточку врача", 
                    web_app=types.WebAppInfo(url=doc['link'])
                )]
            ])

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
                await bot.send_photo(
                    message.chat.id, 
                    photo=doc['photo'], 
                    caption=caption, 
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
            else:
                await bot.send_message(
                    message.chat.id, 
                    text=caption, 
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
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
            await bot.send_message(message.chat.id, text=plain_text, reply_markup=keyboard)

    if keyboard_to_keep:
        await message.answer("✅ Готово! Нажмите на кнопку под каждым врачом для просмотра подробной информации.", reply_markup=keyboard_to_keep)
    else:
        await message.answer("✅ Готово! Нажмите на кнопку под каждым врачом для просмотра подробной информации.", reply_markup=get_back_to_menu_keyboard())

# ------------------ ЗАПУСК ------------------
async def main():
    logger.info("🚀 Бот запущен...")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
