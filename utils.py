"""
Вспомогательные функции
utils.py
"""

from datetime import datetime, date, timedelta
from typing import List, Tuple, Optional
from dateutil.relativedelta import relativedelta
from decimal import Decimal


def format_date(date: datetime.date) -> str:
    """
    Форматировать дату в читаемый вид
    """
    months = {
        1: "января", 2: "февраля", 3: "марта", 4: "апреля",
        5: "мая", 6: "июня", 7: "июля", 8: "августа",
        9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
    }
    
    return f"{date.day} {months[date.month]} {date.year}"


def format_amount(amount: Decimal) -> str:
    """
    Форматировать сумму с разделителями тысяч
    """
    return f"{amount:,.2f} ₽".replace(",", " ")


def format_payment_list(payments: List[dict]) -> str:
    """
    Форматировать список платежей для отображения
    """
    if not payments:
        return "Нет платежей"
    
    text = ""
    total = Decimal('0')
    
    for payment in payments:
        payment_id = payment['id']
        name = payment['name']
        date = payment['date']
        amount = payment['amount']
        comment = payment['comment']
        is_recurring = payment['is_recurring']
        interval_type = payment['interval_type']
        interval_value = payment['interval_value']
        
        total += amount
        
        # Основная информация
        text += f"💳 <b>{name}</b>\n"
        text += f"📅 {format_date(date)}\n"
        text += f"💰 {format_amount(amount)}\n"
        
        # Комментарий
        if comment:
            text += f"📝 {comment}\n"
        
        # Тип платежа
        if is_recurring:
            text += f"🔄 Повтор. ({format_interval(interval_type, interval_value)})"
            if payment['repeat_count']:
                text += f", осталось: {payment['repeat_count']} раз"
            text += "\n"
        
        text += f"🆔 ID: {payment_id}\n"
        text += "\n"
    
    # Итого
    text += f"<b>Итого:</b> {format_amount(total)}"
    
    return text


def get_next_occurrence(
    current_date: datetime.date,
    interval_type: str,
    interval_value: int
) -> Optional[datetime.date]:
    """
    Рассчитать следующую дату повторяющегося платежа
    """
    if not interval_value or interval_value <= 0:
        return None
    
    if interval_type == 'days':
        return current_date + timedelta(days=interval_value)
    elif interval_type == 'months':
        return current_date + relativedelta(months=interval_value)
    return None


def parse_date(date_str: str) -> Optional[date]:
    """
    Парсинг даты из строки с поддержкой нескольких форматов.
    Возвращает только будущие даты (строго больше сегодняшней).
    Поддерживает формат DDMM (без года).
    """
    formats = [
        "%d.%m.%Y", "%d%m%Y", "%d-%m-%Y", "%d/%m/%Y",  # полный год
        "%d.%m.%y", "%d%m%y", "%d-%m-%y", "%d/%m-%y"   # двухзначный год
    ]
    date_str = date_str.strip()

    # Обработка формата DDMM (без года)
    if len(date_str) == 4 and date_str.isdigit():
        try:
            dt = datetime.strptime(date_str, "%d%m")
            today = date.today()
            candidate = date(today.year, dt.month, dt.day)
            if candidate <= today:
                candidate = date(today.year + 1, dt.month, dt.day)
            return candidate
        except ValueError:
            return None

    # Остальные форматы
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            parsed_date = dt.date()
            if parsed_date > date.today():
                return parsed_date
        except ValueError:
            continue
    return None


def get_days_until(target_date: datetime.date) -> int:
    """
    Получить количество дней до целевой даты
    """
    today = datetime.now().date()
    delta = target_date - today
    return delta.days


def format_interval(interval_type: str, value: int) -> str:
    """
    Форматировать интервал в читаемый вид
    """
    if interval_type == 'days':
        if value == 1:
            return "ежедневно"
        elif value == 7:
            return "еженедельно"
        elif value == 14:
            return "раз в 2 недели"
        elif value in (30, 31):
            return "ежемесячно"
        elif value == 365:
            return "ежегодно"
        else:
            return f"каждые {value} дн."
    elif interval_type == 'months':
        if value == 1:
            return "ежемесячно"
        else:
            return f"каждые {value} месяцев"
    return f"{interval_type} {value}"


def validate_amount(amount_str: str) -> Optional[Decimal]:
    """
    Валидация и парсинг суммы
    Добавлена минимальная сумма 1 руб
    """
    try:
        amount = Decimal(amount_str.replace(',', '.').replace(' ', ''))
        if amount >= Decimal('1'):
            return amount.quantize(Decimal('0.01'))
        return None
    except ValueError:
        return None


def truncate_text(text: str, max_length: int = 100) -> str:
    """
    Обрезать текст до заданной длины
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def generate_payment_summary(payments: List[dict]) -> dict:
    """
    Генерировать сводку по платежам
    """
    if not payments:
        return {
            'count': 0,
            'total_amount': Decimal('0'),
            'recurring_count': 0,
            'nearest_date': None
        }
    
    total_amount = sum(p['amount'] for p in payments)
    recurring_count = sum(1 for p in payments if p['is_recurring'])
    
    # Найти ближайшую дату
    dates = [p['date'] for p in payments]
    nearest_date = min(dates)
    
    return {
        'count': len(payments),
        'total_amount': total_amount,
        'recurring_count': recurring_count,
        'nearest_date': nearest_date
    }