"""
Модель тарифа
"""
import json
from modules.core import get_db

db = get_db()

class Tariff(db.Model):
    """Тариф подписки"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    duration_days = db.Column(db.Integer, nullable=False)
    price_uah = db.Column(db.Float, nullable=False)
    price_rub = db.Column(db.Float, nullable=False)
    price_usd = db.Column(db.Float, nullable=False)
    squad_id = db.Column(db.String(128), nullable=True)  # UUID сквада (старое поле, для обратной совместимости)
    squad_ids = db.Column(db.Text, nullable=True)  # JSON массив UUID сквадов ["uuid1", "uuid2", ...]
    traffic_limit_bytes = db.Column(db.BigInteger, default=0)  # Лимит трафика (0 = безлимит)
    hwid_device_limit = db.Column(db.Integer, nullable=True, default=0)  # Лимит устройств
    tier = db.Column(db.String(20), nullable=True)  # 'basic', 'pro', 'elite'
    badge = db.Column(db.String(50), nullable=True)  # Бейдж ('top_sale', etc.)
    bonus_days = db.Column(db.Integer, nullable=True, default=0)  # Бонусные дни
    
    def get_squad_ids(self):
        """Получить список сквадов из JSON или из старого поля squad_id"""
        if self.squad_ids:
            try:
                return json.loads(self.squad_ids)
            except:
                return []
        elif self.squad_id:
            return [self.squad_id]
        return []
    
    def set_squad_ids(self, squad_ids_list):
        """Установить список сквадов в JSON"""
        if squad_ids_list and isinstance(squad_ids_list, list) and len(squad_ids_list) > 0:
            # Фильтруем пустые значения
            filtered_list = [s for s in squad_ids_list if s and str(s).strip()]
            if filtered_list:
                self.squad_ids = json.dumps(filtered_list)
            else:
                self.squad_ids = None
        else:
            self.squad_ids = None
