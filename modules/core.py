"""
Центральный модуль для предоставления доступа к основному экземпляру Flask
и другим общим ресурсам.
"""

from flask import Flask
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_caching import Cache
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_cors import CORS
from flask_mail import Mail
from cryptography.fernet import Fernet
import os
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Основной экземпляр Flask (будет инициализирован в app.py)
app = None

# Расширения Flask
db = None
bcrypt = None
fernet = None
mail = None
cache = None
limiter = None

def init_app(flask_app):
    """
    Инициализация основного экземпляра Flask и всех расширений.
    Этот метод должен быть вызван из app.py.
    """
    global app, db, bcrypt, fernet, mail, cache, limiter

    app = flask_app

    # Конфигурация Flask
    app.config['JWT_SECRET_KEY'] = os.getenv("JWT_SECRET_KEY")
    
    # Конфигурация базы данных (PostgreSQL или SQLite)
    database_url = os.getenv("DATABASE_URL")
    use_postgresql = False
    
    if database_url:
        # PostgreSQL из переменной окружения
        # Проверяем доступность PostgreSQL
        try:
            from sqlalchemy import create_engine, text
            test_engine = create_engine(database_url, connect_args={"connect_timeout": 2})
            with test_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            app.config['SQLALCHEMY_DATABASE_URI'] = database_url
            use_postgresql = True
            print("✅ База данных: PostgreSQL (из DATABASE_URL)")
        except Exception as e:
            # PostgreSQL недоступен, используем SQLite
            print(f"⚠️  PostgreSQL недоступен ({str(e)[:100]}), используем SQLite")
            app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///stealthnet.db'
    elif os.getenv("DB_TYPE", "").lower() == "postgresql" or os.getenv("DB_TYPE", "").lower() == "postgres":
        # PostgreSQL из отдельных переменных
        db_host = os.getenv("DB_HOST", "localhost")
        db_port = os.getenv("DB_PORT", "5432")
        db_name = os.getenv("DB_NAME", "stealthnet")
        db_user = os.getenv("DB_USER", "stealthnet")
        db_password = os.getenv("DB_PASSWORD", "")
        
        if db_password:
            database_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        else:
            database_url = f"postgresql://{db_user}@{db_host}:{db_port}/{db_name}"
        
        # Проверяем доступность PostgreSQL
        try:
            from sqlalchemy import create_engine, text
            test_engine = create_engine(database_url, connect_args={"connect_timeout": 2})
            with test_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            app.config['SQLALCHEMY_DATABASE_URI'] = database_url
            use_postgresql = True
            print(f"✅ База данных: PostgreSQL ({db_host}:{db_port}/{db_name})")
        except Exception as e:
            # PostgreSQL недоступен, используем SQLite
            print(f"⚠️  PostgreSQL недоступен ({str(e)[:100]}), используем SQLite")
            app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///stealthnet.db'
    else:
        # SQLite (по умолчанию для обратной совместимости)
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///stealthnet.db'
        print("✅ База данных: SQLite (stealthnet.db)")
    
    # Сохраняем флаг использования PostgreSQL для дальнейшей проверки миграции
    app.config['USE_POSTGRESQL'] = use_postgresql
    
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['FERNET_KEY'] = os.getenv("FERNET_KEY").encode() if os.getenv("FERNET_KEY") else None

    # Инициализация расширений
    db = SQLAlchemy(app)
    bcrypt = Bcrypt(app)
    fernet = Fernet(app.config['FERNET_KEY']) if app.config.get('FERNET_KEY') else None

    # Конфигурация почты
    app.config['MAIL_SERVER'] = os.getenv("MAIL_SERVER")
    app.config['MAIL_PORT'] = int(os.getenv("MAIL_PORT", 465))
    app.config['MAIL_USE_TLS'] = False
    app.config['MAIL_USE_SSL'] = True
    app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME")
    app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD")
    # Устанавливаем отправителя только если MAIL_USERNAME настроен
    if app.config['MAIL_USERNAME']:
        app.config['MAIL_DEFAULT_SENDER'] = ('StealthNET', app.config['MAIL_USERNAME'])
    else:
        app.config['MAIL_DEFAULT_SENDER'] = ('StealthNET', 'noreply@stealthnet.app')

    mail = Mail(app)
    
    # Конфигурация кэширования (Redis, FileSystemCache или null)
    cache_type = os.getenv("CACHE_TYPE", "null").lower()
    
    if cache_type == "redis":
        # Redis кэширование (рекомендуется для продакшн)
        try:
            redis_host = os.getenv("REDIS_HOST", "localhost")
            redis_port = int(os.getenv("REDIS_PORT", 6379))
            redis_db = int(os.getenv("REDIS_DB", 0))
            redis_password = os.getenv("REDIS_PASSWORD", None)
            
            # Формируем URL для Redis
            if redis_password:
                redis_url = f"redis://:{redis_password}@{redis_host}:{redis_port}/{redis_db}"
            else:
                redis_url = f"redis://{redis_host}:{redis_port}/{redis_db}"
            
            app.config['CACHE_TYPE'] = 'RedisCache'
            app.config['CACHE_REDIS_URL'] = redis_url
            app.config['CACHE_DEFAULT_TIMEOUT'] = int(os.getenv("CACHE_DEFAULT_TIMEOUT", 300))  # 5 минут по умолчанию
            
            # Проверяем подключение к Redis напрямую перед инициализацией Cache
            import redis
            test_redis = redis.Redis(host=redis_host, port=redis_port, db=redis_db, password=redis_password, socket_connect_timeout=2, decode_responses=False)
            test_redis.ping()
            
            # Инициализируем кэш после проверки подключения
            cache = Cache()
            cache.init_app(app)
            
            # Проверяем работу кэша
            try:
                cache.set('test', 'value', timeout=1)
                test_value = cache.get('test')
                if test_value == 'value':
                    print(f"✅ Кэширование: Redis ({redis_host}:{redis_port}, DB {redis_db})")
                else:
                    raise Exception("Cache test failed")
            except Exception as cache_error:
                raise Exception(f"Cache test failed: {cache_error}")
        except Exception as e:
            # Если Redis недоступен, используем FileSystemCache
            print(f"⚠️  Redis недоступен ({str(e)[:100]}), используем FileSystemCache")
            cache_dir = os.path.join(app.instance_path, 'cache')
            os.makedirs(cache_dir, exist_ok=True)
            app.config['CACHE_TYPE'] = 'FileSystemCache'
            app.config['CACHE_DIR'] = cache_dir
            app.config['CACHE_DEFAULT_TIMEOUT'] = int(os.getenv("CACHE_DEFAULT_TIMEOUT", 300))
            print(f"✅ Кэширование: FileSystemCache ({cache_dir})")
    elif cache_type == "filesystem":
        # FileSystemCache (как в старом app.py)
        cache_dir = os.path.join(app.instance_path, 'cache')
        os.makedirs(cache_dir, exist_ok=True)
        app.config['CACHE_TYPE'] = 'FileSystemCache'
        app.config['CACHE_DIR'] = cache_dir
        app.config['CACHE_DEFAULT_TIMEOUT'] = int(os.getenv("CACHE_DEFAULT_TIMEOUT", 300))
        
        print(f"✅ Кэширование: FileSystemCache ({cache_dir})")
    else:
        # Null cache (отключено) - для разработки
        app.config['CACHE_TYPE'] = 'null'
        print("⚠️  Кэширование: отключено (null cache)")
    
    cache = Cache(app)
    limiter = Limiter(get_remote_address, app=app, default_limits=["2000 per day", "500 per hour"], storage_uri="memory://")

    # CORS
    # Временно отключаем CORS для отладки
    # CORS(app, resources={r"/api/.*": {
    #     "origins": [
    #         "http://localhost:5000",
    #         "http://127.0.0.1:5000",
    #         "http://localhost:5001",
    #         "http://127.0.0.1:5001",
    #         os.getenv("YOUR_SERVER_IP_OR_DOMAIN", ""),
    #         "https://stealthnet.app",
    #         "http://stealthnet.app"
    #     ]
    # }})

def get_app():
    """Возвращает основной экземпляр Flask"""
    if app is None:
        raise RuntimeError("Flask app not initialized. Call init_app() first.")
    return app

def get_db():
    """Возвращает экземпляр SQLAlchemy"""
    if db is None:
        raise RuntimeError("Database not initialized. Call init_app() first.")
    return db

def get_bcrypt():
    """Возвращает экземпляр Bcrypt"""
    if bcrypt is None:
        raise RuntimeError("Bcrypt not initialized. Call init_app() first.")
    return bcrypt

def get_fernet():
    """Возвращает экземпляр Fernet"""
    return fernet

def get_mail():
    """Возвращает экземпляр Mail"""
    if mail is None:
        raise RuntimeError("Mail not initialized. Call init_app() first.")
    return mail

def get_cache():
    """Возвращает экземпляр Cache"""
    if cache is None:
        raise RuntimeError("Cache not initialized. Call init_app() first.")
    return cache

def get_limiter():
    """Возвращает экземпляр Limiter"""
    if limiter is None:
        raise RuntimeError("Limiter not initialized. Call init_app() first.")
    return limiter