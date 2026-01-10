#!/usr/bin/env python3
"""
Скрипт для добавления таблиц казино (Колесо Фортуны)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.core import get_db, get_app

app = get_app()
db = get_db()

with app.app_context():
    try:
        from sqlalchemy import inspect, text
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        
        created = []
        
        # Создаём таблицу casino_game
        if 'casino_game' not in tables:
            db.session.execute(text("""
                CREATE TABLE casino_game (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES "user"(id),
                    bet_days INTEGER NOT NULL,
                    multiplier FLOAT NOT NULL,
                    win_days INTEGER NOT NULL,
                    balance_before INTEGER NOT NULL,
                    balance_after INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            db.session.execute(text("""
                CREATE INDEX idx_casino_game_user_id ON casino_game(user_id)
            """))
            db.session.execute(text("""
                CREATE INDEX idx_casino_game_created_at ON casino_game(created_at)
            """))
            created.append('casino_game')
        
        # Создаём таблицу casino_stats
        if 'casino_stats' not in tables:
            db.session.execute(text("""
                CREATE TABLE casino_stats (
                    id SERIAL PRIMARY KEY,
                    total_games INTEGER DEFAULT 0,
                    total_bet_days INTEGER DEFAULT 0,
                    total_win_days INTEGER DEFAULT 0,
                    total_lost_days INTEGER DEFAULT 0,
                    house_profit_days INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            # Создаём начальную запись статистики
            db.session.execute(text("""
                INSERT INTO casino_stats (total_games, total_bet_days, total_win_days, total_lost_days, house_profit_days)
                VALUES (0, 0, 0, 0, 0)
            """))
            created.append('casino_stats')
        
        if created:
            db.session.commit()
            print(f"✅ Таблицы казино созданы: {', '.join(created)}")
        else:
            print("ℹ️  Таблицы казино уже существуют")
            
    except Exception as e:
        error_msg = str(e).lower()
        if 'already exists' in error_msg or 'существует' in error_msg:
            print("ℹ️  Таблицы казино уже существуют")
        else:
            print(f"❌ Ошибка при создании таблиц: {e}")
            db.session.rollback()
            raise




