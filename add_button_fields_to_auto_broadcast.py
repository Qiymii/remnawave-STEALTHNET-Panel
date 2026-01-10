#!/usr/bin/env python3
"""
Скрипт для добавления полей кнопок в таблицу auto_broadcast_message
Поля: button_text, button_url, button_action
Используются для добавления inline кнопок к автоматическим рассылкам в Telegram
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.core import get_db, get_app

app = get_app()
db = get_db()

def add_button_fields():
    """Добавить поля кнопок в таблицу auto_broadcast_message"""
    try:
        from sqlalchemy import inspect, text
        from sqlalchemy.exc import ProgrammingError, OperationalError
        
        inspector = inspect(db.engine)
        
        # Определяем тип базы данных
        is_postgresql = 'postgresql' in str(db.engine.url).lower()
        is_sqlite = 'sqlite' in str(db.engine.url).lower()
        
        # Проверяем существование таблицы
        tables = inspector.get_table_names()
        if 'auto_broadcast_message' not in tables:
            print("ℹ️  Таблица auto_broadcast_message не существует (будет создана при первом запросе)")
            return
        
        columns = [col['name'] for col in inspector.get_columns('auto_broadcast_message')]
        
        added = []
        
        # Добавляем button_text
        if 'button_text' not in columns:
            try:
                db.session.execute(text("""
                    ALTER TABLE auto_broadcast_message 
                    ADD COLUMN button_text VARCHAR(100) NULL
                """))
                added.append('button_text')
            except (ProgrammingError, OperationalError) as e:
                error_msg = str(e).lower()
                if 'already exists' in error_msg or 'существует' in error_msg or 'duplicate' in error_msg or ('column' in error_msg and 'already' in error_msg) or 'уже существует' in error_msg:
                    print("ℹ️  Поле button_text уже существует (возможно добавлено параллельно)")
                else:
                    print(f"⚠️  Ошибка при добавлении button_text: {e}")
                    raise
        
        # Добавляем button_url
        if 'button_url' not in columns:
            try:
                db.session.execute(text("""
                    ALTER TABLE auto_broadcast_message 
                    ADD COLUMN button_url VARCHAR(255) NULL
                """))
                added.append('button_url')
            except (ProgrammingError, OperationalError) as e:
                error_msg = str(e).lower()
                if 'already exists' in error_msg or 'существует' in error_msg or 'duplicate' in error_msg or ('column' in error_msg and 'already' in error_msg) or 'уже существует' in error_msg:
                    print("ℹ️  Поле button_url уже существует (возможно добавлено параллельно)")
                else:
                    print(f"⚠️  Ошибка при добавлении button_url: {e}")
                    raise
        
        # Добавляем button_action
        if 'button_action' not in columns:
            try:
                db.session.execute(text("""
                    ALTER TABLE auto_broadcast_message 
                    ADD COLUMN button_action VARCHAR(50) NULL
                """))
                added.append('button_action')
            except (ProgrammingError, OperationalError) as e:
                error_msg = str(e).lower()
                if 'already exists' in error_msg or 'существует' in error_msg or 'duplicate' in error_msg or ('column' in error_msg and 'already' in error_msg) or 'уже существует' in error_msg:
                    print("ℹ️  Поле button_action уже существует (возможно добавлено параллельно)")
                else:
                    print(f"⚠️  Ошибка при добавлении button_action: {e}")
                    raise
        
        if added:
            db.session.commit()
            print(f"✅ Поля {', '.join(added)} добавлены в таблицу auto_broadcast_message")
        else:
            print("ℹ️  Все поля кнопок уже существуют в таблице auto_broadcast_message")
                
    except Exception as e:
        error_msg = str(e).lower()
        if 'already exists' in error_msg or 'существует' in error_msg or 'duplicate' in error_msg:
            print("ℹ️  Поля кнопок уже существуют в таблице auto_broadcast_message")
        else:
            print(f"❌ Ошибка при добавлении полей: {e}")
            import traceback
            traceback.print_exc()
            db.session.rollback()
            # Не поднимаем исключение, чтобы не прервать другие миграции

# Выполняем миграцию в контексте приложения
with app.app_context():
    add_button_fields()




