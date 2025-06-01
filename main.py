import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command
from aiogram.enums import ParseMode
from sqlalchemy import create_engine, Column, Integer, String, Date, ForeignKey, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from datetime import datetime, date, timedelta
from dotenv import load_dotenv
import os
import csv
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- Настройка окружения --- #
load_dotenv()
TOKEN = "7948057141:AAEgI_k8mtGdYMZA9wYXKT7jgdzvuOYaIAA"
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "1077073462").split(",")))

bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# --- Настройка БД --- #
Base = declarative_base()
engine = create_engine("sqlite:///events.db")
Session = sessionmaker(bind=engine)

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    tg_id = Column(Integer, unique=True)
    full_name = Column(String)
    registrations = relationship("Registration", back_populates="user")

class Event(Base):
    __tablename__ = 'events'
    id = Column(Integer, primary_key=True)
    title = Column(String)
    topic = Column(String)
    description = Column(String)
    date = Column(Date)
    registrations = relationship("Registration", back_populates="event")

class Registration(Base):
    __tablename__ = 'registrations'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    event_id = Column(Integer, ForeignKey('events.id'))
    registered_at = Column(DateTime, default=datetime.utcnow)
    user = relationship("User", back_populates="registrations")
    event = relationship("Event", back_populates="registrations")

Base.metadata.create_all(engine)

# --- Вспомогательные функции --- #
def is_admin(user_id):
    return user_id in ADMIN_IDS

def format_event_short(event):
    return (f"<b>{event.title}</b>\n"
            f"📅 {event.date.strftime('%d.%m.%Y')}\n"
            f"🏷️ Тема: {event.topic}")

def format_event_full(event):
    return (f"<b>{event.title}</b>\n"
            f"📅 Дата: {event.date.strftime('%d.%m.%Y')}\n"
            f"🏷️ Тема: {event.topic}\n"
            f"📝 Описание:\n{event.description}\n\n"
            f"🆔 ID мероприятия: <code>{event.id}</code>")

def format_registration(reg):
    return (f"• {reg.event.title} (ID: {reg.event.id})\n"
            f"  Дата: {reg.event.date.strftime('%d.%m.%Y')}\n"
            f"  Зарегистрирован: {reg.registered_at.strftime('%d.%m.%Y %H:%M')}")

# --- Клавиатуры --- #
def get_main_keyboard(is_admin=False):
    buttons = [
        [KeyboardButton(text="📅 Предстоящие мероприятия")],
        [KeyboardButton(text="🎫 Мои записи")],
        [KeyboardButton(text="❌ Отменить запись")],
        [KeyboardButton(text="ℹ️ Помощь")]
    ]
    if is_admin:
        buttons.insert(0, [KeyboardButton(text="🛠️ Админ-панель")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_admin_keyboard():
    buttons = [
        [KeyboardButton(text="➕ Создать мероприятие")],
        [KeyboardButton(text="📤 Экспорт записей")],
        [KeyboardButton(text="🗑️ Удалить мероприятие")],
        [KeyboardButton(text="👥 Участники")],
        [KeyboardButton(text="🔙 Главное меню")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_back_keyboard():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔙 Назад")]], resize_keyboard=True)

def get_event_list_keyboard(events):
    builder = InlineKeyboardBuilder()
    for event in events:
        builder.button(
            text=f"{event.title}",
            callback_data=f"event_select_{event.id}"
        )
    builder.adjust(1)
    return builder.as_markup()

def get_event_details_keyboard(event_id, is_registered=False):
    builder = InlineKeyboardBuilder()
    
    if not is_registered:
        builder.button(
            text="✅ Записаться", 
            callback_data=f"event_register_{event_id}"
        )
    
    builder.button(
        text="ℹ️ Подробнее" if not is_registered else "📝 Информация",
        callback_data=f"event_details_{event_id}"
    )
    
    builder.button(
        text="🔙 К списку мероприятий",
        callback_data="back_to_events"
    )
    builder.adjust(1)
    return builder.as_markup()

# --- Обработчики команд --- #
@dp.message(Command("start"))
async def start(message: types.Message):
    session = Session()
    if not session.query(User).filter_by(tg_id=message.from_user.id).first():
        user = User(tg_id=message.from_user.id, full_name=message.from_user.full_name)
        session.add(user)
        session.commit()
    session.close()
    
    text = ("👋 Добро пожаловать в систему управления мероприятиями!\n\n"
            "📌 Используйте кнопки ниже для навигации.\n"
            "📎 Для администраторов доступны дополнительные функции")
    
    await message.answer(text, reply_markup=get_main_keyboard(is_admin(message.from_user.id)), parse_mode=ParseMode.HTML)

@dp.message(Command("menu"))
async def show_menu(message: types.Message):
    await message.answer("📱 Главное меню:", reply_markup=get_main_keyboard(is_admin(message.from_user.id)))

@dp.message(Command("help"))
async def help_command(message: types.Message):
    text = ("<b>ℹ️ Справка по командам</b>\n\n"
            "Основные функции:\n"
            "• 📅 Предстоящие мероприятия - список доступных мероприятий\n"
            "• 🎫 Мои записи - ваши текущие регистрации\n"
            "• ❌ Отменить запись - отмена всех ваших регистраций\n\n"
            "Для администраторов:\n"
            "• 🛠️ Админ-панель - управление системой\n"
            "• ➕ Создать мероприятие - добавление нового мероприятия\n"
            "• 🗑️ Удалить мероприятие - удаление существующего\n"
            "• 👥 Участники - просмотр зарегистрированных\n"
            "• 📤 Экспорт записей - выгрузка данных в CSV\n\n"
            "Все функции доступны через интерактивные меню!")
    
    await message.answer(text, parse_mode=ParseMode.HTML)

# --- Обработчики кнопок --- #
@dp.message(F.text == "📅 Предстоящие мероприятия")
async def list_events(message: types.Message):
    session = Session()
    today = date.today()
    events = session.query(Event).filter(Event.date >= today).order_by(Event.date).all()
    
    if not events:
        await message.answer("📭 На данный момент нет доступных мероприятий.", reply_markup=get_main_keyboard(is_admin(message.from_user.id)))
        return
    
    text = "📅 <b>Предстоящие мероприятия:</b>\n\n"
    for idx, event in enumerate(events, 1):
        text += (f"{idx}. {format_event_short(event)}\n\n")
    
    await message.answer(
        text,
        reply_markup=get_event_list_keyboard(events),
        parse_mode=ParseMode.HTML
    )
    session.close()

@dp.message(F.text == "🎫 Мои записи")
async def my_events(message: types.Message):
    session = Session()
    user = session.query(User).filter_by(tg_id=message.from_user.id).first()
    regs = session.query(Registration).filter_by(user_id=user.id).all()
    
    if not regs:
        text = "📭 Вы пока не записаны ни на одно мероприятие."
        await message.answer(text, reply_markup=get_main_keyboard(is_admin(message.from_user.id)))
        return
    
    text = "🎫 <b>Ваши мероприятия:</b>\n\n"
    for reg in regs:
        text += format_registration(reg) + "\n\n"
    
    builder = InlineKeyboardBuilder()
    for reg in regs:
        builder.button(
            text=f"❌ Отменить {reg.event.title}",
            callback_data=f"cancel_{reg.id}"
        )
    builder.adjust(1)
    
    await message.answer(
        text,
        reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML
    )
    session.close()

@dp.message(F.text == "❌ Отменить запись")
async def cancel_all_registrations(message: types.Message):
    session = Session()
    user = session.query(User).filter_by(tg_id=message.from_user.id).first()
    regs = session.query(Registration).filter_by(user_id=user.id).all()
    
    if not regs:
        await message.answer("📭 У вас нет активных записей.", reply_markup=get_main_keyboard(is_admin(message.from_user.id)))
        return
    
    for reg in regs:
        session.delete(reg)
    session.commit()
    
    await message.answer("✅ Все ваши записи отменены.", reply_markup=get_main_keyboard(is_admin(message.from_user.id)))
    session.close()

@dp.message(F.text == "🛠️ Админ-панель")
async def admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещен!", reply_markup=get_main_keyboard(False))
        return
    
    text = "🛠️ <b>Административная панель</b>\n\nВыберите действие:"
    await message.answer(text, reply_markup=get_admin_keyboard(), parse_mode=ParseMode.HTML)

@dp.message(F.text == "➕ Создать мероприятие")
async def create_event_start(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещен!", reply_markup=get_main_keyboard(False))
        return
    
    text = ("✏️ <b>Создание нового мероприятия</b>\n\n"
            "Введите данные в формате:\n"
            "<code>Название;Тема;Описание;ГГГГ-ММ-ДД</code>\n\n"
            "Пример:\n"
            "<code>Встреча разработчиков;IT;Обсуждение новых технологий;2024-12-15</code>\n\n"
            "Для отмены нажмите кнопку '🔙 Назад'")
    
    await message.answer(text, reply_markup=get_back_keyboard(), parse_mode=ParseMode.HTML)

@dp.message(F.text == "📤 Экспорт записей")
async def export_event_users(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещен!", reply_markup=get_main_keyboard(False))
        return
    
    session = Session()
    events = session.query(Event).all()
    
    if not events:
        await message.answer("📭 Нет мероприятий для экспорта", reply_markup=get_admin_keyboard())
        return
    
    text = "📤 <b>Экспорт участников</b>\n\nВыберите мероприятие:"
    builder = InlineKeyboardBuilder()
    for event in events:
        builder.button(
            text=f"{event.title} ({event.date.strftime('%d.%m.%Y')})",
            callback_data=f"export_{event.id}"
        )
    builder.adjust(1)
    
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
    session.close()

@dp.message(F.text == "🗑️ Удалить мероприятие")
async def delete_event_start(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещен!", reply_markup=get_main_keyboard(False))
        return
    
    session = Session()
    events = session.query(Event).order_by(Event.date).all()
    
    if not events:
        await message.answer("📭 Нет мероприятий для удаления", reply_markup=get_admin_keyboard())
        return
    
    text = "🗑️ <b>Удаление мероприятия</b>\n\nВыберите мероприятие:"
    builder = InlineKeyboardBuilder()
    for event in events:
        builder.button(
            text=f"{event.title} ({event.date.strftime('%d.%m.%Y')})",
            callback_data=f"delete_{event.id}"
        )
    builder.adjust(1)
    
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
    session.close()

@dp.message(F.text == "👥 Участники")
async def show_users_start(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещен!", reply_markup=get_main_keyboard(False))
        return
    
    session = Session()
    events = session.query(Event).order_by(Event.date).all()
    
    if not events:
        await message.answer("📭 Нет мероприятий", reply_markup=get_admin_keyboard())
        return
    
    text = "👥 <b>Просмотр участников</b>\n\nВыберите мероприятие:"
    builder = InlineKeyboardBuilder()
    for event in events:
        builder.button(
            text=f"{event.title} ({len(event.registrations)})",
            callback_data=f"users_{event.id}"
        )
    builder.adjust(1)
    
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
    session.close()

@dp.message(F.text == "🔙 Назад")
async def back_handler(message: types.Message):
    if is_admin(message.from_user.id):
        await message.answer("🔙 Возврат в админ-панель", reply_markup=get_admin_keyboard())
    else:
        await message.answer("🔙 Возврат в главное меню", reply_markup=get_main_keyboard(False))

@dp.message(F.text == "🔙 Главное меню")
async def back_to_main_menu(message: types.Message):
    await message.answer("🏠 Возврат в главное меню", reply_markup=get_main_keyboard(is_admin(message.from_user.id)))

# --- Обработчики событий (новые для кнопки "Подробнее") --- #
@dp.callback_query(F.data.startswith("event_select_"))
async def event_select(callback: types.CallbackQuery):
    event_id = int(callback.data.split("_")[2])
    session = Session()
    event = session.query(Event).get(event_id)
    user = session.query(User).filter_by(tg_id=callback.from_user.id).first()
    
    if not event:
        await callback.answer("Мероприятие не найдено!")
        return
    
    # Проверяем, зарегистрирован ли пользователь
    is_registered = session.query(Registration).filter_by(
        user_id=user.id, 
        event_id=event_id
    ).first() is not None
    
    text = format_event_short(event)
    session.close()
    
    await callback.message.edit_text(
        text,
        reply_markup=get_event_details_keyboard(event_id, is_registered),
        parse_mode=ParseMode.HTML
    )

@dp.callback_query(F.data.startswith("event_details_"))
async def event_details(callback: types.CallbackQuery):
    event_id = int(callback.data.split("_")[2])
    session = Session()
    event = session.query(Event).get(event_id)
    user = session.query(User).filter_by(tg_id=callback.from_user.id).first()
    
    if not event:
        await callback.answer("Мероприятие не найдено!")
        return
    
    # Проверяем, зарегистрирован ли пользователь
    is_registered = session.query(Registration).filter_by(
        user_id=user.id, 
        event_id=event_id
    ).first() is not None
    
    text = format_event_full(event)
    session.close()
    
    await callback.message.edit_text(
        text,
        reply_markup=get_event_details_keyboard(event_id, is_registered),
        parse_mode=ParseMode.HTML
    )

@dp.callback_query(F.data.startswith("event_register_"))
async def register_callback(callback: types.CallbackQuery):
    event_id = int(callback.data.split("_")[2])
    session = Session()
    
    try:
        user = session.query(User).filter_by(tg_id=callback.from_user.id).first()
        event = session.query(Event).get(event_id)
        
        if not event:
            await callback.answer("Мероприятие не найдено!")
            return
        
        existing = session.query(Registration).filter_by(user_id=user.id, event_id=event_id).first()
        
        if existing:
            await callback.answer("⚠️ Вы уже записаны на это мероприятие!")
            return
        
        reg = Registration(user_id=user.id, event_id=event_id)
        session.add(reg)
        session.commit()
        
        text = (f"✅ <b>Вы успешно записаны!</b>\n\n"
                f"Мероприятие: <b>{event.title}</b>\n"
                f"Дата: {event.date.strftime('%d.%m.%Y')}\n\n"
                f"Запись №: <code>{reg.id}</code>")
        
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="📅 Мои записи", callback_data="my_events"),
                InlineKeyboardButton(text="📋 Все мероприятия", callback_data="back_to_events")
            ]]),
            parse_mode=ParseMode.HTML
        )
    finally:
        session.close()

@dp.callback_query(F.data == "back_to_events")
async def back_to_events(callback: types.CallbackQuery):
    session = Session()
    today = date.today()
    events = session.query(Event).filter(Event.date >= today).order_by(Event.date).all()
    
    if not events:
        await callback.message.edit_text("📭 На данный момент нет доступных мероприятий.")
        return
    
    text = "📅 <b>Предстоящие мероприятия:</b>\n\n"
    for idx, event in enumerate(events, 1):
        text += (f"{idx}. {format_event_short(event)}\n\n")
    
    await callback.message.edit_text(
        text,
        reply_markup=get_event_list_keyboard(events),
        parse_mode=ParseMode.HTML
    )
    session.close()

# --- Остальные обработчики --- #
@dp.callback_query(F.data.startswith("cancel_"))
async def cancel_registration(callback: types.CallbackQuery):
    reg_id = int(callback.data.split("_")[1])
    session = Session()
    
    try:
        reg = session.query(Registration).get(reg_id)
        if not reg:
            await callback.answer("Запись не найдена!")
            return
        
        if reg.user.tg_id != callback.from_user.id:
            await callback.answer("Это не ваша запись!")
            return
        
        event_title = reg.event.title
        session.delete(reg)
        session.commit()
        
        text = f"❌ Запись на мероприятие <b>{event_title}</b> отменена."
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="📅 Мои записи", callback_data="my_events")
            ]]),
            parse_mode=ParseMode.HTML
        )
    finally:
        session.close()

@dp.callback_query(F.data.startswith("export_"))
async def perform_export(callback: types.CallbackQuery):
    event_id = int(callback.data.split("_")[1])
    session = Session()
    event = session.query(Event).get(event_id)
    
    if not event:
        await callback.answer("Мероприятие не найдено!")
        return
    
    filename = f"participants_{event_id}.csv"
    with open(filename, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["ID", "ФИО", "Дата регистрации"])
        
        for reg in event.registrations:
            writer.writerow([
                reg.user.tg_id,
                reg.user.full_name,
                reg.registered_at.strftime("%Y-%m-%d %H:%M")
            ])
    
    text = f"📊 <b>Экспорт участников</b>\n\nМероприятие: <b>{event.title}</b>\nУчастников: {len(event.registrations)}"
    await callback.message.answer_document(
        types.FSInputFile(filename),
        caption=text,
        parse_mode=ParseMode.HTML
    )
    session.close()

@dp.callback_query(F.data.startswith("delete_"))
async def confirm_delete(callback: types.CallbackQuery):
    event_id = int(callback.data.split("_")[1])
    session = Session()
    event = session.query(Event).get(event_id)
    
    if not event:
        await callback.answer("Мероприятие не найдено!")
        return
    
    text = (f"⚠️ <b>Подтвердите удаление</b>\n\n"
            f"Мероприятие: <b>{event.title}</b>\n"
            f"Дата: {event.date.strftime('%d.%m.%Y')}\n"
            f"Участников: {len(event.registrations)}\n\n"
            f"Это действие нельзя отменить!")
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить удаление", callback_data=f"confirm_delete_{event_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_panel")]]
        ),
        parse_mode=ParseMode.HTML
    )
    session.close()

@dp.callback_query(F.data.startswith("confirm_delete_"))
async def perform_delete(callback: types.CallbackQuery):
    event_id = int(callback.data.split("_")[2])
    session = Session()
    event = session.query(Event).get(event_id)
    
    if event:
        title = event.title
        session.delete(event)
        session.commit()
        text = f"✅ Мероприятие <b>{title}</b> удалено!"
    else:
        text = "⚠️ Мероприятие не найдено"
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 В админ-панель", callback_data="admin_panel")
        ]]),
        parse_mode=ParseMode.HTML
    )
    session.close()

@dp.callback_query(F.data.startswith("users_"))
async def show_event_users(callback: types.CallbackQuery):
    event_id = int(callback.data.split("_")[1])
    session = Session()
    event = session.query(Event).get(event_id)
    
    if not event:
        await callback.answer("Мероприятие не найдено!")
        return
    
    registrations = event.registrations
    if not registrations:
        text = f"📭 На мероприятие <b>{event.title}</b> пока никто не зарегистрировался."
    else:
        text = f"👥 <b>Участники мероприятия</b>\n\nМероприятие: <b>{event.title}</b>\n\n"
        for reg in registrations:
            text += f"• {reg.user.full_name} (ID: {reg.user.tg_id})\n"
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📤 Экспорт", callback_data=f"export_{event_id}"),
            InlineKeyboardButton(text="🔙 Назад", callback_data="show_users")
        ]]),
        parse_mode=ParseMode.HTML
    )
    session.close()

# --- Обработка создания мероприятий --- #
@dp.message(F.text.contains(';'))
async def handle_event_creation(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    
    parts = message.text.split(';')
    if len(parts) != 4:
        await message.answer("⚠️ Неверный формат. Нужно 4 части, разделенные ';'", reply_markup=get_admin_keyboard())
        return
    
    try:
        title, topic, description, raw_date = [part.strip() for part in parts]
        event_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
    except ValueError:
        await message.answer("⚠️ Ошибка в формате даты. Используйте ГГГГ-ММ-ДД", reply_markup=get_admin_keyboard())
        return
    
    session = Session()
    event = Event(
        title=title,
        topic=topic,
        description=description,
        date=event_date
    )
    session.add(event)
    session.commit()
    
    text = (f"✅ <b>Мероприятие создано!</b>\n\n"
            f"ID: <code>{event.id}</code>\n"
            f"Название: <b>{title}</b>\n"
            f"Дата: {event_date.strftime('%d.%m.%Y')}")
    
    await message.answer(text, reply_markup=get_admin_keyboard(), parse_mode=ParseMode.HTML)
    session.close()

# --- Напоминания --- #
async def notify_users():
    session = Session()
    tomorrow = date.today() + timedelta(days=1)
    events = session.query(Event).filter_by(date=tomorrow).all()
    
    for event in events:
        for reg in event.registrations:
            try:
                await bot.send_message(
                    reg.user.tg_id,
                    f"🔔 <b>Напоминание о мероприятии</b>\n\n"
                    f"Завтра состоится: <b>{event.title}</b>\n"
                    f"Дата: {event.date.strftime('%d.%m.%Y')}\n\n"
                    f"Не забудьте прийти!",
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                print(f"Ошибка отправки напоминания: {e}")
    session.close()

# --- Запуск --- #
async def main():
    scheduler.add_job(notify_users, 'cron', hour=9, minute=0)
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
