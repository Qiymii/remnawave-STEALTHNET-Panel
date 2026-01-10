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

with app.app_context():
    try:
        from sqlalchemy import inspect, text
        inspector = inspect(db.engine)
        
        # Проверяем существование таблицы
        tables = inspector.get_table_names()
        if 'auto_broadcast_message' not in tables:
            print("ℹ️  Таблица auto_broadcast_message не существует (будет создана при первом запросе)")
        else:
            columns = [col['name'] for col in inspector.get_columns('auto_broadcast_message')]
            
            added = []
            
            # Добавляем button_text
            if 'button_text' not in columns:
                db.session.execute(text("""
                    ALTER TABLE auto_broadcast_message 
                    ADD COLUMN button_text VARCHAR(100) NULL
                """))
                added.append('button_text')
            
            # Добавляем button_url
            if 'button_url' not in columns:
                db.session.execute(text("""
                    ALTER TABLE auto_broadcast_message 
                    ADD COLUMN button_url VARCHAR(255) NULL
                """))
                added.append('button_url')
            
            # Добавляем button_action
            if 'button_action' not in columns:
                db.session.execute(text("""
                    ALTER TABLE auto_broadcast_message 
                    ADD COLUMN button_action VARCHAR(50) NULL
                """))
                added.append('button_action')
            
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
            db.session.rollback()
            raise




