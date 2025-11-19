"""
Telegram Bot для управления платежами и напоминаниями
Главный файл: bot.py
(Исправленная версия для aiogram 3.x с использованием Magic Filters F)
"""

import logging
import asyncio
from datetime import datetime, time
from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties  # Добавлен импорт

from database import Database
from config import TOKEN, ADMIN_ID, REMINDER_TIME
from utils import format_payment_list, format_date, parse_date, format_amount, get_next_occurrence, validate_amount, format_interval

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG,  # Изменено на DEBUG для детального логирования
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Исправленная инициализация бота
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Инициализация БД
db = Database()

# Состояния для добавления
class AddPayment(StatesGroup):
    name = State()
    amount = State()  # Новый порядок
    date = State()
    type = State()
    comment = State()
    recur_type = State()
    interval = State()
    repeats = State()

# Состояния для редактирования
class EditPayment(StatesGroup):
    name = State()
    amount = State()  # Новый порядок
    date = State()
    type = State()
    comment = State()
    recur_type = State()
    interval = State()
    repeats = State()

form_router = Router()
dp.include_router(form_router)

async def delete_message(chat_id: int, message_id: int):
    try:
        await bot.delete_message(chat_id, message_id)
    except:
        pass

async def delete_after_5s(chat_id: int, message_id: int):
    await asyncio.sleep(5)
    await delete_message(chat_id, message_id)

# Reply клавиатура для меню
def get_menu_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Меню")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )
    return keyboard

@form_router.message(CommandStart())
@form_router.message(F.text == "Меню")
async def command_start(message: types.Message, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить платеж", callback_data="add_payment")],
        [InlineKeyboardButton(text="📋 Список платежей", callback_data="list_payments")],
        [InlineKeyboardButton(text="📅 Платежи на сегодня", callback_data="today_payments")],
        [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")]
    ])
    
    await message.answer(
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        "Я помогу тебе управлять платежами и напоминаниями.\n"
        "Выбери действие:",
        reply_markup=keyboard
    )

# ====================== ДОБАВЛЕНИЕ ПЛАТЕЖА ======================

@form_router.callback_query(F.data == "add_payment")
async def start_add_payment(callback: types.CallbackQuery, state: FSMContext):
    logger.debug(f"Handler start_add_payment triggered with data: {callback.data}")  # Добавлен лог
    await state.set_state(AddPayment.name)
    msg = await callback.message.answer(
        "💳 Введите название платежа:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Отмена", callback_data="cancel_add")]
        ])
    )
    await state.update_data(last_bot_msg=msg.message_id)
    await callback.answer()
    asyncio.create_task(delete_after_5s(callback.message.chat.id, callback.message.message_id))

@form_router.message(AddPayment.name)
async def payment_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await delete_message(message.chat.id, data.get('last_bot_msg'))
    await message.delete()
    
    await state.update_data(payment_name=message.text.strip())
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="back_add")],
        [InlineKeyboardButton(text="Отмена", callback_data="cancel_add")]
    ])
    msg = await message.answer("💰 Введите сумму (мин. 1 ₽):", reply_markup=keyboard)
    await state.update_data(last_bot_msg=msg.message_id, prev_state=AddPayment.name)
    await state.set_state(AddPayment.amount)

@form_router.message(AddPayment.amount)
async def payment_amount(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await delete_message(message.chat.id, data.get('last_bot_msg'))
    await message.delete()
    
    amount = validate_amount(message.text.strip())
    if not amount:
        msg = await message.answer("❌ Неверная сумма (мин. 1 ₽). Повторите:")
        await state.update_data(last_bot_msg=msg.message_id)
        asyncio.create_task(delete_after_5s(msg.chat.id, msg.message_id))
        return
    
    await state.update_data(payment_amount=amount)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="back_add")],
        [InlineKeyboardButton(text="Отмена", callback_data="cancel_add")]
    ])
    msg = await message.answer("📅 Введите дату платежа (ДД.ММ.ГГГГ или ДДММГГ):", reply_markup=keyboard)
    await state.update_data(last_bot_msg=msg.message_id, prev_state=AddPayment.amount)
    await state.set_state(AddPayment.date)

@form_router.message(AddPayment.date)
async def payment_date(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await delete_message(message.chat.id, data.get('last_bot_msg'))
    await message.delete()
    
    payment_date = parse_date(message.text.strip())
    if not payment_date:
        msg = await message.answer("❌ Неверный формат или дата не в будущем. Повторите:")
        await state.update_data(last_bot_msg=msg.message_id)
        asyncio.create_task(delete_after_5s(msg.chat.id, msg.message_id))
        return
    
    await state.update_data(payment_date=payment_date)
    await ask_payment_type(message, state)

async def ask_payment_type(message: types.Message | types.CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Однократный", callback_data="type_once")],
        [InlineKeyboardButton(text="Повторяющийся", callback_data="type_recurring")],
        [InlineKeyboardButton(text="Назад", callback_data="back_add")],
        [InlineKeyboardButton(text="Отмена", callback_data="cancel_add")]
    ])
    msg = await message.answer("🔄 Тип платежа:", reply_markup=keyboard)
    await state.update_data(last_bot_msg=msg.message_id, prev_state=AddPayment.date)
    await state.set_state(AddPayment.type)

@form_router.callback_query(AddPayment.type, F.data.in_({"type_once", "type_recurring"}))
async def payment_type(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    await delete_message(callback.message.chat.id, data.get('last_bot_msg'))
    
    if callback.data == "type_once":
        await ask_payment_comment(callback.message, state)
        return
    
    # Повторяющийся
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Дни", callback_data="recur_days")],
        [InlineKeyboardButton(text="Месяцы", callback_data="recur_months")],
        [InlineKeyboardButton(text="Назад", callback_data="back_add")],
        [InlineKeyboardButton(text="Отмена", callback_data="cancel_add")]
    ])
    msg = await callback.message.answer("🔁 Тип интервала:", reply_markup=keyboard)
    await state.update_data(last_bot_msg=msg.message_id, prev_state=AddPayment.type)
    await state.set_state(AddPayment.recur_type)

@form_router.callback_query(AddPayment.recur_type, F.data.startswith("recur_"))
async def payment_recur_type(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    await delete_message(callback.message.chat.id, data.get('last_bot_msg'))
    
    interval_type = callback.data.split("_")[1]
    await state.update_data(interval_type=interval_type)
    
    # Популярные интервалы
    if interval_type == "days":
        buttons = [
            ["Ежедневно (1)", "interval_days_1"],
            ["Еженедельно (7)", "interval_days_7"],
            ["Раз в 2 недели (14)", "interval_days_14"],
            ["Ежемесячно (30)", "interval_days_30"],
            ["Вручную", "interval_manual"]
        ]
    else:
        buttons = [
            ["Ежемесячно (1)", "interval_months_1"],
            ["Ежеквартально (3)", "interval_months_3"],
            ["Ежегодно (12)", "interval_months_12"],
            ["Вручную", "interval_manual"]
        ]
    
    keyboard_rows = [[InlineKeyboardButton(text=text, callback_data=data)] for text, data in buttons]
    keyboard_rows.append([InlineKeyboardButton(text="Назад", callback_data="back_add")])
    keyboard_rows.append([InlineKeyboardButton(text="Отмена", callback_data="cancel_add")])
    
    msg = await callback.message.answer(f"🔁 Выберите интервал:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows))
    await state.update_data(last_bot_msg=msg.message_id)
    await state.set_state(AddPayment.interval)

@form_router.callback_query(AddPayment.interval, F.data.startswith("interval_"))
async def select_predefined_interval(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    await delete_message(callback.message.chat.id, data.get('last_bot_msg'))
    
    if callback.data == "interval_manual":
        msg = await callback.message.answer("🔢 Введите число вручную:")
        await state.update_data(last_bot_msg=msg.message_id)
        return
    
    value = int(callback.data.split("_")[-1])
    await state.update_data(interval_value=value)
    await ask_repeats(callback.message, state)

@form_router.message(AddPayment.interval)
async def payment_interval_manual(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await delete_message(message.chat.id, data.get('last_bot_msg'))
    await message.delete()
    
    try:
        value = int(message.text.strip())
        if value <= 0:
            raise ValueError
        await state.update_data(interval_value=value)
        await ask_repeats(message, state)
    except ValueError:
        msg = await message.answer("❌ Положительное число!")
        await state.update_data(last_bot_msg=msg.message_id)
        asyncio.create_task(delete_after_5s(msg.chat.id, msg.message_id))

async def ask_repeats(message: types.Message | types.CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="back_add")],
        [InlineKeyboardButton(text="Отмена", callback_data="cancel_add")]
    ])
    msg = await message.answer("🔢 Количество повторений (0 = бесконечно):", reply_markup=keyboard)
    await state.update_data(last_bot_msg=msg.message_id)
    await state.set_state(AddPayment.repeats)

@form_router.message(AddPayment.repeats)
async def payment_repeats(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await delete_message(message.chat.id, data.get('last_bot_msg'))
    await message.delete()
    
    try:
        repeats = int(message.text.strip())
        if repeats < 0:
            raise ValueError
    except ValueError:
        msg = await message.answer("❌ Некорректное число!")
        await state.update_data(last_bot_msg=msg.message_id)
        asyncio.create_task(delete_after_5s(msg.chat.id, msg.message_id))
        return
    
    # Сохранение повторяющегося
    payment_id = db.add_payment(
        user_id=message.from_user.id,
        chat_id=message.chat.id,
        name=data['payment_name'],
        date=data['payment_date'],
        amount=data['payment_amount'],
        comment=data.get('payment_comment'),
        is_recurring=True,
        interval_type=data['interval_type'],
        interval_value=data['interval_value'],
        repeat_count=repeats if repeats > 0 else None
    )
    
    await notify_admin(message.from_user, data, recurring=True, repeats=repeats)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Добавить ещё", callback_data="add_payment")],
        [InlineKeyboardButton(text="Меню", callback_data="back_to_menu")],
        [InlineKeyboardButton(text="Закрыть", callback_data="close")]
    ])
    final_msg = await message.answer("✅ Повторяющийся платеж добавлен!", reply_markup=keyboard)
    asyncio.create_task(delete_after_5s(message.chat.id, final_msg.message_id))
    await state.clear()

async def ask_payment_comment(message: types.Message | types.CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустить", callback_data="skip_comment")],
        [InlineKeyboardButton(text="Назад", callback_data="back_add")],
        [InlineKeyboardButton(text="Отмена", callback_data="cancel_add")]
    ])
    msg = await message.answer("📝 Комментарий (или пропустить):", reply_markup=keyboard)
    await state.update_data(last_bot_msg=msg.message_id, prev_state=AddPayment.type)
    await state.set_state(AddPayment.comment)

@form_router.message(AddPayment.comment)
async def payment_comment_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await delete_message(message.chat.id, data.get('last_bot_msg'))
    await message.delete()
    
    await state.update_data(payment_comment=message.text.strip())
    # Сохранение однократного (поскольку тип already once)
    payment_id = db.add_payment(
        user_id=message.from_user.id,
        chat_id=message.chat.id,
        name=data['payment_name'],
        date=data['payment_date'],
        amount=data['payment_amount'],
        comment=data.get('payment_comment'),
        is_recurring=False
    )
    await notify_admin(message.from_user, data, recurring=False)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Добавить ещё", callback_data="add_payment")],
        [InlineKeyboardButton(text="Меню", callback_data="back_to_menu")],
        [InlineKeyboardButton(text="Закрыть", callback_data="close")]
    ])
    final_msg = await message.answer("✅ Платеж добавлен!", reply_markup=keyboard)
    asyncio.create_task(delete_after_5s(message.chat.id, final_msg.message_id))
    await state.clear()

@form_router.callback_query(AddPayment.comment, F.data == "skip_comment")
async def payment_comment_skip(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    await delete_message(callback.message.chat.id, data.get('last_bot_msg'))
    await state.update_data(payment_comment=None)
    # Сохранение однократного
    payment_id = db.add_payment(
        user_id=callback.from_user.id,
        chat_id=callback.message.chat.id,
        name=data['payment_name'],
        date=data['payment_date'],
        amount=data['payment_amount'],
        comment=None,
        is_recurring=False
    )
    await notify_admin(callback.from_user, data, recurring=False)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Добавить ещё", callback_data="add_payment")],
        [InlineKeyboardButton(text="Меню", callback_data="back_to_menu")],
        [InlineKeyboardButton(text="Закрыть", callback_data="close")]
    ])
    final_msg = await callback.message.answer("✅ Платеж добавлен!", reply_markup=keyboard)
    asyncio.create_task(delete_after_5s(callback.message.chat.id, final_msg.message_id))
    await state.clear()

# ====================== НАЗАД / ОТМЕНА ======================

@form_router.callback_query(F.data == "back_add")
async def handle_add_back(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    current_state = await state.get_state()
    data = await state.get_data()
    prev = data.get('prev_state')
    if prev:
        await state.set_state(prev)
        # Здесь можно добавить переотправку предыдущего сообщения, но для простоты — пользователь просто вводит заново
    else:
        await cancel_add(callback, state)

@form_router.callback_query(F.data == "cancel_add")
async def cancel_add(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await back_to_menu(callback.message)

# ====================== СПИСОК ПЛАТЕЖЕЙ ======================

@form_router.callback_query(F.data == "list_payments")
async def show_chat_payments(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    payments = db.get_active_payments_by_chat(callback.message.chat.id)

    if not payments:
        msg = await callback.message.answer("📭 В этом чате нет активных платежей.")
        asyncio.create_task(delete_after_5s(msg.chat.id, msg.message_id))
        return

    # Формируем список кнопок — каждый платеж отдельная кнопка
    keyboard_rows = [
        [InlineKeyboardButton(text=f"{p['name']}, {format_amount(p['amount'])}, {format_date(p['date'])}, {'Повтор.' if p['is_recurring'] else 'Однокр.'}", callback_data=f"payment_select:{p['id']}")]
        for p in payments
    ]
    keyboard_rows.append([InlineKeyboardButton(text="Меню", callback_data="back_to_menu")])
    keyboard_rows.append([InlineKeyboardButton(text="Закрыть", callback_data="close")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    msg = await callback.message.answer("📋 Выберите платеж:", reply_markup=keyboard)
    await state.update_data(list_msg_id=msg.message_id)
    asyncio.create_task(delete_after_5s(callback.message.chat.id, callback.message.message_id))

# ====================== ДЕТАЛИ ПЛАТЕЖА ======================

@form_router.callback_query(F.data.startswith("payment_select:"))
async def show_payment_details(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    payment_id = int(callback.data.split(":")[1])
    payment = db.get_payment(payment_id)

    data = await state.get_data()
    if 'list_msg_id' in data:
        await delete_message(callback.message.chat.id, data['list_msg_id'])

    if not payment:
        msg = await callback.message.answer("❌ Платеж не найден.")
        asyncio.create_task(delete_after_5s(msg.chat.id, msg.message_id))
        return

    text = (
        f"💳 <b>{payment['name']}</b>\n"
        f"📅 {format_date(payment['date'])}\n"
        f"💰 {format_amount(payment['amount'])}\n"
    )
    if payment.get("comment"):
        text += f"📝 {payment['comment']}\n"
    if payment.get("is_recurring"):
        text += f"🔄 Повторяющийся ({format_interval(payment['interval_type'], payment['interval_value'])})\n"
    text += f"🆔 ID: {payment_id}"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Оплачен", callback_data=f"payment_done:{payment_id}")],
        [InlineKeyboardButton(text="✏️ Изменить", callback_data=f"payment_edit:{payment_id}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"payment_delete:{payment_id}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="list_payments")]
    ])
    await callback.message.answer(text, reply_markup=keyboard)


# ====================== ДЕЙСТВИЯ С ПЛАТЕЖОМ ======================

@form_router.callback_query(F.data.startswith("payment_done:"))
async def mark_payment_done(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    payment_id = int(callback.data.split(":")[1])
    db.complete_payment(payment_id)
    msg = await callback.message.answer("✅ Платеж отмечен как выполненный.")
    asyncio.create_task(delete_after_5s(msg.chat.id, msg.message_id))


@form_router.callback_query(F.data.startswith("payment_delete:"))
async def delete_payment(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    payment_id = int(callback.data.split(":")[1])
    db.delete_payment(payment_id)
    msg = await callback.message.answer("🗑 Платеж удалён.")
    asyncio.create_task(delete_after_5s(msg.chat.id, msg.message_id))

# ====================== РЕДАКТИРОВАНИЕ ПЛАТЕЖА (ЦИКЛ) ======================

def edit_controls(step: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data=f"skip:{step}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back:{step}")],
        [InlineKeyboardButton(text="✅ Завершить", callback_data="finish_edit")]
    ])


# Запуск цикла редактирования
@form_router.callback_query(F.data.startswith("payment_edit:"))
async def start_edit_cycle(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    payment_id = int(callback.data.split(":")[1])
    await state.update_data(edit_payment_id=payment_id, step="name")
    await state.set_state(EditPayment.name)
    await callback.message.edit_text("Введите новое название платежа:", reply_markup=edit_controls("name"))


# === Название
@form_router.message(EditPayment.name)
async def edit_name_step(message: types.Message, state: FSMContext):
    data = await state.get_data()
    db.update_payment_field(data["edit_payment_id"], "name", message.text.strip())
    await message.delete()
    await state.update_data(step="amount")
    await state.set_state(EditPayment.amount)
    await message.answer("Введите новую сумму:", reply_markup=edit_controls("amount"))


# === Сумма
@form_router.message(EditPayment.amount)
async def edit_amount_step(message: types.Message, state: FSMContext):
    new_amount = validate_amount(message.text.strip())
    await message.delete()
    if not new_amount:
        msg = await message.answer("❌ Некорректная сумма. Попробуйте снова.")
        asyncio.create_task(delete_after_5s(msg.chat.id, msg.message_id))
        return
    data = await state.get_data()
    db.update_payment_field(data["edit_payment_id"], "amount", new_amount)
    await state.update_data(step="date")
    await state.set_state(EditPayment.date)
    await message.answer("Введите новую дату (ДДММ или ДДММГГ):", reply_markup=edit_controls("date"))


# === Дата
@form_router.message(EditPayment.date)
async def edit_date_step(message: types.Message, state: FSMContext):
    new_date = parse_date(message.text.strip())
    await message.delete()
    if not new_date:
        msg = await message.answer("❌ Неверный формат даты. Попробуйте снова.")
        asyncio.create_task(delete_after_5s(msg.chat.id, msg.message_id))
        return
    data = await state.get_data()
    db.update_payment_field(data["edit_payment_id"], "date", new_date)
    await ask_edit_type(message, state)


async def ask_edit_type(message: types.Message | types.CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Однократный", callback_data="type_once_edit")],
        [InlineKeyboardButton(text="Повторяющийся", callback_data="type_recurring_edit")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back:type")],
        [InlineKeyboardButton(text="✅ Завершить", callback_data="finish_edit")]
    ])
    msg = await message.answer("🔄 Выберите тип платежа:", reply_markup=keyboard)
    await state.update_data(last_bot_msg=msg.message_id, prev_state=EditPayment.date)
    await state.set_state(EditPayment.type)

@form_router.callback_query(EditPayment.type, F.data.in_({"type_once_edit", "type_recurring_edit"}))
async def edit_payment_type(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    await delete_message(callback.message.chat.id, data.get('last_bot_msg'))
    
    payment_id = data['edit_payment_id']
    is_recurring = callback.data == "type_recurring_edit"
    db.update_payment_field(payment_id, "is_recurring", is_recurring)
    
    if not is_recurring:
        await ask_edit_comment(callback.message, state)
        return
    
    # Повторяющийся
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Дни", callback_data="recur_days_edit")],
        [InlineKeyboardButton(text="Месяцы", callback_data="recur_months_edit")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back:recur_type")],
        [InlineKeyboardButton(text="✅ Завершить", callback_data="finish_edit")]
    ])
    msg = await callback.message.answer("🔁 Тип интервала:", reply_markup=keyboard)
    await state.update_data(last_bot_msg=msg.message_id, prev_state=EditPayment.type)
    await state.set_state(EditPayment.recur_type)

@form_router.callback_query(EditPayment.recur_type, F.data.startswith("recur_") & F.data.endswith("_edit"))
async def edit_payment_recur_type(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    await delete_message(callback.message.chat.id, data.get('last_bot_msg'))
    
    interval_type = callback.data.split("_")[1]
    db.update_payment_field(data['edit_payment_id'], "interval_type", interval_type)
    await state.update_data(interval_type=interval_type)
    
    # Популярные интервалы
    if interval_type == "days":
        buttons = [
            ["Ежедневно (1)", "interval_days_1_edit"],
            ["Еженедельно (7)", "interval_days_7_edit"],
            ["Раз в 2 недели (14)", "interval_days_14_edit"],
            ["Ежемесячно (30)", "interval_days_30_edit"],
            ["Вручную", "interval_manual_edit"]
        ]
    else:
        buttons = [
            ["Ежемесячно (1)", "interval_months_1_edit"],
            ["Ежеквартально (3)", "interval_months_3_edit"],
            ["Ежегодно (12)", "interval_months_12_edit"],
            ["Вручную", "interval_manual_edit"]
        ]
    
    keyboard_rows = [[InlineKeyboardButton(text=text, callback_data=data)] for text, data in buttons]
    keyboard_rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back:interval")])
    keyboard_rows.append([InlineKeyboardButton(text="✅ Завершить", callback_data="finish_edit")])
    
    msg = await callback.message.answer(f"🔁 Выберите интервал:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows))
    await state.update_data(last_bot_msg=msg.message_id, prev_state=EditPayment.recur_type)
    await state.set_state(EditPayment.interval)

@form_router.callback_query(EditPayment.interval, F.data.startswith("interval_") & F.data.endswith("_edit"))
async def edit_select_predefined_interval(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    await delete_message(callback.message.chat.id, data.get('last_bot_msg'))
    
    if callback.data == "interval_manual_edit":
        msg = await callback.message.answer("🔢 Введите число вручную:")
        await state.update_data(last_bot_msg=msg.message_id)
        return
    
    value_str = callback.data.split("_")[-2]
    value = int(value_str)
    db.update_payment_field(data['edit_payment_id'], "interval_value", value)
    await state.update_data(interval_value=value)
    await ask_edit_repeats(callback.message, state)

@form_router.message(EditPayment.interval)
async def edit_payment_interval_manual(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await delete_message(message.chat.id, data.get('last_bot_msg'))
    await message.delete()
    
    try:
        value = int(message.text.strip())
        if value <= 0:
            raise ValueError
        db.update_payment_field(data['edit_payment_id'], "interval_value", value)
        await state.update_data(interval_value=value)
        await ask_edit_repeats(message, state)
    except ValueError:
        msg = await message.answer("❌ Положительное число!")
        await state.update_data(last_bot_msg=msg.message_id)
        asyncio.create_task(delete_after_5s(msg.chat.id, msg.message_id))

async def ask_edit_repeats(message: types.Message | types.CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back:repeats")],
        [InlineKeyboardButton(text="✅ Завершить", callback_data="finish_edit")]
    ])
    msg = await message.answer("🔢 Количество повторений (0 = бесконечно):", reply_markup=keyboard)
    await state.update_data(last_bot_msg=msg.message_id, prev_state=EditPayment.interval)
    await state.set_state(EditPayment.repeats)

@form_router.message(EditPayment.repeats)
async def edit_repeats_step(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await delete_message(message.chat.id, data.get('last_bot_msg'))
    await message.delete()
    
    try:
        repeats = int(message.text.strip())
        if repeats < 0:
            raise ValueError
        db.update_payment_field(data["edit_payment_id"], "repeat_count", repeats if repeats > 0 else None)
        await ask_edit_comment(message, state)
    except ValueError:
        msg = await message.answer("❌ Некорректное число.")
        asyncio.create_task(delete_after_5s(msg.chat.id, msg.message_id))
        await state.update_data(last_bot_msg=msg.message_id)

async def ask_edit_comment(message: types.Message | types.CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустить", callback_data="skip_comment_edit")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back:comment")],
        [InlineKeyboardButton(text="✅ Завершить", callback_data="finish_edit")]
    ])
    msg = await message.answer("📝 Введите новый комментарий (или пропустить):", reply_markup=keyboard)
    await state.update_data(last_bot_msg=msg.message_id, prev_state=EditPayment.type if 'is_recurring' else EditPayment.repeats)
    await state.set_state(EditPayment.comment)

@form_router.message(EditPayment.comment)
async def edit_comment_step(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await delete_message(message.chat.id, data.get('last_bot_msg'))
    await message.delete()
    db.update_payment_field(data["edit_payment_id"], "comment", message.text.strip())
    msg = await message.answer("✅ Редактирование завершено.")
    asyncio.create_task(delete_after_5s(msg.chat.id, msg.message_id))
    await state.clear()

@form_router.callback_query(EditPayment.comment, F.data == "skip_comment_edit")
async def edit_comment_skip(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    await delete_message(callback.message.chat.id, data.get('last_bot_msg'))
    db.update_payment_field(data["edit_payment_id"], "comment", None)
    msg = await callback.message.answer("✅ Редактирование завершено.")
    asyncio.create_task(delete_after_5s(msg.chat.id, msg.message_id))
    await state.clear()

# ====================== КНОПКИ УПРАВЛЕНИЯ ======================

@form_router.callback_query(F.data.startswith("skip:"))
async def skip_step(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    step = callback.data.split(":")[1]
    # переход к следующему шагу
    if step == "name":
        await state.set_state(EditPayment.amount)
        await state.update_data(step="amount")
        await callback.message.edit_text("Введите новую сумму:", reply_markup=edit_controls("amount"))
    elif step == "amount":
        await state.set_state(EditPayment.date)
        await state.update_data(step="date")
        await callback.message.edit_text("Введите новую дату (ДД.ММ.ГГГГ или ДДММГГ):", reply_markup=edit_controls("date"))
    elif step == "date":
        await ask_edit_type(callback.message, state)
    elif step == "type":
        await ask_edit_comment(callback.message, state)
    elif step == "comment":
        msg = await callback.message.answer("✅ Редактирование завершено.")
        asyncio.create_task(delete_after_5s(msg.chat.id, msg.message_id))
        await state.clear()
    elif step == "recur_type":
        await ask_edit_type(callback.message, state)
    elif step == "interval":
        await ask_edit_repeats(callback.message, state)
    elif step == "repeats":
        await ask_edit_comment(callback.message, state)


@form_router.callback_query(F.data.startswith("back:"))
async def back_step(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    step = callback.data.split(":")[1]
    # возвращаемся на предыдущий шаг
    if step == "amount":
        await state.set_state(EditPayment.name)
        await state.update_data(step="name")
        await callback.message.edit_text("Введите новое название платежа:", reply_markup=edit_controls("name"))
    elif step == "date":
        await state.set_state(EditPayment.amount)
        await state.update_data(step="amount")
        await callback.message.edit_text("Введите новую сумму:", reply_markup=edit_controls("amount"))
    elif step == "type":
        await state.set_state(EditPayment.date)
        await state.update_data(step="date")
        await callback.message.edit_text("Введите новую дату (ДД.ММ.ГГГГ или ДДММГГ):", reply_markup=edit_controls("date"))
    elif step == "comment":
        await ask_edit_type(callback.message, state)
    elif step == "recur_type":
        await ask_edit_type(callback.message, state)
    elif step == "interval":
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Дни", callback_data="recur_days_edit")],
            [InlineKeyboardButton(text="Месяцы", callback_data="recur_months_edit")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back:recur_type")],
            [InlineKeyboardButton(text="✅ Завершить", callback_data="finish_edit")]
        ])
        await callback.message.edit_text("🔁 Тип интервала:", reply_markup=keyboard)
        await state.set_state(EditPayment.recur_type)
    elif step == "repeats":
        # Назад к интервалу
        data = await state.get_data()
        interval_type = data.get('interval_type', 'days')
        if interval_type == "days":
            buttons = [
                ["Ежедневно (1)", "interval_days_1_edit"],
                ["Еженедельно (7)", "interval_days_7_edit"],
                ["Раз в 2 недели (14)", "interval_days_14_edit"],
                ["Ежемесячно (30)", "interval_days_30_edit"],
                ["Вручную", "interval_manual_edit"]
            ]
        else:
            buttons = [
                ["Ежемесячно (1)", "interval_months_1_edit"],
                ["Ежеквартально (3)", "interval_months_3_edit"],
                ["Ежегодно (12)", "interval_months_12_edit"],
                ["Вручную", "interval_manual_edit"]
            ]
        keyboard_rows = [[InlineKeyboardButton(text=text, callback_data=data)] for text, data in buttons]
        keyboard_rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back:interval")])
        keyboard_rows.append([InlineKeyboardButton(text="✅ Завершить", callback_data="finish_edit")])
        
        await callback.message.edit_text(f"🔁 Выберите интервал:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows))
        await state.set_state(EditPayment.interval)


@form_router.callback_query(F.data == "finish_edit")
async def finish_edit(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    msg = await callback.message.answer("✅ Редактирование завершено.")
    asyncio.create_task(delete_after_5s(msg.chat.id, msg.message_id))
    await state.clear()


# ====================== НЕДОСТАЮЩИЕ HANDLERS ======================

@form_router.callback_query(F.data == "back_to_menu")
async def handle_back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    if 'list_msg_id' in data:
        await delete_message(callback.message.chat.id, data['list_msg_id'])
    await back_to_menu(callback.message)
    await state.clear()

@form_router.callback_query(F.data == "close")
async def handle_close(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        await callback.message.delete()
    except:
        pass
    await back_to_menu(callback.message)  # Добавлено по требованию
    await state.clear()

@form_router.callback_query(F.data == "help")
async def show_help(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    help_text = (
        "ℹ️ Помощь по боту:\n\n"
        "• /start - Главное меню\n"
        "• Добавление платежа: Укажите название, дату, сумму, комментарий и тип (однократный или повторяющийся)\n"
        "• Список платежей: Просмотр активных платежей в чате\n"
        "• Платежи на сегодня: Показывает платежи на текущую дату\n"
        "• Редактирование: Изменяйте поля платежа последовательно\n"
        "• Напоминания: Ежедневно в указанное время (REMINDER_TIME)\n\n"
        "Если проблемы - свяжитесь с администратором."
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Закрыть", callback_data="close")]
    ])
    msg = await callback.message.answer(help_text, reply_markup=keyboard)
    asyncio.create_task(delete_after_5s(callback.message.chat.id, callback.message.message_id))

@form_router.callback_query(F.data == "today_payments")
async def show_today_payments(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    today = datetime.now().date()
    payments = db.get_payments_by_date(today)
    if not payments:
        msg = await callback.message.answer("📅 На сегодня нет платежей.")
        asyncio.create_task(delete_after_5s(msg.chat.id, msg.message_id))
        return
    text = format_payment_list(payments)
    msg = await callback.message.answer(text)
    asyncio.create_task(delete_after_5s(callback.message.chat.id, callback.message.message_id))

# ====================== УВЕДОМЛЕНИЯ АДМИНУ ======================

async def notify_admin(user: types.User, data: dict, recurring: bool = False, repeats: int = 0):
    if not ADMIN_ID:
        return
    username = user.username or user.first_name
    text = f"➕ Новый {'повторяющийся ' if recurring else ''}платеж\n"
    text += f"От: @{username} ({user.id})\n"
    text += f"Название: {data['payment_name']}\n"
    text += f"Дата: {format_date(data['payment_date'])}\n"
    text += f"Сумма: {format_amount(data['payment_amount'])}\n"
    if recurring:
        interval_text = format_interval(data['interval_type'], data['interval_value'])
        repeat_text = f"{repeats} раз" if repeats > 0 else "бесконечно"
        text += f"Интервал: {interval_text}\nПовторений: {repeat_text}"
    try:
        await bot.send_message(ADMIN_ID, text)
    except Exception as e:
        logger.error(f"Ошибка уведомления админа: {e}")


# ====================== ЗАПУСК ======================

async def scheduler():
    while True:
        now = datetime.now()
        if now.hour == REMINDER_TIME[0] and now.minute == REMINDER_TIME[1]:
            await send_daily_reminders()
        await asyncio.sleep(60)

async def send_daily_reminders():
    today = datetime.now().date()
    payments = db.get_payments_by_date(today)
    for p in payments:
        text = f"<a href=\"tg://user?id={p['user_id']}\">Пользователь</a>\n🔔 Напоминание:\n"
        text += f"{p['name']} — {format_amount(p['amount'])}"
        if p['comment']:
            text += f"\n{p['comment']}"
        await bot.send_message(p['chat_id'], text)

async def back_to_menu(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить платеж", callback_data="add_payment")],
        [InlineKeyboardButton(text="📋 Список", callback_data="list_payments")],
        [InlineKeyboardButton(text="Сегодня", callback_data="today_payments")],
        [InlineKeyboardButton(text="Помощь", callback_data="help")]
    ])
    await message.answer("Меню:", reply_markup=keyboard)  # Изменено на answer, чтобы не редактировать удалённое сообщение

async def main():
    asyncio.create_task(scheduler())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())