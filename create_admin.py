#!/usr/bin/env python3
"""
Скрипт для создания администратора
"""

import sys
import os
from dotenv import load_dotenv

load_dotenv()

def create_admin(email, password):
    """Создать администратора"""
    from flask import Flask
    from modules.core import init_app, get_db, get_bcrypt
    
    app = Flask(__name__)
    init_app(app)
    
    with app.app_context():
        # Импортируем модели после инициализации приложения
        from modules.models.user import User
        
        db = get_db()
        bcrypt = get_bcrypt()
        
        # Проверяем, существует ли пользователь
        user = User.query.filter_by(email=email).first()
        
        if user:
            # Обновляем существующего пользователя
            password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
            user.password_hash = password_hash
            user.role = 'ADMIN'
            user.is_verified = True
            db.session.commit()
            print(f"✅ Пользователь {email} обновлен и назначен администратором")
        else:
            # Создаем нового пользователя
            # Синхронизируем sequence для user.id, если нужно
            try:
                from sqlalchemy import text
                max_id_result = db.session.execute(text('SELECT MAX(id) FROM "user"')).scalar()
                if max_id_result:
                    db.session.execute(text(f'SELECT setval(\'user_id_seq\', {max_id_result})'))
                    db.session.commit()
            except Exception as e:
                print(f"⚠️  Предупреждение при синхронизации sequence: {e}")
            
            password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
            new_user = User(
                email=email,
                password_hash=password_hash,
                role='ADMIN',
                is_verified=True
            )
            db.session.add(new_user)
            db.session.flush()
            new_user.referral_code = f"ADMIN-{new_user.id}"
            db.session.commit()
            print(f"✅ Администратор {email} успешно создан")
        
        print(f"   Email: {email}")
        print(f"   Пароль: {password}")
        print(f"   Роль: ADMIN")
        return True

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Использование: python3 create_admin.py <email> <пароль>")
        print("Пример: python3 create_admin.py admin@example.com admin123")
        sys.exit(1)
    
    email = sys.argv[1]
    password = sys.argv[2]
    
    success = create_admin(email, password)
    sys.exit(0 if success else 1)


