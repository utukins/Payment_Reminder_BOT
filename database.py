"""
Модуль для работы с базой данных
database.py
"""

import logging
from datetime import datetime, timedelta
from typing import List, Tuple, Optional
from decimal import Decimal

from sqlalchemy import create_engine, select, Column, Integer, String, Text, Boolean, ForeignKey, Date, func, text, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from sqlalchemy.types import DECIMAL  # Для Decimal типа

from dateutil.relativedelta import relativedelta

from config import DATABASE_NAME  # Добавлен импорт
from utils import get_next_occurrence  # Импорт для complete_payment

logger = logging.getLogger(__name__)

# Создание двигателя SQLite
engine = create_engine(f"sqlite:///{DATABASE_NAME}", echo=True)

class Base(DeclarativeBase):
    pass

class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    user_id: Mapped[int]
    chat_id: Mapped[int]
    date: Mapped[datetime.date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(DECIMAL(10, 2))  # Изменено на Decimal
    comment: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default='active')
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    interval_type: Mapped[Optional[str]] = mapped_column(String(50))
    interval_value: Mapped[Optional[int]] = mapped_column(Integer)
    repeat_count: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)

    __table_args__ = (
        Index('idx_payments_user_chat_date', 'user_id', 'chat_id', 'date'),  # Добавлен индекс
    )

class Log(Base):
    __tablename__ = "logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int]
    payment_id: Mapped[Optional[int]] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(50))
    details: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)

# Создание таблиц
Base.metadata.create_all(engine)

class Database:
    """Класс для работы с базой данных через SQLAlchemy ORM"""
    
    def __init__(self):
        self.engine = engine
        self._migrate()  # Добавлен вызов миграции
    
    def _migrate(self):
        """Проверка и добавление отсутствующих колонок"""
        with self.engine.connect() as conn:
            try:
                # Проверка наличия колонок в payments
                result = conn.execute(text("PRAGMA table_info(payments)"))
                columns = {row[1]: row[2] for row in result}  # {name: type}
                
                if 'chat_id' not in columns:
                    conn.execute(text("ALTER TABLE payments ADD COLUMN chat_id INTEGER"))
                    logger.info("Добавлена колонка chat_id в таблицу payments")
                
                if 'interval_type' not in columns:
                    conn.execute(text("ALTER TABLE payments ADD COLUMN interval_type TEXT"))
                    logger.info("Добавлена колонка interval_type в таблицу payments")
                
                if 'interval_value' not in columns:
                    conn.execute(text("ALTER TABLE payments ADD COLUMN interval_value INTEGER"))
                    logger.info("Добавлена колонка interval_value в таблицу payments")
                
                if 'repeat_count' not in columns:
                    conn.execute(text("ALTER TABLE payments ADD COLUMN repeat_count INTEGER"))
                    logger.info("Добавлена колонка repeat_count в таблицу payments")
                
                if 'is_recurring' not in columns:
                    conn.execute(text("ALTER TABLE payments ADD COLUMN is_recurring BOOLEAN DEFAULT 0"))
                    logger.info("Добавлена колонка is_recurring в таблицу payments")
                
                # Проверка типа amount (улучшено для Decimal)
                if 'amount' in columns and columns['amount'].upper() != 'DECIMAL':
                    logger.warning("Колонка amount имеет тип FLOAT вместо DECIMAL. Рекомендуется сбросить БД для изменения типа.")
                    # В SQLite нельзя изменить тип без пересоздания таблицы, так что только warning
                
                conn.commit()
            except OperationalError as e:
                logger.error(f"Ошибка миграции: {e}")
    
    def _get_session(self):
        return Session(self.engine)
    
    def add_payment(
        self,
        user_id: int,
        chat_id: int,
        name: str,
        date: datetime.date,
        amount: Decimal,  # Изменено на Decimal
        comment: Optional[str] = None,
        is_recurring: bool = False,
        interval_type: Optional[str] = None,
        interval_value: Optional[int] = None,
        repeat_count: Optional[int] = None
    ) -> int:
        """
        Добавить новый платеж
        """
        with self._get_session() as session:
            payment = Payment(
                name=name,
                user_id=user_id,
                chat_id=chat_id,
                date=date,
                amount=amount,
                comment=comment,
                is_recurring=is_recurring,
                interval_type=interval_type,
                interval_value=interval_value,
                repeat_count=repeat_count
            )
            session.add(payment)
            session.commit()
            payment_id = payment.id
            
            # Логирование
            self._log_action(session, user_id, payment_id, "add", f"Добавлен платеж: {name}, {amount} ₽, дата: {date}")
            
            return payment_id
    
    def get_payment(self, payment_id: int) -> Optional[dict]:
        """Получить платеж по ID"""
        with self._get_session() as session:
            stmt = select(Payment).where(Payment.id == payment_id)
            result = session.scalar(stmt)
            return result.__dict__ if result else None
    
    def get_active_payments(self, user_id: int, chat_id: int) -> List[dict]:
        """Получить все активные платежи пользователя в чате"""
        with self._get_session() as session:
            stmt = select(Payment).where(Payment.user_id == user_id, Payment.chat_id == chat_id, Payment.status == 'active').order_by(Payment.date)
            results = [p.__dict__ for p in session.scalars(stmt).all()]
            return results
    
    def get_payments_by_date(self, date: datetime.date) -> List[dict]:
        """Получить все платежи на конкретную дату (для напоминаний)"""
        with self._get_session() as session:
            stmt = select(Payment).where(Payment.date == date, Payment.status == 'active')
            results = [p.__dict__ for p in session.scalars(stmt).all()]
            return results

    def get_active_payments_by_chat(self, chat_id: int) -> List[dict]:
        """Получить все активные платежи в чате (независимо от пользователя)"""
        with self._get_session() as session:
            stmt = select(Payment).where(Payment.chat_id == chat_id, Payment.status == 'active').order_by(Payment.date)
            results = [p.__dict__ for p in session.scalars(stmt).all()]
            return results
    
    def complete_payment(self, payment_id: int):
        """Отметить платеж как выполненный"""
        with self._get_session() as session:
            stmt = select(Payment).where(Payment.id == payment_id)
            payment = session.scalar(stmt)
            if payment:
                payment.status = 'completed'
                
                # Логирование
                self._log_action(session, payment.user_id, payment_id, "complete", f"Выполнен платеж: {payment.name}")
                
                # Если повторяющийся - создаем следующий
                if payment.is_recurring:
                    next_date = get_next_occurrence(
                        payment.date,
                        payment.interval_type,
                        payment.interval_value
                    )
                    if next_date and (not payment.repeat_count or payment.repeat_count > 1):
                        new_repeat_count = payment.repeat_count - 1 if payment.repeat_count else None
                        new_payment = Payment(
                            name=payment.name,
                            user_id=payment.user_id,
                            chat_id=payment.chat_id,
                            date=next_date,
                            amount=payment.amount,
                            comment=payment.comment,
                            is_recurring=True,
                            interval_type=payment.interval_type,
                            interval_value=payment.interval_value,
                            repeat_count=new_repeat_count
                        )
                        session.add(new_payment)
                        session.commit()
                        new_id = new_payment.id
                        logger.info(f"Создан следующий платеж ID:{new_id} на основе ID:{payment_id}")
                
                session.commit()
    
    def postpone_payment(self, payment_id: int, days: int) -> datetime.date:
        """
        Перенести платеж на N дней
        """
        with self._get_session() as session:
            stmt = select(Payment).where(Payment.id == payment_id)
            payment = session.scalar(stmt)
            if payment:
                old_date = payment.date
                new_date = old_date + timedelta(days=days)
                payment.date = new_date
                
                # Логирование
                self._log_action(
                    session,
                    payment.user_id,
                    payment_id,
                    "postpone",
                    f"Перенесен платеж '{payment.name}' с {old_date} на {new_date}"
                )
                
                session.commit()
                return new_date
            return None
    
    def delete_payment(self, payment_id: int):
        """Удалить платеж"""
        with self._get_session() as session:
            stmt = select(Payment).where(Payment.id == payment_id)
            payment = session.scalar(stmt)
            if payment:
                # Логирование
                self._log_action(
                    session,
                    payment.user_id,
                    payment_id,
                    "delete",
                    f"Удален платеж: {payment.name}"
                )
                session.delete(payment)
                session.commit()
    
    def update_payment_field(self, payment_id: int, field: str, value):
        """Обновить конкретное поле платежа"""
        with self._get_session() as session:
            stmt = select(Payment).where(Payment.id == payment_id)
            payment = session.scalar(stmt)
            if payment:
                setattr(payment, field, value)
                
                # Логирование
                self._log_action(
                    session,
                    payment.user_id,
                    payment_id,
                    "update",
                    f"Обновлено поле {field} платежа '{payment.name}' на {value}"
                )
                
                session.commit()
    
    def _log_action(
        self,
        session,
        user_id: int,
        payment_id: Optional[int],
        action: str,
        details: str
    ):
        """Записать действие в лог"""
        log = Log(
            user_id=user_id,
            payment_id=payment_id,
            action=action,
            details=details
        )
        session.add(log)
        session.commit()
        logger.info(f"LOG: User {user_id}, Action: {action}, Details: {details}")
    
    def get_logs(self, user_id: Optional[int] = None, limit: int = 100) -> List[dict]:
        """
        Получить логи действий
        """
        with self._get_session() as session:
            if user_id:
                stmt = select(Log).where(Log.user_id == user_id).order_by(Log.created_at.desc()).limit(limit)
            else:
                stmt = select(Log).order_by(Log.created_at.desc()).limit(limit)
            results = [l.__dict__ for l in session.scalars(stmt).all()]
            return results
    
    def get_statistics(self, user_id: int, chat_id: int) -> dict:
        """Получить статистику по платежам пользователя в чате"""
        with self._get_session() as session:
            total = session.query(func.count(Payment.id)).filter(Payment.user_id == user_id, Payment.chat_id == chat_id).scalar()
            active = session.query(func.count(Payment.id)).filter(Payment.user_id == user_id, Payment.chat_id == chat_id, Payment.status == 'active').scalar()
            completed = session.query(func.count(Payment.id)).filter(Payment.user_id == user_id, Payment.chat_id == chat_id, Payment.status == 'completed').scalar()
            total_amount = session.query(func.sum(Payment.amount)).filter(Payment.user_id == user_id, Payment.chat_id == chat_id, Payment.status == 'active').scalar() or Decimal('0')
            
            return {
                'total': total,
                'active': active,
                'completed': completed,
                'total_amount': total_amount
            }
