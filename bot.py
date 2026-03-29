import re
from datetime import datetime, timedelta
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
import requests
import time
import json

# ========== НАСТРОЙКИ ==========
VK_TOKEN = "vk1.a.saqWO0JbCpERiTwMPuTDi1VFZdObaNX2eOIHim12O-TH7vN-ce_uGYRYrJvEuYI5XqoOHztw3aq5FCBK9pfVnET-yPPPbbnLtX32jHJ9LO-je1hBuFrvp-Ry9BSnDR5O2MjRE7--XKhOv3LQ9l6_ZufZXVksjoqXHdsvPxXsjPxLuN-VNLzSi_hsHtLEhJZkpYgCtwVAlATk2m3s3C5QSQ"
VK_GROUP_ID = 237047714
SPREADSHEET_ID = "1_57qA5vsVDJevrscNWKPt4q8Hp0XdwdKUbyUlnooKMU"

GID_ARCHIVE = "1821608543"
GID_SCHEDULE = "0"

ADMIN_PASSWORD = "vladsexmahina"
# =================================

EXAM_LINKS = {
    "theory": {
        "url": "https://yandex.ru/maps/10747/podolsk/?ll=37.554071%2C55.408501&mode=whatshere&whatshere%5Bpoint%5D=37.554118%2C55.408510&whatshere%5Bzoom%5D=19.8&z=11.74",
        "description": "📍 *Теоретическая часть экзамена*\n\n🗺️ *Адрес:* г. Подольск, ул. Правды, 32Б (МРЭО)\n⏰ *Время явки:* 8:45\n🚪 *Место встречи:* Ступеньки при входе в МРЭО"
    },
    "practice": {
        "url": "https://yandex.ru/maps/10747/podolsk/?l=sat&ll=37.556634%2C55.410682&mode=whatshere&whatshere%5Bpoint%5D=37.556422%2C55.410930&whatshere%5Bzoom%5D=19&z=19",
        "description": "📍 *Практическая часть экзамена*\n\n🗺️ *Адрес:* г. Подольск, площадка для практического экзамена\n⏰ *Время явки:* 9:00\n\nℹ️ *Важно:*\n• Если вы идете на экзамен первый раз: после успешной сдачи теории вы сразу направляетесь на эту площадку\n• Если вы идете на экзамен повторно (теория сдана, практика нет): нужно явиться на площадку в 9:00"
    }
}

TIME_MAP = {
    "0.4375": "17:30", "0.5": "18:00", "0.5625": "18:30", "0.625": "19:00", "0.6875": "19:30",
    "0.375": "16:00", "0.3125": "15:30", "0.25": "15:00", "0.1875": "14:30", "0.125": "14:00",
    "0.0625": "13:30", "0.0": "13:00",
    "10:30:00": "10:30", "12:00:00": "12:00", "13:30:00": "13:30", "15:00:00": "15:00", "16:30:00": "16:30",
    "18:00:00": "18:00", "19:30:00": "19:30", "21:00:00": "21:00", "22:30:00": "22:30"
}

print("🚀 Запуск бота...")
print(f"ID таблицы: {SPREADSHEET_ID}")

cached_archive = None
cached_schedule = None
last_update_time = None

user_data = {}
admin_sessions = {}  # user_id -> {"awaiting_password": True, "authorized": True, "awaiting_date": False, "awaiting_student": False}

def clean_number(value):
    if not value:
        return 0
    s = str(value)
    s = s.replace('\xa0', '').replace(' ', '').replace(' ', '')
    cleaned = re.sub(r'[^\d\-\.]', '', s)
    if cleaned == "" or cleaned == "-":
        return 0
    try:
        return float(cleaned)
    except:
        return 0

def parse_time_range(time_str, date_obj):
    lessons = []
    if not time_str or not time_str.strip():
        return lessons
    if '-' in time_str:
        parts = time_str.split('-')
        if len(parts) == 2:
            time1 = parts[0].strip()
            time2 = parts[1].strip()
            lesson_time1 = TIME_MAP.get(time1, time1)
            time_match1 = re.search(r'(\d{1,2}):(\d{2})', lesson_time1)
            if time_match1:
                hour1 = int(time_match1.group(1))
                minute1 = int(time_match1.group(2))
                lesson_date1 = date_obj.replace(hour=hour1, minute=minute1)
                lessons.append(lesson_date1)
            lesson_time2 = TIME_MAP.get(time2, time2)
            time_match2 = re.search(r'(\d{1,2}):(\d{2})', lesson_time2)
            if time_match2:
                hour2 = int(time_match2.group(1))
                minute2 = int(time_match2.group(2))
                lesson_date2 = date_obj.replace(hour=hour2, minute=minute2)
                lessons.append(lesson_date2)
    else:
        lesson_time = TIME_MAP.get(time_str, time_str)
        time_match = re.search(r'(\d{1,2}):(\d{2})', lesson_time)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2))
            lesson_date = date_obj.replace(hour=hour, minute=minute)
            lessons.append(lesson_date)
    return lessons

def get_sheet_data(gid, force_refresh=False):
    global cached_archive, cached_schedule, last_update_time
    
    if not force_refresh:
        if gid == GID_ARCHIVE and cached_archive is not None:
            return cached_archive
        if gid == GID_SCHEDULE and cached_schedule is not None:
            return cached_schedule
    
    try:
        url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid={gid}"
        print(f"  🔄 Загружаем gid={gid}...")
        response = requests.get(url, timeout=30)
        if response.status_code != 200:
            print(f"  ❌ Ошибка: {response.status_code}")
            return None

        try:
            content = response.content.decode('utf-8')
        except:
            try:
                content = response.content.decode('cp1251')
            except:
                content = response.text
        
        lines = content.strip().split('\n')
        
        all_data = []
        for line in lines:
            if not line.strip():
                continue
            cells = []
            current = ""
            in_quotes = False
            for char in line:
                if char == '"':
                    in_quotes = not in_quotes
                elif char == ',' and not in_quotes:
                    cells.append(current.strip())
                    current = ""
                else:
                    current += char
            cells.append(current.strip())
            cells = [c.strip('"') for c in cells]
            all_data.append(cells)
        
        print(f"  ✅ Загружено {len(all_data)} строк")
        
        if gid == GID_ARCHIVE:
            cached_archive = all_data
        else:
            cached_schedule = all_data
        last_update_time = datetime.now().strftime("%H:%M:%S")
        
        return all_data
            
    except Exception as e:
        print(f"  ❌ Ошибка: {e}")
        return None

def refresh_all_data():
    global cached_archive, cached_schedule, last_update_time
    print("\n🔄 Принудительное обновление данных из таблицы...")
    cached_archive = None
    cached_schedule = None
    archive = get_sheet_data(GID_ARCHIVE, force_refresh=True)
    schedule = get_sheet_data(GID_SCHEDULE, force_refresh=True)
    if archive and schedule:
        print(f"✅ Данные успешно обновлены! Время: {last_update_time}")
        return True
    else:
        print("❌ Ошибка при обновлении данных!")
        return False

def get_student_schedule_by_row(student_row_index, schedule_data):
    if not schedule_data or len(schedule_data) < 2:
        return None, [], False
    schedule_index = student_row_index - 1
    if schedule_index >= len(schedule_data):
        return None, [], False
    
    dates_row = schedule_data[0]
    student_row = schedule_data[schedule_index]
    
    total_lessons = student_row[5] if len(student_row) > 5 and student_row[5] else "0"
    psych_nark = student_row[6] if len(student_row) > 6 and student_row[6] else "нет"
    state_fee = student_row[7] if len(student_row) > 7 and student_row[7] else "нет"
    
    exam1_value = student_row[8] if len(student_row) > 8 and student_row[8] else ""
    exam2_value = student_row[9] if len(student_row) > 9 and student_row[9] else ""
    exam3_value = student_row[10] if len(student_row) > 10 and student_row[10] else ""
    
    exam_date1 = dates_row[8] if len(dates_row) > 8 else ""
    exam_date2 = dates_row[9] if len(dates_row) > 9 else ""
    exam_date3 = dates_row[10] if len(dates_row) > 10 else ""
    
    def extract_date_from_header(header):
        match = re.search(r'\((\d{1,2})\.(\d{1,2})\.(\d{4})\)', header)
        if match:
            return f"{match.group(1)}.{match.group(2)}.{match.group(3)}"
        return None
    
    exam_dates = []
    has_upcoming_exam = False
    
    exam_values = [exam1_value, exam2_value, exam3_value]
    exam_headers = [exam_date1, exam_date2, exam_date3]
    
    for val, header in zip(exam_values, exam_headers):
        if val and val.strip():
            if "идёт" in val.lower() or "идет" in val.lower():
                has_upcoming_exam = True
            date = extract_date_from_header(header)
            if date:
                exam_dates.append(f"Экзамен {date}: {val}")
            else:
                exam_dates.append(f"Экзамен: {val}")
    
    if not exam_dates:
        exam_dates = ["Экзамен не назначен"]
    
    lessons = []
    now = datetime.now()
    current_year = now.year
    
    for col in range(11, min(len(dates_row), len(student_row))):
        date_str = str(dates_row[col]).strip() if col < len(dates_row) else ""
        time_value = str(student_row[col]).strip() if col < len(student_row) else ""
        if not time_value or time_value == "":
            continue
        date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', date_str)
        if not date_match:
            date_match = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', date_str)
        if not date_match:
            continue
        try:
            if date_match.group(1).isdigit() and len(date_match.group(1)) == 4:
                year = int(date_match.group(1))
                month = int(date_match.group(2))
                day = int(date_match.group(3))
            else:
                day = int(date_match.group(1))
                month = int(date_match.group(2))
                year = int(date_match.group(3))
            lesson_date_base = datetime(year, month, day)
            time_lessons = parse_time_range(time_value, lesson_date_base)
            for lesson_date in time_lessons:
                is_past = lesson_date < now
                lessons.append({
                    'date': lesson_date,
                    'date_str': lesson_date.strftime('%d.%m.%Y'),
                    'time': lesson_date.strftime('%H:%M'),
                    'is_past': is_past
                })
        except Exception as e:
            continue
    
    lessons.sort(key=lambda x: x['date'])
    
    info = {
        'total_lessons': total_lessons,
        'psych_nark': psych_nark,
        'state_fee': state_fee,
        'exam_dates': exam_dates,
        'has_upcoming_exam': has_upcoming_exam
    }
    return info, lessons, has_upcoming_exam

def get_students_by_date(all_data, schedule_data, target_date):
    result = []
    if not schedule_data or len(schedule_data) < 2:
        return result
    
    dates_row = schedule_data[0]
    target_col = None
    for col in range(11, min(len(dates_row), 50)):
        date_str = str(dates_row[col]).strip()
        date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', date_str)
        if date_match:
            lesson_date = datetime(int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3)))
            if lesson_date.date() == target_date.date():
                target_col = col
                break
        else:
            date_match2 = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', date_str)
            if date_match2:
                lesson_date = datetime(int(date_match2.group(3)), int(date_match2.group(2)), int(date_match2.group(1)))
                if lesson_date.date() == target_date.date():
                    target_col = col
                    break
    
    if target_col is None:
        return result
    
    for idx, row in enumerate(schedule_data[1:], start=2):
        if len(row) > target_col and row[target_col] and row[target_col].strip():
            time_val = row[target_col].strip()
            student_fio = row[0].strip() if len(row) > 0 else ""
            for archive_row in all_data[1:]:
                if len(archive_row) > 0 and archive_row[0]:
                    archive_fio = archive_row[0].strip()
                    if student_fio and (student_fio in archive_fio or archive_fio in student_fio):
                        result.append({
                            'fio': archive_row[0],
                            'phone': archive_row[1] if len(archive_row) > 1 else "не указан",
                            'time': time_val
                        })
                        break
    return result

def format_welcome_message():
    return """🎓 *Добро пожаловать в бот автошколы Agoshkov Avto!*

🔍 *Введите ваше ФИО* (как в договоре)

_Пример: Петров Александр Сергеевич_

👑 *Администраторам:* введите /admin для входа в админ-панель"""

def format_student_info(archive_row, schedule_info, lessons):
    full_fio = archive_row[0]
    phone = archive_row[1] if len(archive_row) > 1 else "не указан"
    branch = archive_row[2] if len(archive_row) > 2 else "не указан"
    study_format = archive_row[3] if len(archive_row) > 3 else "не указан"
    
    total_amount_raw = archive_row[4] if len(archive_row) > 4 else "0"
    paid_raw = archive_row[5] if len(archive_row) > 5 else "0"
    
    total_amount = clean_number(total_amount_raw)
    paid = clean_number(paid_raw)
    debt = total_amount - paid
    
    fio_clean = full_fio.strip()

    response = f"👋 *Здравствуйте, {fio_clean}!*\n\n"

    response += "📞 *Контактная информация:*\n"
    response += f"├ Телефон: {phone}\n"
    response += f"├ Филиал: {branch}\n"
    response += f"└ Формат: {study_format}\n\n"

    response += "💰 *Финансовая информация:*\n"
    response += f"├ Сумма обучения: {total_amount:.0f} ₽\n"
    response += f"├ Оплачено: {paid:.0f} ₽\n"
    
    if debt > 0:
        response += f"└ Долг: {debt:.0f} ₽\n\n"
    else:
        response += f"└ Долг: 0 ₽ ✅ (оплачено полностью)\n\n"

    if schedule_info:
        response += "📚 *Программа обучения:*\n"
        response += f"├ Всего занятий: {schedule_info['total_lessons']}\n"
        response += f"├ Псих. нарколог: {schedule_info['psych_nark']}\n"
        response += f"├ Госпошлина: {schedule_info['state_fee']}\n"
        
        if 'exam_dates' in schedule_info and schedule_info['exam_dates']:
            for exam in schedule_info['exam_dates']:
                response += f"├ {exam}\n"
        else:
            response += "├ Экзамен не назначен\n"
        response += "\n"

    if lessons:
        now = datetime.now()
        completed = 0
        future_lessons = []

        response += "📅 *Расписание занятий:*\n"

        for lesson in lessons:
            if lesson['is_past']:
                marker = "✅"
                completed += 1
            else:
                marker = "📌"
                future_lessons.append(lesson)
            
            response += f"{marker} {lesson['date_str']} — {lesson['time']}"
            if lesson['is_past']:
                response += " *(пройдено)*"
            response += "\n"

        remaining = len(lessons) - completed
        response += f"\n📊 *Статистика:*\n"
        response += f"├ Проведено: {completed}\n"
        response += f"├ Осталось: {remaining}\n"
        response += f"└ Всего запланировано: {len(lessons)}\n"

        if future_lessons:
            next_lesson = future_lessons[0]
            response += f"\n⭐ *Ближайшее занятие:* {next_lesson['date_str']} в {next_lesson['time']}"
    else:
        response += "📅 *Расписание занятий:*\n"
        response += "└ Занятия пока не добавлены в расписание"

    return response

def get_full_keyboard(has_exam=False, is_admin=False):
    buttons = [
        [{"action": {"type": "text", "label": "📅 Расписание"}, "color": "primary"}],
        [{"action": {"type": "text", "label": "💰 Финансы"}, "color": "positive"}],
        [{"action": {"type": "text", "label": "📊 Программа"}, "color": "secondary"}],
        [{"action": {"type": "text", "label": "📋 Вся информация"}, "color": "primary"}]
    ]
    if has_exam:
        buttons.append([{"action": {"type": "text", "label": "📍 Место экзамена"}, "color": "secondary"}])
    buttons.append([{"action": {"type": "text", "label": "🔄 Обновить данные"}, "color": "secondary"}])
    buttons.append([{"action": {"type": "text", "label": "❓ Помощь"}, "color": "secondary"}])
    if is_admin:
        buttons.append([{"action": {"type": "text", "label": "🔓 Сменить ученика"}, "color": "secondary"}])
    return {"one_time": False, "buttons": buttons}

def get_admin_keyboard():
    return {
        "one_time": False,
        "buttons": [
            [{"action": {"type": "text", "label": "📅 Занятия по датам"}, "color": "primary"}],
            [{"action": {"type": "text", "label": "👤 Сменить ученика"}, "color": "secondary"}],
            [{"action": {"type": "text", "label": "🚪 Выйти из админки"}, "color": "secondary"}]
        ]
    }

def get_simple_keyboard():
    return {
        "one_time": False,
        "buttons": [
            [{"action": {"type": "text", "label": "🔄 Обновить данные"}, "color": "secondary"}],
            [{"action": {"type": "text", "label": "❓ Помощь"}, "color": "secondary"}],
            [{"action": {"type": "text", "label": "👑 Админ-панель"}, "color": "secondary"}]
        ]
    }

def get_exam_info():
    return f"""📍 *Информация о сдаче экзаменов*

{EXAM_LINKS['theory']['description']}
🔗 [Открыть карту]({EXAM_LINKS['theory']['url']})

{EXAM_LINKS['practice']['description']}
🔗 [Открыть карту]({EXAM_LINKS['practice']['url']})

💡 *Совет:* Сохраните эти адреса в заметки, чтобы не потерять!"""

def send_message(vk, user_id, message, with_keyboard=False, is_authorized=False, has_exam=False, is_admin=False, admin_mode=False):
    try:
        params = {"user_id": user_id, "message": message, "random_id": int(time.time() * 1000)}
        if with_keyboard:
            if admin_mode:
                params["keyboard"] = json.dumps(get_admin_keyboard())
            elif is_authorized:
                params["keyboard"] = json.dumps(get_full_keyboard(has_exam, is_admin))
            else:
                params["keyboard"] = json.dumps(get_simple_keyboard())
        vk.messages.send(**params)
        return True
    except Exception as e:
        print(f"Ошибка: {e}")
        return False

# ====================== ЗАПУСК ======================
print("\n📡 Подключение к VK...")
try:
    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()
    longpoll = VkBotLongPoll(vk_session, VK_GROUP_ID)
    print("✅ Подключение к VK успешно!")
except Exception as e:
    print(f"❌ Ошибка: {e}")
    exit()

print("\n📥 Загрузка данных...")
archive = get_sheet_data(GID_ARCHIVE)
schedule = get_sheet_data(GID_SCHEDULE)

if not archive:
    print("❌ Не удалось загрузить Архив!")
    exit()
if not schedule:
    print("❌ Не удалось загрузить Расписание!")
    exit()

print(f"\n✅ Архив: {len(archive)} строк")
print(f"✅ Расписание: {len(schedule)} строк")
print(f"📅 Данные обновлены: {last_update_time}")

print("\n" + "="*60)
print("🤖 БОТ ЗАПУЩЕН!")
print("📱 Напишите ФИО ученика для авторизации")
print("👑 Для админ-панели: /admin")
print("="*60)

while True:
    try:
        for event in longpoll.listen():
            if event.type == VkBotEventType.MESSAGE_NEW and event.object.message:
                user_id = event.object.message['from_id']
                text = event.object.message['text'].strip()
                print(f"\n📩 Сообщение: '{text}'")

                # ========== АДМИН АВТОРИЗАЦИЯ ==========
                if text.lower() == "/admin":
                    admin_sessions[user_id] = {"awaiting_password": True}
                    send_message(vk, user_id, "🔐 *Вход в админ-панель*\n\nВведите пароль:", with_keyboard=False)
                    continue
                
                # Обработка ввода пароля
                if user_id in admin_sessions and admin_sessions[user_id].get("awaiting_password"):
                    if text == ADMIN_PASSWORD:
                        admin_sessions[user_id] = {"authorized": True, "awaiting_date": False, "awaiting_student": False}
                        user_data[user_id] = {"is_admin": True}
                        send_message(vk, user_id, "✅ *Доступ разрешен!*\n\nДобро пожаловать в админ-панель.", with_keyboard=True, admin_mode=True)
                    else:
                        del admin_sessions[user_id]
                        send_message(vk, user_id, "❌ *Неверный пароль!*\n\nДоступ запрещен.", with_keyboard=False)
                    continue
                
                # ========== АДМИН-ПАНЕЛЬ (авторизован) ==========
                if user_id in admin_sessions and admin_sessions[user_id].get("authorized"):
                    # Кнопка "Занятия по датам"
                    if text == "📅 Занятия по датам":
                        admin_sessions[user_id]["awaiting_date"] = True
                        send_message(vk, user_id, "📅 *Выберите дату*\n\nВведите дату в формате:\n28.03.2026\n\nИли напишите 'сегодня' для текущей даты", with_keyboard=False, admin_mode=True)
                        continue
                    
                    # Кнопка "Сменить ученика"
                    elif text == "👤 Сменить ученика":
                        admin_sessions[user_id]["awaiting_student"] = True
                        send_message(vk, user_id, "👤 *Режим смены ученика*\n\nВведите ФИО ученика, под которым хотите войти:", with_keyboard=False, admin_mode=True)
                        continue
                    
                    # Кнопка "Выйти из админки"
                    elif text == "🚪 Выйти из админки":
                        del admin_sessions[user_id]
                        if user_id in user_data:
                            del user_data[user_id]
                        send_message(vk, user_id, "👋 Вы вышли из админ-панели.\n\n" + format_welcome_message(), with_keyboard=True, is_authorized=False)
                        continue
                    
                    # Обработка ввода даты
                    if admin_sessions[user_id].get("awaiting_date"):
                        current_archive = cached_archive if cached_archive else archive
                        current_schedule = cached_schedule if cached_schedule else schedule
                        
                        if text.lower() == "сегодня":
                            now = datetime.now()
                            msk_time = now - timedelta(hours=4)
                            target_date = msk_time
                        else:
                            try:
                                day, month, year = text.split('.')
                                target_date = datetime(int(year), int(month), int(day))
                            except:
                                send_message(vk, user_id, "❌ *Неверный формат даты!*\n\nИспользуйте формат: 28.03.2026\nИли напишите 'сегодня'", with_keyboard=False, admin_mode=True)
                                continue
                        
                        students = get_students_by_date(current_archive, current_schedule, target_date)
                        date_str = target_date.strftime("%d.%m.%Y")
                        
                        if students:
                            response = f"📋 *Ученики с занятиями на {date_str}:*\n\n"
                            for s in students:
                                response += f"👤 {s['fio']}\n"
                                response += f"📞 {s['phone']}\n"
                                response += f"⏰ Время: {s['time']}\n\n"
                            if len(response) > 4000:
                                response = response[:4000] + "\n\n... и еще ученики"
                        else:
                            response = f"✅ *На {date_str} занятий нет*"
                        
                        admin_sessions[user_id]["awaiting_date"] = False
                        send_message(vk, user_id, response, with_keyboard=True, admin_mode=True)
                        continue
                    
                    # Обработка смены ученика
                    if admin_sessions[user_id].get("awaiting_student"):
                        current_archive = cached_archive if cached_archive else archive
                        
                        found = None
                        found_row_index = -1
                        search_query = text.strip().lower()
                        
                        for idx, row in enumerate(current_archive[1:], start=2):
                            if not row or len(row) == 0 or not row[0]:
                                continue
                            cell = str(row[0]).strip().lower()
                            if search_query == cell or search_query in cell:
                                found = row
                                found_row_index = idx
                                break
                        
                        if found:
                            user_data[user_id] = {"fio": found[0], "row_index": found_row_index, "is_admin": True}
                            admin_sessions[user_id]["awaiting_student"] = False
                            current_schedule = cached_schedule if cached_schedule else schedule
                            _, _, has_exam = get_student_schedule_by_row(found_row_index, current_schedule)
                            fio_clean = found[0].strip()
                            response = f"✅ *Успешно!*\n\nВы вошли как: {fio_clean}\n\nТеперь вы можете использовать кнопки для просмотра информации этого ученика."
                            send_message(vk, user_id, response, with_keyboard=True, admin_mode=True)
                        else:
                            send_message(vk, user_id, f"❌ Ученик '{text}' не найден. Попробуйте снова:", with_keyboard=False, admin_mode=True)
                        continue
                    
                    # Если админ нажал на обычную кнопку (расписание, финансы и т.д.) - пропускаем, они будут обработаны ниже
                    if text in ["📅 Расписание", "💰 Финансы", "📊 Программа", "📋 Вся информация", "📍 Место экзамена", "🔄 Обновить данные", "❓ Помощь"]:
                        pass
                    else:
                        continue
                
                # ========== ОБЫЧНЫЕ КОМАНДЫ ==========
                if text.lower() in ["начать", "start", "привет"]:
                    send_message(vk, user_id, format_welcome_message(), with_keyboard=True, is_authorized=False)
                    continue

                if text == "❓ Помощь":
                    help_text = f"""🔍 *Как пользоваться ботом:*

1️⃣ Введите ваше ФИО (как в договоре)
   Пример: *Петров Александр Сергеевич*

2️⃣ После авторизации появятся кнопки:
   • 📅 Расписание — только даты занятий
   • 💰 Финансы — только финансы
   • 📊 Программа — только программу
   • 📋 Вся информация — полный отчет
   • 📍 Место экзамена — адреса сдачи экзаменов (появляется, если у вас назначен экзамен)
   • 🔄 Обновить данные — загружает свежие данные из таблицы
   • ❓ Помощь — это сообщение

👑 *Администраторам:* введите /admin для входа в админ-панель

💡 *Важно:* Кнопка "🔄 Обновить данные" всегда доступна. 
Сотрудник часто изменяет данные в таблице, нажмите её, чтобы получить актуальную информацию!

📅 *Последнее обновление данных:* {last_update_time}"""
                    is_auth = user_id in user_data
                    has_exam = False
                    is_admin = user_data.get(user_id, {}).get("is_admin", False)
                    if is_auth and user_id in user_data and "row_index" in user_data[user_id]:
                        student_row = user_data[user_id]["row_index"]
                        current_schedule = cached_schedule if cached_schedule else schedule
                        _, _, has_exam = get_student_schedule_by_row(student_row, current_schedule)
                    send_message(vk, user_id, help_text, with_keyboard=True, is_authorized=is_auth, has_exam=has_exam, is_admin=is_admin)
                    continue

                if text == "🔄 Обновить данные":
                    send_message(vk, user_id, "🔄 Обновляю данные из таблицы...", with_keyboard=False)
                    if refresh_all_data():
                        archive = cached_archive
                        schedule = cached_schedule
                        is_auth = user_id in user_data
                        has_exam = False
                        is_admin = user_data.get(user_id, {}).get("is_admin", False)
                        if is_auth and user_id in user_data and "row_index" in user_data[user_id]:
                            student_row = user_data[user_id]["row_index"]
                            current_schedule = cached_schedule if cached_schedule else schedule
                            _, _, has_exam = get_student_schedule_by_row(student_row, current_schedule)
                        send_message(vk, user_id, f"✅ Данные успешно обновлены!\n\n📅 Время обновления: {last_update_time}", with_keyboard=True, is_authorized=is_auth, has_exam=has_exam, is_admin=is_admin)
                    else:
                        is_auth = user_id in user_data
                        is_admin = user_data.get(user_id, {}).get("is_admin", False)
                        send_message(vk, user_id, "❌ Ошибка при обновлении данных. Проверьте подключение к интернету.", with_keyboard=True, is_authorized=is_auth, is_admin=is_admin)
                    continue

                # ========== ОБРАБОТКА КНОПОК ДЛЯ АВТОРИЗОВАННЫХ ==========
                if user_id in user_data and "row_index" in user_data[user_id]:
                    print(f"🔍 Обработка кнопки: '{text}'")
                    student_fio = user_data[user_id]["fio"]
                    student_row = user_data[user_id]["row_index"]
                    is_admin = user_data[user_id].get("is_admin", False)
                    print(f"   Ученик: {student_fio[:40]}, строка: {student_row}")
                    
                    current_archive = cached_archive if cached_archive else archive
                    current_schedule = cached_schedule if cached_schedule else schedule
                    
                    found = None
                    for row in current_archive[1:]:
                        if len(row) > 0 and row[0] and student_fio in row[0]:
                            found = row
                            print(f"   ✅ Найдены данные ученика")
                            break
                    
                    if not found:
                        print(f"   ❌ Данные ученика не найдены!")
                        del user_data[user_id]
                        send_message(vk, user_id, "❌ Ваши данные не найдены. Пожалуйста, введите ФИО заново.", with_keyboard=False)
                        continue
                    
                    schedule_info, lessons, has_exam = get_student_schedule_by_row(student_row, current_schedule)
                    print(f"   has_exam={has_exam}, занятий={len(lessons)}")
                    
                    fio_clean = found[0].strip()
                    
                    if text == "📅 Расписание":
                        print("   ➤ Отправка расписания")
                        if lessons:
                            response = f"📅 *Расписание занятий для {fio_clean}*\n\n"
                            for lesson in lessons:
                                response += f"{lesson['date_str']} — {lesson['time']}\n"
                        else:
                            response = f"📅 *Расписание занятий для {fio_clean}*\n\nНет запланированных занятий"
                    
                    elif text == "💰 Финансы":
                        print("   ➤ Отправка финансов")
                        total = clean_number(found[4] if len(found) > 4 else "0")
                        paid = clean_number(found[5] if len(found) > 5 else "0")
                        debt = total - paid
                        response = f"💰 *Финансовая информация для {fio_clean}*\n\n"
                        response += f"Сумма обучения: {total:.0f} ₽\n"
                        response += f"Оплачено: {paid:.0f} ₽\n"
                        if debt > 0:
                            response += f"Долг: {debt:.0f} ₽"
                        else:
                            response += f"Долг: 0 ₽ ✅ (оплачено полностью)"
                    
                    elif text == "📊 Программа":
                        print("   ➤ Отправка программы")
                        if schedule_info:
                            response = f"📊 *Программа обучения для {fio_clean}*\n\n"
                            response += f"Всего занятий: {schedule_info['total_lessons']}\n"
                            response += f"Псих. нарколог: {schedule_info['psych_nark']}\n"
                            response += f"Госпошлина: {schedule_info['state_fee']}\n"
                            if 'exam_dates' in schedule_info:
                                for exam in schedule_info['exam_dates']:
                                    response += f"{exam}\n"
                        else:
                            response = f"📊 *Программа обучения*\n\nИнформация не найдена"
                    
                    elif text == "📋 Вся информация":
                        print("   ➤ Отправка всей информации")
                        response = format_student_info(found, schedule_info, lessons)
                    
                    elif text == "📍 Место экзамена":
                        print("   ➤ Отправка места экзамена")
                        response = get_exam_info()
                    
                    else:
                        print(f"   ❌ Неизвестная кнопка, игнорируем")
                        continue
                    
                    send_message(vk, user_id, response, with_keyboard=True, is_authorized=True, has_exam=has_exam, is_admin=is_admin)
                    continue

                # ========== АВТОРИЗАЦИЯ ПО ФИО ==========
                print(f"🔍 ПОИСК: '{text}'")
                current_archive = cached_archive if cached_archive else archive
                found = None
                found_row_index = -1
                search_query = text.strip().lower()
                
                for idx, row in enumerate(current_archive[1:], start=2):
                    if not row or len(row) == 0 or not row[0]:
                        continue
                    cell = str(row[0]).strip().lower()
                    if search_query == cell or search_query in cell:
                        found = row
                        found_row_index = idx
                        print(f"✅ НАЙДЕН! Строка {idx}: {row[0][:50]}")
                        break
                
                if found:
                    current_schedule = cached_schedule if cached_schedule else schedule
                    _, _, has_exam = get_student_schedule_by_row(found_row_index, current_schedule)
                    user_data[user_id] = {"fio": found[0], "row_index": found_row_index, "is_admin": False}
                    fio_clean = found[0].strip()
                    welcome = f"👋 *Здравствуйте, {fio_clean}!*\n\n"
                    welcome += "✅ Вы успешно авторизованы! Теперь вы можете использовать кнопки для получения информации:\n\n"
                    welcome += "📅 Расписание — только даты занятий\n"
                    welcome += "💰 Финансы — только финансы\n"
                    welcome += "📊 Программа — только программу\n"
                    welcome += "📋 Вся информация — полный отчет\n"
                    if has_exam:
                        welcome += "📍 Место экзамена — адреса сдачи экзаменов\n"
                    welcome += "🔄 Обновить данные — загрузить свежие данные из таблицы\n"
                    welcome += "❓ Помощь — это сообщение\n\n"
                    welcome += f"📅 *Данные обновлены:* {last_update_time}"
                    send_message(vk, user_id, welcome, with_keyboard=True, is_authorized=True, has_exam=has_exam, is_admin=False)
                    print(f"✅ Авторизован: {found[0][:50]}")
                else:
                    send_message(vk, user_id, "❌ *Ученик не найден*\n\n" + format_welcome_message(), with_keyboard=False)
                    print(f"❌ УЧЕНИК НЕ НАЙДЕН: '{text}'")

    except Exception as e:
        print(f"⚠️ Ошибка: {e}")
        time.sleep(5)