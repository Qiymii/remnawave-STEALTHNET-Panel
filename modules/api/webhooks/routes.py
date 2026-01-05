"""
API вебхуков платежных систем

- POST /api/webhook/heleket - Heleket webhook
- POST /api/webhook/yookassa - YooKassa webhook
- POST /api/webhook/telegram - Telegram Stars webhook
- POST /api/webhook/telegram-stars - Telegram Stars webhook (alt)
- POST /api/webhook/freekassa - FreeKassa webhook
- POST /api/webhook/robokassa - Robokassa webhook
"""

from flask import request, jsonify
from datetime import datetime, timezone, timedelta
import requests
import json
import os
import threading

from modules.core import get_app, get_db, get_cache, get_fernet
from modules.models.payment import Payment, PaymentSetting
from modules.models.user import User
from modules.models.tariff import Tariff
from modules.models.promo import PromoCode
from modules.models.referral import ReferralSetting
from modules.currency import convert_to_usd

app = get_app()
db = get_db()
cache = get_cache()

BOT_API_URL = os.getenv("BOT_API_URL", "")
BOT_API_TOKEN = os.getenv("BOT_API_TOKEN", "")


def add_referral_commission(user, amount_usd, is_tariff_purchase=True):
    """
    Начисляет реферальную комиссию рефереру пользователя
    
    Args:
        user: Пользователь, который совершил покупку/пополнение
        amount_usd: Сумма в USD
        is_tariff_purchase: True если покупка тарифа, False если пополнение баланса
    """
    try:
        # Проверяем тип реферальной системы
        referral_settings = ReferralSetting.query.first()
        if not referral_settings:
            return
        
        # Если система на днях, не начисляем проценты
        if referral_settings.referral_type != 'PERCENT':
            return
        
        # Проверяем наличие реферера
        if not user.referrer_id:
            return
        
        referrer = db.session.get(User, user.referrer_id)
        if not referrer:
            return
        
        # Получаем процент реферала (индивидуальный или дефолтный)
        referral_percent = referrer.referral_percent if referrer.referral_percent else referral_settings.default_referral_percent
        
        # Вычисляем комиссию
        commission_usd = (amount_usd * referral_percent) / 100.0
        
        # Начисляем на баланс реферера
        current_balance = float(referrer.balance) if referrer.balance else 0.0
        referrer.balance = current_balance + commission_usd
        
        print(f"[REFERRAL] Начислено {commission_usd:.2f} USD ({referral_percent}%) рефереру {referrer.id} за покупку пользователя {user.id}")
        
    except Exception as e:
        print(f"[REFERRAL] Ошибка начисления комиссии: {e}")
        import traceback
        traceback.print_exc()


def get_remnawave_headers(additional_headers=None):
    headers = {}
    cookies = {}
    ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")
    if ADMIN_TOKEN:
        headers["Authorization"] = f"Bearer {ADMIN_TOKEN}"
    REMNAWAVE_COOKIES_STR = os.getenv("REMNAWAVE_COOKIES", "")
    if REMNAWAVE_COOKIES_STR:
        try:
            cookies = json.loads(REMNAWAVE_COOKIES_STR)
        except:
            pass
    if additional_headers:
        headers.update(additional_headers)
    return headers, cookies


def decrypt_key(key):
    fernet = get_fernet()
    if not key or not fernet:
        return ""
    try:
        return fernet.decrypt(key).decode('utf-8')
    except:
        return ""


def sync_subscription_to_bot(app_context, remnawave_uuid):
    """Синхронизация подписки в бота"""
    with app_context:
        try:
            if not BOT_API_URL or not BOT_API_TOKEN:
                return
            bot_api_url = BOT_API_URL.rstrip('/')
            requests.post(
                f"{bot_api_url}/remnawave/sync/from-panel",
                headers={"X-API-Key": BOT_API_TOKEN, "Content-Type": "application/json"},
                json={},
                timeout=60
            )
        except Exception as e:
            print(f"Background sync error: {e}")


def process_successful_payment(payment, user, tariff):
    """Обработка успешного платежа"""
    API_URL = os.getenv("API_URL")
    ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")
    DEFAULT_SQUAD_ID = os.getenv("DEFAULT_SQUAD_ID")
    
    headers = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
    
    try:
        resp = requests.get(f"{API_URL}/api/users/{user.remnawave_uuid}", headers=headers)
        if resp.status_code != 200:
            print(f"Failed to get user data: {resp.status_code}")
            return False
            
        user_data = resp.json().get('response', {})
        current_expire = user_data.get('expireAt')
        current_squads = user_data.get('activeInternalSquads', [])
        
        if current_expire:
            # Обработка формата с 'Z'
            if isinstance(current_expire, str) and current_expire.endswith('Z'):
                current_expire = current_expire[:-1] + '+00:00'
            current_expire_dt = datetime.fromisoformat(current_expire)
            if current_expire_dt.tzinfo is None:
                current_expire_dt = current_expire_dt.replace(tzinfo=timezone.utc)
            new_expire_dt = max(datetime.now(timezone.utc), current_expire_dt) + timedelta(days=tariff.duration_days)
        else:
            new_expire_dt = datetime.now(timezone.utc) + timedelta(days=tariff.duration_days)
        
        # Получаем список сквадов из тарифа
        squad_ids = []
        if hasattr(tariff, 'get_squad_ids'):
            squad_ids = tariff.get_squad_ids()
        elif hasattr(tariff, 'squad_ids') and tariff.squad_ids:
            try:
                import json
                squad_ids = json.loads(tariff.squad_ids) if isinstance(tariff.squad_ids, str) else tariff.squad_ids
            except:
                squad_ids = []
        
        # Если сквады не указаны, используем дефолтный
        if not squad_ids:
            if tariff.squad_id:
                squad_ids = [tariff.squad_id]
            else:
                squad_ids = [DEFAULT_SQUAD_ID] if DEFAULT_SQUAD_ID else []
        
        patch_payload = {
            "uuid": user.remnawave_uuid,
            "expireAt": new_expire_dt.isoformat(),
            "activeInternalSquads": squad_ids
        }
        
        if tariff.traffic_limit_bytes and tariff.traffic_limit_bytes > 0:
            patch_payload["trafficLimitBytes"] = tariff.traffic_limit_bytes
            patch_payload["trafficLimitStrategy"] = "NO_RESET"
        
        h, c = get_remnawave_headers({"Content-Type": "application/json"})
        patch_resp = requests.patch(f"{API_URL}/api/users", headers=h, cookies=c, json=patch_payload)
        
        if not patch_resp.ok:
            print(f"Failed to update user: {patch_resp.status_code}")
            return False
        
        # Списываем промокод
        if payment.promo_code_id:
            promo = db.session.get(PromoCode, payment.promo_code_id)
            if promo and promo.uses_left > 0:
                promo.uses_left -= 1
        
        payment.status = 'PAID'
        db.session.commit()
        
        # Начисляем реферальную комиссию
        amount_usd = convert_to_usd(payment.amount, payment.currency)
        add_referral_commission(user, amount_usd, is_tariff_purchase=True)
        db.session.commit()
        
        cache.delete(f'live_data_{user.remnawave_uuid}')
        cache.delete(f'nodes_{user.remnawave_uuid}')
        cache.delete('all_live_users_map')
        
        # Отправляем уведомление админам
        try:
            from modules.notifications import notify_payment
            notify_payment(payment, user, tariff, is_balance_topup=False)
        except Exception as e:
            print(f"Error sending payment notification: {e}")
        
        # Отправляем уведомление пользователю в бот
        try:
            from modules.notifications import send_user_payment_notification_async
            send_user_payment_notification_async(user, is_successful=True, tariff_name=tariff.name, is_balance_topup=False, payment_order_id=payment.order_id, payment=payment)
        except Exception as e:
            print(f"Error sending user payment notification: {e}")
        
        # Синхронизация с ботом
        if BOT_API_URL and BOT_API_TOKEN:
            threading.Thread(
                target=sync_subscription_to_bot,
                args=(app.app_context(), user.remnawave_uuid),
                daemon=True
            ).start()
        
        return True
        
    except Exception as e:
        print(f"Error processing payment: {e}")
        return False


# ============================================================================
# WEBHOOKS
# ============================================================================

@app.route('/api/webhook/heleket', methods=['POST'])
def heleket_webhook():
    """Heleket webhook"""
    try:
        data = request.json
        print(f"[HELEKET] Received: {json.dumps(data, indent=2)}")
        
        order_id = data.get('order_id')
        status = data.get('status')
        
        if not order_id or not status:
            return jsonify({"status": "error", "message": "Missing parameters"}), 400
        
        payment = Payment.query.filter_by(order_id=order_id).first()
        if not payment:
            return jsonify({"status": "error", "message": "Payment not found"}), 404
        
        payment.status = status.upper()
        payment.payment_system_id = data.get('payment_id')
        db.session.commit()
        
        if status.upper() == 'PAID':
            user = User.query.get(payment.user_id)
            tariff = Tariff.query.get(payment.tariff_id)
            
            if user and tariff:
                process_successful_payment(payment, user, tariff)
        
        return jsonify({"status": "success"}), 200
        
    except Exception as e:
        print(f"[HELEKET] Error: {e}")
        return jsonify({"status": "error", "message": str(e)[:200]}), 500


@app.route('/api/webhook/yookassa', methods=['GET', 'POST'])
def yookassa_webhook():
    """YooKassa webhook"""
    # YooKassa может отправлять GET запрос для проверки доступности webhook
    if request.method == 'GET':
        return jsonify({"status": "ok", "message": "YooKassa webhook is available"}), 200
    
    try:
        data = request.json
        print(f"[YOOKASSA] 📥 Webhook received: {json.dumps(data, indent=2, ensure_ascii=False)}")
        
        # YooKassa может отправлять разные типы событий
        event_type = data.get('event', '')
        object_data = data.get('object')
        
        if not object_data:
            print(f"[YOOKASSA] ❌ No object data in webhook")
            return jsonify({"status": "error", "message": "No object data"}), 400
        
        # Обработка событий возврата (refund.succeeded)
        if event_type == 'refund.succeeded':
            # Для возвратов ищем платеж по payment_id из объекта возврата
            payment_id = object_data.get('payment_id')
            if not payment_id:
                print(f"[YOOKASSA] ❌ Missing payment_id in refund object")
                return jsonify({"status": "error", "message": "Missing payment_id in refund"}), 400
            
            # Ищем платеж по payment_system_id (который равен payment_id из YooKassa)
            payment = Payment.query.filter_by(payment_system_id=payment_id).first()
            if not payment:
                print(f"[YOOKASSA] ⚠️ Payment not found for refund payment_id: {payment_id} (ignoring)")
                # Возвращаем успех, чтобы YooKassa не повторял запрос
                return jsonify({"status": "success", "message": "Refund processed (payment not found)"}), 200
            
            # Обрабатываем возврат только если платеж был успешным
            if payment.status != 'PAID':
                print(f"[YOOKASSA] ⚠️ Payment {payment_id} is not PAID (status={payment.status}), skipping refund")
                return jsonify({"status": "success", "message": "Refund ignored (payment not paid)"}), 200
            
            user = User.query.get(payment.user_id)
            if not user:
                print(f"[YOOKASSA] ⚠️ User not found for refund payment {payment_id} (ignoring)")
                return jsonify({"status": "success", "message": "Refund processed (user not found)"}), 200
            
            refund_amount = float(object_data.get('amount', {}).get('value', 0))
            refund_currency = object_data.get('amount', {}).get('currency', 'RUB')
            
            print(f"[YOOKASSA] 🔄 Processing refund: payment_id={payment_id}, amount={refund_amount} {refund_currency}, user_id={user.id}")
            
            # Откатываем изменения
            if payment.tariff_id is None:
                # Это было пополнение баланса - вычитаем сумму
                current_balance_usd = float(user.balance) if user.balance else 0.0
                refund_amount_usd = convert_to_usd(refund_amount, refund_currency)
                new_balance = max(0.0, current_balance_usd - refund_amount_usd)  # Не даем балансу уйти в минус
                user.balance = new_balance
                payment.status = 'REFUNDED'
                db.session.commit()
                
                cache.delete(f'live_data_{user.remnawave_uuid}')
                cache.delete('all_live_users_map')
                
                print(f"[YOOKASSA] ✅ Balance refund processed: user_id={user.id}, refund={refund_amount_usd} USD, new_balance={new_balance} USD")
            else:
                # Это была покупка тарифа - отменяем тариф (но не трогаем баланс, так как это возврат платежа)
                payment.status = 'REFUNDED'
                db.session.commit()
                
                # TODO: Можно добавить логику отмены тарифа через RemnaWave API, если нужно
                print(f"[YOOKASSA] ✅ Tariff purchase refunded: user_id={user.id}, tariff_id={payment.tariff_id}")
            
            return jsonify({"status": "success"}), 200
        
        # Для обычных платежей получаем order_id из metadata
        metadata = object_data.get('metadata', {})
        order_id = metadata.get('order_id')
        status = object_data.get('status', '').lower()
        
        print(f"[YOOKASSA] 🔍 Parsed: event={event_type}, order_id={order_id}, status={status}")
        
        if not order_id:
            print(f"[YOOKASSA] ❌ Missing order_id in metadata: {metadata}")
            # Для событий payment.succeeded пробуем найти по payment_system_id
            if event_type == 'payment.succeeded':
                payment_system_id = object_data.get('id')
                if payment_system_id:
                    payment = Payment.query.filter_by(payment_system_id=payment_system_id).first()
                    if payment:
                        print(f"[YOOKASSA] ✅ Found payment by payment_system_id: {payment_system_id}")
                        order_id = payment.order_id  # Используем order_id из найденного платежа
                    else:
                        print(f"[YOOKASSA] ❌ Payment not found by payment_system_id: {payment_system_id}")
                        return jsonify({"status": "error", "message": "Payment not found"}), 404
                else:
                    return jsonify({"status": "error", "message": "Missing order_id in metadata"}), 400
            else:
                return jsonify({"status": "error", "message": "Missing order_id in metadata"}), 400
        
        if not status:
            print(f"[YOOKASSA] ❌ Missing status in object")
            return jsonify({"status": "error", "message": "Missing status"}), 400
        
        payment = Payment.query.filter_by(order_id=order_id).first()
        if not payment:
            print(f"[YOOKASSA] ❌ Payment not found for order_id: {order_id}")
            # Попробуем найти по payment_system_id
            payment_id = object_data.get('id')
            if payment_id:
                payment = Payment.query.filter_by(payment_system_id=payment_id).first()
                if payment:
                    print(f"[YOOKASSA] ✅ Found payment by payment_system_id: {payment_id}")
            if not payment:
                return jsonify({"status": "error", "message": "Payment not found"}), 404
        
        print(f"[YOOKASSA] 💳 Payment found: id={payment.id}, user_id={payment.user_id}, tariff_id={payment.tariff_id}, current_status={payment.status}")
        
        # Проверяем, не был ли платеж уже обработан (до изменения статуса)
        if payment.status == 'PAID':
            print(f"[YOOKASSA] ⚠️ Payment {order_id} already processed (status=PAID)")
            return jsonify({"status": "success", "message": "Payment already processed"}), 200
        
        # Сохраняем payment_system_id (ID платежа в YooKassa)
        payment_system_id = object_data.get('id')
        if payment_system_id:
            payment.payment_system_id = payment_system_id
            db.session.commit()
            print(f"[YOOKASSA] 💾 Saved payment_system_id: {payment_system_id}")
        
        # YooKassa отправляет статус 'succeeded' для успешных платежей
        # Также обрабатываем статус 'succeeded' из события 'payment.succeeded'
        if status == 'succeeded':
            user = User.query.get(payment.user_id)
            if not user:
                print(f"[YOOKASSA] User not found for payment {order_id}")
                return jsonify({"status": "error", "message": "User not found"}), 404
            
            print(f"[YOOKASSA] Processing payment: order_id={order_id}, user_id={user.id}, tariff_id={payment.tariff_id}, amount={payment.amount} {payment.currency}")
            
            # Если это пополнение баланса (tariff_id == None)
            if payment.tariff_id is None:
                current_balance_usd = float(user.balance) if user.balance else 0.0
                amount_usd = convert_to_usd(payment.amount, payment.currency)
                new_balance = current_balance_usd + amount_usd
                user.balance = new_balance
                payment.status = 'PAID'
                db.session.commit()
                
                # Начисляем реферальную комиссию
                add_referral_commission(user, amount_usd, is_tariff_purchase=False)
                db.session.commit()
                
                cache.delete(f'live_data_{user.remnawave_uuid}')
                cache.delete('all_live_users_map')
                
                # Отправляем уведомление админам
                try:
                    from modules.notifications import notify_payment
                    notify_payment(payment, user, is_balance_topup=True)
                except Exception as e:
                    print(f"Error sending payment notification: {e}")
                
                # Отправляем уведомление пользователю в бот
                try:
                    from modules.notifications import send_user_payment_notification_async
                    send_user_payment_notification_async(user, is_successful=True, is_balance_topup=True, payment=payment)
                except Exception as e:
                    print(f"Error sending user payment notification: {e}")
                
                print(f"[YOOKASSA] ✅ Balance top-up successful: user_id={user.id}, amount={amount_usd} USD, new_balance={new_balance} USD")
            else:
                # Покупка тарифа
                tariff = Tariff.query.get(payment.tariff_id)
                if tariff:
                    # process_successful_payment уже отправляет уведомления админам и пользователю
                    success = process_successful_payment(payment, user, tariff)
                    if success:
                        print(f"[YOOKASSA] ✅ Tariff purchase successful: user_id={user.id}, tariff_id={tariff.id}, tariff_name={tariff.name}")
                    else:
                        print(f"[YOOKASSA] ❌ Failed to process tariff purchase: user_id={user.id}, tariff_id={tariff.id}")
                else:
                    print(f"[YOOKASSA] ❌ Warning: Tariff not found for payment {payment.order_id}, tariff_id={payment.tariff_id}")
        else:
            # Логируем другие статусы для отладки
            print(f"[YOOKASSA] Payment status: {status} (not processing, waiting for 'succeeded')")
        
        return jsonify({"status": "success"}), 200
        
    except Exception as e:
        print(f"[YOOKASSA] Error: {e}")
        return jsonify({"status": "error", "message": str(e)[:200]}), 500


@app.route('/api/webhook/telegram', methods=['POST'])
@app.route('/api/webhook/telegram-stars', methods=['POST'])
def telegram_webhook():
    """Telegram Stars webhook"""
    try:
        update = request.json
        if not update:
            return jsonify({"ok": True}), 200
        
        # PreCheckoutQuery
        if 'pre_checkout_query' in update:
            pre_checkout = update['pre_checkout_query']
            order_id = pre_checkout.get('invoice_payload')
            query_id = pre_checkout.get('id')
            
            s = PaymentSetting.query.first()
            bot_token = decrypt_key(s.telegram_bot_token) if s else None
            
            if not bot_token:
                return jsonify({"ok": True}), 200
            
            p = Payment.query.filter_by(order_id=order_id).first()
            if p and p.status == 'PENDING':
                requests.post(
                    f"https://api.telegram.org/bot{bot_token}/answerPreCheckoutQuery",
                    json={"pre_checkout_query_id": query_id, "ok": True},
                    timeout=5
                )
            else:
                requests.post(
                    f"https://api.telegram.org/bot{bot_token}/answerPreCheckoutQuery",
                    json={"pre_checkout_query_id": query_id, "ok": False, "error_message": "Payment not found"},
                    timeout=5
                )
            
            return jsonify({"ok": True}), 200
        
        # Successful payment
        if 'message' in update and 'successful_payment' in update['message']:
            successful_payment = update['message']['successful_payment']
            order_id = successful_payment.get('invoice_payload')
            
            p = Payment.query.filter_by(order_id=order_id).first()
            if not p:
                p = Payment.query.filter_by(payment_system_id=order_id).first()
            
            if not p or p.status == 'PAID':
                return jsonify({"ok": True}), 200
            
            u = db.session.get(User, p.user_id)
            if not u:
                return jsonify({"ok": True}), 200
            
        # Пополнение баланса
        if p.tariff_id is None:
            current_balance = float(u.balance) if u.balance else 0.0
            amount_usd = convert_to_usd(p.amount, p.currency)
            u.balance = current_balance + amount_usd
            p.status = 'PAID'
            db.session.commit()
            
            # Начисляем реферальную комиссию
            add_referral_commission(u, amount_usd, is_tariff_purchase=False)
            db.session.commit()
            
            # Отправляем уведомление админам
            try:
                from modules.notifications import notify_payment
                notify_payment(p, u, is_balance_topup=True)
            except Exception as e:
                print(f"Error sending payment notification: {e}")
            
            # Отправляем уведомление пользователю в бот
            try:
                from modules.notifications import send_user_payment_notification_async
                send_user_payment_notification_async(u, is_successful=True, is_balance_topup=True, payment=p)
            except Exception as e:
                print(f"Error sending user payment notification: {e}")
            
            cache.delete(f'live_data_{u.remnawave_uuid}')
            return jsonify({"ok": True}), 200
        
        # Покупка тарифа
        t = db.session.get(Tariff, p.tariff_id)
        if not t:
            return jsonify({"ok": True}), 200
        
        # process_successful_payment уже отправляет уведомление пользователю
        process_successful_payment(p, u, t)
        
        return jsonify({"ok": True}), 200
        
    except Exception as e:
        print(f"[TELEGRAM] Error: {e}")
        return jsonify({"ok": True}), 200


@app.route('/api/internal/process-telegram-payment', methods=['POST'])
def process_telegram_payment_internal():
    """Внутренний API для обработки платежей Telegram Stars от бота"""
    try:
        # Проверяем внутренний ключ (простая защита)
        internal_key = request.headers.get('X-Internal-Key')
        if internal_key != 'telegram-stars-internal':
            return jsonify({"success": False, "message": "Unauthorized"}), 401
        
        data = request.json or {}
        order_id = data.get('order_id')
        telegram_id = data.get('telegram_id')
        
        print(f"[TELEGRAM-INTERNAL] Processing payment: order_id={order_id}, telegram_id={telegram_id}")
        
        if not order_id:
            return jsonify({"success": False, "message": "Missing order_id"}), 400
        
        # Ищем платеж
        p = Payment.query.filter_by(order_id=order_id).first()
        if not p:
            p = Payment.query.filter_by(payment_system_id=order_id).first()
        
        if not p:
            print(f"[TELEGRAM-INTERNAL] Payment not found: {order_id}")
            return jsonify({"success": False, "message": "Payment not found"}), 404
        
        if p.status == 'PAID':
            return jsonify({"success": True, "message": "Платеж уже обработан"}), 200
        
        u = db.session.get(User, p.user_id)
        if not u:
            return jsonify({"success": False, "message": "User not found"}), 404
        
        # Пополнение баланса
        if p.tariff_id is None:
            current_balance = float(u.balance) if u.balance else 0.0
            amount_usd = convert_to_usd(p.amount, p.currency)
            u.balance = current_balance + amount_usd
            p.status = 'PAID'
            db.session.commit()
            
            # Начисляем реферальную комиссию
            try:
                add_referral_commission(u, amount_usd, is_tariff_purchase=False)
                db.session.commit()
            except Exception as e:
                print(f"[TELEGRAM-INTERNAL] Referral commission error: {e}")
            
            # Отправляем уведомление админам
            try:
                from modules.notifications import notify_payment
                notify_payment(p, u, is_balance_topup=True)
            except Exception as e:
                print(f"[TELEGRAM-INTERNAL] Notification error: {e}")
            
            cache.delete(f'live_data_{u.remnawave_uuid}')
            print(f"[TELEGRAM-INTERNAL] Balance topped up: user={u.id}, amount={amount_usd} USD")
            return jsonify({
                "success": True, 
                "message": f"Баланс пополнен на {p.amount} {p.currency}"
            }), 200
        
        # Покупка тарифа
        t = db.session.get(Tariff, p.tariff_id)
        if not t:
            return jsonify({"success": False, "message": "Tariff not found"}), 404
        
        # process_successful_payment обработает платеж
        try:
            process_successful_payment(p, u, t)
            print(f"[TELEGRAM-INTERNAL] Tariff activated: user={u.id}, tariff={t.name}")
            return jsonify({
                "success": True, 
                "message": f"Подписка '{t.name}' активирована!"
            }), 200
        except Exception as e:
            print(f"[TELEGRAM-INTERNAL] Tariff activation error: {e}")
            return jsonify({"success": False, "message": str(e)}), 500
        
    except Exception as e:
        print(f"[TELEGRAM-INTERNAL] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/webhook/freekassa', methods=['POST', 'GET'])
def freekassa_webhook():
    """FreeKassa webhook"""
    try:
        data = request.values.to_dict()
        print(f"[FREEKASSA] Received: {data}")
        
        order_id = data.get('MERCHANT_ORDER_ID')
        if not order_id:
            return "NO", 400
        
        payment = Payment.query.filter_by(order_id=order_id).first()
        if not payment:
            return "NO", 404
        
        if payment.status != 'PAID':
            payment.status = 'PAID'
            payment.payment_system_id = data.get('intid')
            db.session.commit()
            
            user = User.query.get(payment.user_id)
            tariff = Tariff.query.get(payment.tariff_id)
            
            if user and tariff:
                process_successful_payment(payment, user, tariff)
        
        return "YES", 200
        
    except Exception as e:
        print(f"[FREEKASSA] Error: {e}")
        return "NO", 500


@app.route('/api/webhook/robokassa', methods=['POST', 'GET'])
def robokassa_webhook():
    """Robokassa webhook"""
    try:
        data = request.values.to_dict()
        print(f"[ROBOKASSA] Received: {data}")
        
        order_id = data.get('InvId') or data.get('inv_id')
        if not order_id:
            return "NO", 400
        
        payment = Payment.query.filter_by(order_id=str(order_id)).first()
        if not payment:
            return "NO", 404
        
        if payment.status != 'PAID':
            payment.status = 'PAID'
            db.session.commit()
            
            user = User.query.get(payment.user_id)
            tariff = Tariff.query.get(payment.tariff_id)
            
            if user and tariff:
                process_successful_payment(payment, user, tariff)
        
        return f"OK{order_id}", 200
        
    except Exception as e:
        print(f"[ROBOKASSA] Error: {e}")
        return "NO", 500


def parse_iso_datetime(iso_string):
    """Парсит ISO формат даты, поддерживая как стандартный формат, так и формат с 'Z' (UTC)"""
    if not iso_string:
        raise ValueError("Empty ISO string")
    
    # Заменяем 'Z' на '+00:00' для совместимости с fromisoformat
    if iso_string.endswith('Z'):
        iso_string = iso_string[:-1] + '+00:00'
    
    return datetime.fromisoformat(iso_string)


# ============================================================================
# CRYSTALPAY WEBHOOK
# ============================================================================

@app.route('/api/webhook/crystalpay', methods=['POST'])
def crystalpay_webhook():
    """Webhook для обработки уведомлений от CrystalPay"""
    try:
        d = request.json
        if d.get('state') != 'payed':
            return jsonify({"error": False}), 200
        
        p = Payment.query.filter_by(order_id=d.get('extra')).first()
        if not p or p.status == 'PAID':
            return jsonify({"error": False}), 200
        
        u = db.session.get(User, p.user_id)
        if not u:
            return jsonify({"error": False}), 200
        
        # Если это пополнение баланса (tariff_id == None)
        if p.tariff_id is None:
            current_balance_usd = float(u.balance) if u.balance else 0.0
            amount_usd = convert_to_usd(p.amount, p.currency)
            u.balance = current_balance_usd + amount_usd
            p.status = 'PAID'
            db.session.commit()
            
            # Начисляем реферальную комиссию
            add_referral_commission(u, amount_usd, is_tariff_purchase=False)
            db.session.commit()
            
            # Отправляем уведомление админам
            try:
                from modules.notifications import notify_payment
                notify_payment(p, u, is_balance_topup=True)
            except Exception as e:
                print(f"Error sending payment notification: {e}")
            
            # Отправляем уведомление пользователю в бот
            try:
                from modules.notifications import send_user_payment_notification_async
                send_user_payment_notification_async(u, is_successful=True, is_balance_topup=True, payment=p)
            except Exception as e:
                print(f"Error sending user payment notification: {e}")
            
            cache.delete(f'live_data_{u.remnawave_uuid}')
            cache.delete('all_live_users_map')
            
            return jsonify({"error": False}), 200
        
        # Обычная покупка тарифа
        t = db.session.get(Tariff, p.tariff_id)
        if not t:
            return jsonify({"error": False}), 200
        
        # process_successful_payment уже отправляет уведомление пользователю
        process_successful_payment(p, u, t)
        
        return jsonify({"error": False}), 200
        
    except Exception as e:
        print(f"[CRYSTALPAY] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": False}), 200


# ============================================================================
# PLATEGA WEBHOOK
# ============================================================================

@app.route('/api/webhook/platega', methods=['POST'])
def platega_webhook():
    """
    Webhook для обработки уведомлений от Platega
    
    Согласно документации Platega API:
    - Endpoint должен принимать JSON-запросы
    - Всегда возвращать статус 200 OK для своевременных обновлений
    - Статусы: PENDING, CANCELED, CONFIRMED, CHARGEBACKED
    - Успешный платеж: CONFIRMED
    - Структура webhook может содержать:
      - id (UUID транзакции) - на верхнем уровне или в transaction
      - status (PENDING, CANCELED, CONFIRMED, CHARGEBACKED)
      - transaction.id или id
      - paymentDetails (amount, currency)
    """
    # Всегда возвращаем 200 OK, даже при ошибках, чтобы Platega не повторял запрос
    try:
        # Проверяем, что запрос содержит JSON
        if not request.is_json:
            # Пробуем распарсить как JSON вручную
            try:
                if request.data:
                    import json as json_lib
                    webhook_data = json_lib.loads(request.data.decode('utf-8'))
                else:
                    print("[PLATEGA] No JSON data in request")
                    return jsonify({"status": "ok"}), 200
            except Exception as parse_error:
                print(f"[PLATEGA] Failed to parse JSON: {parse_error}")
                return jsonify({"status": "ok"}), 200
        else:
            webhook_data = request.json
        
        if not webhook_data:
            print("[PLATEGA] Empty webhook data")
            return jsonify({"status": "ok"}), 200
        
        # Логируем входящий webhook для отладки
        print(f"[PLATEGA] Webhook received: {json.dumps(webhook_data, indent=2)}")
        
        # Получаем статус (может быть на верхнем уровне или в transaction)
        status = webhook_data.get('status', '')
        transaction = webhook_data.get('transaction', {})
        
        # Если статус в transaction, используем его
        if not status and transaction:
            status = transaction.get('status', '')
        
        # Нормализуем статус (документация использует верхний регистр: CONFIRMED)
        status_upper = status.upper() if status else ''
        
        # Согласно документации Platega, успешный платеж имеет статус CONFIRMED
        # Также поддерживаем старые варианты для обратной совместимости
        if status_upper not in ['CONFIRMED', 'PAID', 'SUCCESS', 'COMPLETED']:
            print(f"[PLATEGA] Ignoring status: {status_upper}")
            return jsonify({"status": "ok"}), 200
        
        # Получаем ID транзакции
        # Может быть на верхнем уровне (id) или в transaction (id)
        transaction_id = webhook_data.get('id') or transaction.get('id')
        
        # Также проверяем externalId или invoiceId для обратной совместимости
        external_id = webhook_data.get('externalId') or transaction.get('externalId')
        invoice_id = webhook_data.get('invoiceId') or transaction.get('invoiceId')
        
        print(f"[PLATEGA] Transaction ID: {transaction_id}, External ID: {external_id}, Invoice ID: {invoice_id}")
        
        # Согласно документации Platega, проверяем статус через API для подтверждения
        # GET /transaction/{id} - проверка статуса оплаты платежа
        verified_status = None
        if transaction_id:
            try:
                from modules.models.payment import PaymentSetting, decrypt_key
                import requests
                
                settings = PaymentSetting.query.first()
                if settings:
                    platega_key = decrypt_key(getattr(settings, 'platega_api_key', None)) if settings else None
                    platega_merchant_raw = decrypt_key(getattr(settings, 'platega_merchant_id', None)) if settings else None
                    
                    if platega_key and platega_merchant_raw:
                        # Обработка Merchant ID (убираем префикс 'live_' если есть)
                        import re
                        import uuid as uuid_lib
                        platega_merchant = platega_merchant_raw.strip()
                        if platega_merchant.startswith('live_'):
                            platega_merchant = platega_merchant[5:]
                        uuid_pattern = r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
                        uuid_match = re.search(uuid_pattern, platega_merchant)
                        if uuid_match:
                            platega_merchant = uuid_match.group(0)
                        
                        # Проверяем статус через API Platega
                        api_url = f"https://app.platega.io/transaction/{transaction_id}"
                        headers = {
                            "X-MerchantId": platega_merchant,
                            "X-Secret": platega_key,
                            "Content-Type": "application/json"
                        }
                        
                        resp = requests.get(api_url, headers=headers, timeout=10)
                        if resp.status_code == 200:
                            api_data = resp.json()
                            verified_status = api_data.get('status', '').upper()
                            print(f"[PLATEGA] Verified status from API: {verified_status}, full response: {json.dumps(api_data, indent=2)}")
                        elif resp.status_code == 404:
                            print(f"[PLATEGA] Transaction {transaction_id} not found in Platega API (404)")
                        else:
                            print(f"[PLATEGA] Failed to verify status via API: {resp.status_code} - {resp.text[:200]}")
            except Exception as api_error:
                print(f"[PLATEGA] Error verifying status via API: {api_error}")
        
        # Используем проверенный статус из API, если доступен, иначе из webhook
        if verified_status:
            status_upper = verified_status
            print(f"[PLATEGA] Using verified status from API: {status_upper}")
        else:
            status_upper = status.upper() if status else ''
            print(f"[PLATEGA] Using status from webhook: {status_upper}")
        
        # Ищем платеж по transaction_id (это payment_system_id в нашей БД)
        p = None
        if transaction_id:
            p = Payment.query.filter_by(payment_system_id=str(transaction_id)).first()
        
        # Если не нашли, пробуем по externalId или invoiceId (это может быть order_id)
        if not p and external_id:
            p = Payment.query.filter_by(order_id=str(external_id)).first()
        
        if not p and invoice_id:
            p = Payment.query.filter_by(order_id=str(invoice_id)).first()
        
        if not p:
            print(f"[PLATEGA] Payment not found for transaction_id={transaction_id}, external_id={external_id}, invoice_id={invoice_id}")
            return jsonify({"status": "ok"}), 200
        
        # Если платеж уже обработан, игнорируем
        if p.status == 'PAID':
            print(f"[PLATEGA] Payment {p.order_id} already processed")
            return jsonify({"status": "ok"}), 200
        
        # Получаем пользователя и тариф
        u = db.session.get(User, p.user_id)
        t = db.session.get(Tariff, p.tariff_id) if p.tariff_id else None
        
        if not u:
            print(f"[PLATEGA] User not found for payment {p.order_id}")
            return jsonify({"status": "ok"}), 200
        
        # Если это пополнение баланса (нет тарифа), обрабатываем отдельно
        if not t:
            # Для пополнения баланса обновляем статус и пополняем баланс
            p.status = 'PAID'
            # Пополняем баланс пользователя
            u.balance = (u.balance or 0) + float(p.amount)
            db.session.commit()
            print(f"[PLATEGA] Balance topup payment {p.order_id} marked as PAID, balance updated: {u.balance}")
            return jsonify({"status": "ok"}), 200
        
        # Обрабатываем успешный платеж за тариф
        if process_successful_payment(p, u, t):
            print(f"[PLATEGA] Successfully processed payment {p.order_id}")
            return jsonify({"status": "ok"}), 200
        else:
            print(f"[PLATEGA] Failed to process payment {p.order_id}")
            return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        print(f"[PLATEGA] Error: {e}")
        import traceback
        traceback.print_exc()
        # Всегда возвращаем 200 OK с JSON ответом, чтобы Platega не повторял запрос
        # Это важно для своевременных обновлений статуса транзакций
        return jsonify({"status": "ok"}), 200


# ============================================================================
# MULENPAY WEBHOOK
# ============================================================================

@app.route('/api/webhook/mulenpay', methods=['POST'])
def mulenpay_webhook():
    """Webhook для обработки уведомлений от MulenPay"""
    try:
        webhook_data = request.json
        
        status = webhook_data.get('status', '').lower()
        order_id = webhook_data.get('order_id') or webhook_data.get('orderId')
        
        if status not in ['paid', 'success', 'completed']:
            return jsonify({}), 200
        
        if not order_id:
            return jsonify({}), 200
        
        p = Payment.query.filter_by(order_id=order_id).first()
        if not p or p.status == 'PAID':
            return jsonify({}), 200
        
        u = db.session.get(User, p.user_id)
        t = db.session.get(Tariff, p.tariff_id)
        
        if not u or not t:
            return jsonify({}), 200
        
        if process_successful_payment(p, u, t):
            return jsonify({}), 200
        else:
            return jsonify({}), 200
        
    except Exception as e:
        print(f"[MULENPAY] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({}), 200


# ============================================================================
# URLPAY WEBHOOK
# ============================================================================

@app.route('/api/webhook/urlpay', methods=['POST'])
def urlpay_webhook():
    """Webhook для обработки уведомлений от URLPay"""
    try:
        webhook_data = request.json
        
        status = webhook_data.get('status', '').lower()
        order_id = webhook_data.get('order_id') or webhook_data.get('orderId')
        
        if status not in ['paid', 'success', 'completed']:
            return jsonify({}), 200
        
        if not order_id:
            return jsonify({}), 200
        
        p = Payment.query.filter_by(order_id=order_id).first()
        if not p or p.status == 'PAID':
            return jsonify({}), 200
        
        u = db.session.get(User, p.user_id)
        t = db.session.get(Tariff, p.tariff_id)
        
        if not u or not t:
            return jsonify({}), 200
        
        if process_successful_payment(p, u, t):
            return jsonify({}), 200
        else:
            return jsonify({}), 200
        
    except Exception as e:
        print(f"[URLPAY] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({}), 200


# ============================================================================
# BTCPAYSERVER WEBHOOK
# ============================================================================

@app.route('/api/webhook/btcpayserver', methods=['POST'])
def btcpayserver_webhook():
    """Webhook для обработки уведомлений от BTCPayServer"""
    try:
        webhook_data = request.json
        
        # BTCPayServer отправляет разные типы событий
        event_type = webhook_data.get('type', '')
        
        # Нас интересуют только события оплаты
        if event_type not in ['InvoiceSettled', 'InvoiceReceivedPayment']:
            return jsonify({}), 200
        
        invoice_data = webhook_data.get('data', {})
        invoice_id = invoice_data.get('id') or invoice_data.get('invoiceId')
        
        if not invoice_id:
            return jsonify({}), 200
        
        p = Payment.query.filter_by(order_id=invoice_id).first()
        if not p or p.status == 'PAID':
            return jsonify({}), 200
        
        u = db.session.get(User, p.user_id)
        t = db.session.get(Tariff, p.tariff_id)
        
        if not u or not t:
            return jsonify({}), 200
        
        if process_successful_payment(p, u, t):
            return jsonify({}), 200
        else:
            return jsonify({}), 200
        
    except Exception as e:
        print(f"[BTCPAYSERVER] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({}), 200


# ============================================================================
# TRIBUTE WEBHOOK
# ============================================================================

@app.route('/api/webhook/tribute', methods=['POST'])
def tribute_webhook():
    """Webhook для обработки уведомлений от Tribute"""
    try:
        webhook_data = request.json
        
        status = webhook_data.get('status', '').lower()
        order_id = webhook_data.get('order_id') or webhook_data.get('orderId')
        
        if status not in ['paid', 'success', 'completed']:
            return jsonify({}), 200
        
        if not order_id:
            return jsonify({}), 200
        
        p = Payment.query.filter_by(order_id=order_id).first()
        if not p or p.status == 'PAID':
            return jsonify({}), 200
        
        u = db.session.get(User, p.user_id)
        t = db.session.get(Tariff, p.tariff_id)
        
        if not u or not t:
            return jsonify({}), 200
        
        if process_successful_payment(p, u, t):
            return jsonify({}), 200
        else:
            return jsonify({}), 200
        
    except Exception as e:
        print(f"[TRIBUTE] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({}), 200


# ============================================================================
# MONOBANK WEBHOOK
# ============================================================================

@app.route('/api/webhook/monobank', methods=['POST'])
def monobank_webhook():
    """Webhook для обработки уведомлений от Monobank"""
    try:
        webhook_data = request.json
        
        # Monobank отправляет данные в формате statementItem
        invoice_id = webhook_data.get('invoiceId') or webhook_data.get('invoice_id')
        
        if not invoice_id:
            return jsonify({}), 200
        
        p = Payment.query.filter_by(order_id=invoice_id).first()
        if not p or p.status == 'PAID':
            return jsonify({}), 200
        
        u = db.session.get(User, p.user_id)
        t = db.session.get(Tariff, p.tariff_id)
        
        if not u or not t:
            return jsonify({}), 200
        
        if process_successful_payment(p, u, t):
            return jsonify({}), 200
        else:
            return jsonify({}), 200
        
    except Exception as e:
        print(f"[MONOBANK] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({}), 200
