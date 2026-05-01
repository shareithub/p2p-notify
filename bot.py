#!/usr/bin/env python3
"""
Binance P2P Order Notifier Bot v3
- Notifikasi order baru
- Monitoring order aktif (update status tiap polling)
- Proxy toggle ON/OFF saat runtime
"""

import os
import sys
import time
import hmac
import hashlib
import requests
import logging
import threading
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode
from dotenv import load_dotenv

load_dotenv()

# ─── Konfigurasi ──────────────────────────────────────────────
BINANCE_API_KEY    = os.getenv("BINANCE_API_KEY", "")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY", "")
TELEGRAM_TOKEN     = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
POLL_INTERVAL      = int(os.getenv("POLL_INTERVAL", "10"))

# ─── Proxy ────────────────────────────────────────────────────
_PROXY_HTTP  = os.getenv("PROXY_HTTP", "")
_PROXY_HTTPS = os.getenv("PROXY_HTTPS", "")
_PROXY_DICT  = {}
if _PROXY_HTTP:  _PROXY_DICT["http"]  = _PROXY_HTTP
if _PROXY_HTTPS: _PROXY_DICT["https"] = _PROXY_HTTPS

_proxy_lock    = threading.Lock()
_proxy_enabled = False

def set_proxy(enabled: bool):
    global _proxy_enabled
    with _proxy_lock:
        _proxy_enabled = enabled

def get_proxy():
    with _proxy_lock:
        return _PROXY_DICT if _proxy_enabled and _PROXY_DICT else None

def proxy_status_str() -> str:
    with _proxy_lock:
        if not _PROXY_DICT:
            return "❌ Tidak ada proxy di .env"
        state = "🟢 ON" if _proxy_enabled else "🔴 OFF"
        host  = (_PROXY_HTTPS or _PROXY_HTTP).split("@")[-1]
        return f"{state}  ({host})"

# ─── Base URLs ────────────────────────────────────────────────
SAPI_BASE = "https://api.binance.com"
MGS_BASE  = "https://www.binance.com"
C2C_WEB   = "https://c2c.binance.com"

# ─── Logging ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ─── Status order ─────────────────────────────────────────────
ORDER_STATUS = {
    # Numeric
    "0": "⏳ Menunggu",
    "1": "💰 Belum Bayar",
    "2": "✅ Sudah Bayar",
    "3": "🔄 Proses Rilis Koin",
    "4": "🎉 Selesai",
    "5": "⚠️ Dalam Banding",
    "6": "❌ Dibatalkan",
    "7": "⏰ Kedaluwarsa",
    # String (Binance kadang kirim string bukan angka)
    "TRADING":      "💰 Belum Bayar / Aktif",
    "PAYING":       "💰 Belum Bayar",
    "PAID":         "✅ Sudah Bayar",
    "BUYER_PAYED":  "✅ Buyer Sudah Bayar",
    "BUYER_PAID":   "✅ Buyer Sudah Bayar",
    "SELLER_PAID":  "✅ Seller Sudah Bayar",
    "COMPLETED":    "🎉 Selesai",
    "CANCELLED":    "❌ Dibatalkan",
    "CANCEL":       "❌ Dibatalkan",
    "IN_APPEAL":    "⚠️ Dalam Banding",
    "APPEAL":       "⚠️ Dalam Banding",
    "APPEALING":    "⚠️ Dalam Banding",
    "EXPIRED":      "⏰ Kedaluwarsa",
    "FINISH":       "🎉 Selesai",
    "TIMEOUT":      "⏰ Kedaluwarsa",
    "RELEASING":    "🔄 Proses Rilis Koin",
}

# Status yang masih aktif (perlu dipantau terus)
ACTIVE_STATUSES = {
    "0", "1", "2", "3", "5",
    "TRADING", "PAYING", "PAID", "BUYER_PAYED", "BUYER_PAID",
    "SELLER_PAID", "RELEASING", "IN_APPEAL", "APPEAL", "APPEALING",
}

# Status final (selesai dipantau)
FINAL_STATUSES = {
    "4", "6", "7",
    "COMPLETED", "CANCELLED", "CANCEL", "EXPIRED", "FINISH", "TIMEOUT",
}

PAYMENT_ICONS = {
    "BCA": "🏦", "BNI": "🏦", "BRI": "🏦", "MANDIRI": "🏦",
    "BSI": "🏦", "CIMB": "🏦", "BTN": "🏦", "BANK": "🏦",
    "DANA": "💙", "OVO": "💜", "GOPAY": "💚", "SHOPEEPAY": "🧡",
    "LINKAJA": "❤️", "JENIUS": "💙", "FLIP": "🟦",
    "QRIS": "📱", "TRANSFER": "🏦",
}

FIAT_SYM = {
    "IDR": "Rp", "USD": "$", "EUR": "€",
    "CNY": "¥", "SGD": "S$", "MYR": "RM ",
}


# ─── Helper ───────────────────────────────────────────────────
def payment_icon(identifier: str) -> str:
    upper = (identifier or "").upper()
    for key, icon in PAYMENT_ICONS.items():
        if key in upper:
            return icon
    return "💳"

def fmt_num(val, dec=2) -> str:
    try:
        return f"{float(val):,.{dec}f}"
    except Exception:
        return str(val)

def fmt_time(ms) -> str:
    if not ms:
        return "—"
    try:
        dt  = datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)
        wib = dt + timedelta(hours=7)
        return wib.strftime("%d %b %Y  %H:%M:%S WIB")
    except Exception:
        return str(ms)

def fmt_duration(ms_start, ms_end) -> str:
    if not ms_start or not ms_end:
        return "—"
    diff   = (int(ms_end) - int(ms_start)) // 1000
    h, rem = divmod(diff, 3600)
    m, s   = divmod(rem, 60)
    if h:   return f"{h}j {m}m {s}d"
    return f"{m} menit {s} detik" if m else f"{s} detik"

def first_val(*args):
    """Ambil nilai pertama yang tidak kosong / falsy dari beberapa sumber."""
    for a in args:
        if a not in (None, "", 0, "0"):
            return a
    return None


# ─── Signing ──────────────────────────────────────────────────
def _sign(params: dict) -> str:
    return hmac.new(
        BINANCE_SECRET_KEY.encode("utf-8"),
        urlencode(params).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

def _headers() -> dict:
    return {
        "X-MBX-APIKEY": BINANCE_API_KEY,
        "User-Agent":   "binance-wallet/1.0.0 (Skill)",
        "Content-Type": "application/json",
    }

def _ts() -> int:
    return int(time.time() * 1000)


# ─── HTTP helpers ─────────────────────────────────────────────
def _get(base: str, path: str, extra: dict = {}) -> dict:
    params = {**extra, "timestamp": _ts()}
    params["signature"] = _sign(params)
    try:
        r = requests.get(f"{base}{path}", params=params,
                         headers=_headers(), proxies=get_proxy(), timeout=20)
        return r.json()
    except Exception as e:
        log.error(f"GET {path}: {e}")
        return {}

def _post(base: str, path: str, body: dict = {}) -> dict:
    params = {"timestamp": _ts()}
    params["signature"] = _sign(params)
    try:
        r = requests.post(f"{base}{path}", params=params, json=body,
                          headers=_headers(), proxies=get_proxy(), timeout=20)
        return r.json()
    except Exception as e:
        log.error(f"POST {path}: {e}")
        return {}


# ─── Fetch ────────────────────────────────────────────────────
def fetch_orders(rows: int = 20) -> list:
    data = _get(SAPI_BASE, "/sapi/v1/c2c/orderMatch/listUserOrderHistory",
                {"page": 1, "rows": rows})
    if not data:
        log.warning("fetch_orders: response kosong")
        return []

    code  = str(data.get("code", "—"))
    msg   = data.get("msg", "")
    total = data.get("total", "—")

    log.info(f"  ┌─ fetch_orders response")
    log.info(f"  │  code    : {code}")
    log.info(f"  │  msg     : {msg or '(kosong)'}")
    log.info(f"  │  total   : {total}")

    if code and code not in ("000000", "0", "200", "—"):
        log.warning(f"  └─ ❌ API error: code={code} msg={msg}")
        return []

    orders = data.get("data", [])
    if not isinstance(orders, list):
        log.warning(f"  └─ ⚠️  Format data tidak dikenal: {str(orders)[:80]}")
        return []

    log.info(f"  │  jumlah  : {len(orders)} order")
    for i, o in enumerate(orders, 1):
        no        = o.get("orderNumber", "—")
        status    = o.get("orderStatus", "—")
        trade     = o.get("tradeType", "—")
        asset     = o.get("asset", "—")
        fiat      = o.get("fiat", "—")
        amount    = o.get("amount", "—")
        total_p   = o.get("totalPrice", "—")
        unit_p    = o.get("unitPrice", "—")
        create_ms = o.get("createTime", 0)
        cp_nick   = o.get("counterPartNickName", "—")
        adv_no    = o.get("advertisementNo", "—")
        log.info(f"  │  [{i:02d}] No      : {no}")
        log.info(f"  │       Status  : {status}")
        log.info(f"  │       Type    : {trade}  Asset: {asset}  Fiat: {fiat}")
        log.info(f"  │       Amount  : {amount} {asset}  @ {unit_p}  Total: {total_p}")
        log.info(f"  │       Mitra   : {cp_nick}")
        log.info(f"  │       Iklan   : {adv_no}")
        log.info(f"  │       Masuk   : {fmt_time(create_ms)}")
        if i < len(orders):
            log.info(f"  │       ─────────────────────────────")
    log.info(f"  └─ ✅ selesai")
    return orders

def fetch_order_detail(order_no: str) -> dict:
    """Coba dua endpoint, kembalikan detail terlengkap."""
    log.info(f"  ┌─ fetch_order_detail: {order_no}")
    # Coba kedua nama field karena Binance tidak konsisten
    for method, base, path, body in [
        ("POST", SAPI_BASE, "/sapi/v1/c2c/agent/orderMatch/getUserOrderDetail", {"orderNumber": order_no}),
        ("POST", SAPI_BASE, "/sapi/v1/c2c/agent/orderMatch/getUserOrderDetail", {"orderNo":     order_no}),
    ]:
        try:
            log.info(f"  │  Mencoba {method} {path}")
            data   = _post(base, path, body) if method == "POST" else _get(base, path, body)
            code   = str(data.get("code", "—"))
            msg    = data.get("msg", "")
            detail = data.get("data") or {}

            log.info(f"  │  code     : {code}")
            log.info(f"  │  msg      : {msg or '(kosong)'}")

            if not detail:
                log.info(f"  │  data     : (kosong) — coba endpoint berikutnya")
                continue

            # Log semua field penting dari detail
            log.info(f"  │  ── Field Detail ──────────────────────")
            log.info(f"  │  orderNo        : {detail.get('orderNo', '—')}")
            log.info(f"  │  orderStatus    : {detail.get('orderStatus', '—')}")
            log.info(f"  │  tradeType      : {detail.get('tradeType', '—')}")
            log.info(f"  │  asset          : {detail.get('asset', '—')}")
            log.info(f"  │  fiatUnit       : {detail.get('fiatUnit', '—')}")
            log.info(f"  │  amount         : {detail.get('amount', '—')}")
            log.info(f"  │  price          : {detail.get('price', '—')}")
            log.info(f"  │  totalPrice     : {detail.get('totalPrice', '—')}")
            log.info(f"  │  payTimeLimit   : {detail.get('payTimeLimit', '—')}")
            log.info(f"  │  payTimeOut     : {detail.get('payTimeOut', '—')}")
            log.info(f"  │  payEndTime     : {detail.get('payEndTime', '—')}")
            log.info(f"  │  notifyPayEndT  : {detail.get('notifyPayEndTime', '—')}  → {fmt_time(detail.get('notifyPayEndTime', 0))}")
            log.info(f"  │  notifyPayTime  : {detail.get('notifyPayTime', '—')}  → {fmt_time(detail.get('notifyPayTime', 0))}")
            log.info(f"  │  confirmPayTime : {detail.get('confirmPayTime', '—')}  → {fmt_time(detail.get('confirmPayTime', 0))}")
            log.info(f"  │  createTime     : {detail.get('createTime', '—')}  → {fmt_time(detail.get('createTime', 0))}")
            log.info(f"  │  buyerNickname  : {detail.get('buyerNickname', '—')}")
            log.info(f"  │  sellerNickname : {detail.get('sellerNickname', '—')}")
            log.info(f"  │  nickName       : {detail.get('nickName', '—')}")
            log.info(f"  │  makerNickname  : {detail.get('makerNickname', '—')}")
            log.info(f"  │  takerNickname  : {detail.get('takerNickname', '—')}")
            log.info(f"  │  counterPartN   : {detail.get('counterPartNickName', '—')}")
            log.info(f"  │  advNo          : {detail.get('advNo', '—')}")
            log.info(f"  │  commission     : {detail.get('commission', '—')}")
            log.info(f"  │  commissionRate : {detail.get('commissionRate', '—')}")
            log.info(f"  │  isComplaint    : {detail.get('isComplaintAllowed', '—')}")
            log.info(f"  │  complaintStat  : {detail.get('complaintStatus', '—')}")

            # Log payment methods
            methods = (detail.get('tradeMethods') or detail.get('tradeMethodList')
                       or detail.get('buyerPaymentList') or detail.get('paymentList') or [])
            log.info(f"  │  ── Payment Methods ({len(methods)}) ──────────────")
            for m in methods:
                log.info(f"  │    identifier  : {m.get('identifier', '—')}")
                log.info(f"  │    name        : {m.get('tradeMethodName', '—')}")
                log.info(f"  │    payAccount  : {m.get('payAccount', '—')}")
                log.info(f"  │    payBank     : {m.get('payBank', '—')}")
                log.info(f"  │    realName    : {m.get('realName', '—')}")
                log.info(f"  │    accountNo   : {m.get('accountNo', '—')}")
                for field in (m.get('fields') or []):
                    log.info(f"  │    field       : {field.get('fieldName','')} = {field.get('fieldValue','')}")

            # Log semua key yang belum di-cover (untuk debug field baru)
            covered = {
                'orderNo','orderStatus','tradeType','asset','fiatUnit','amount',
                'price','totalPrice','payTimeLimit','payTimeOut','payEndTime',
                'notifyPayEndTime','notifyPayTime','confirmPayTime','createTime',
                'buyerNickname','sellerNickname','nickName','makerNickname',
                'takerNickname','counterPartNickName','advNo','commission',
                'commissionRate','isComplaintAllowed','complaintStatus',
                'tradeMethods','tradeMethodList','buyerPaymentList','paymentList',
            }
            extra_keys = {k: v for k, v in detail.items() if k not in covered}
            if extra_keys:
                log.info(f"  │  ── Field Lainnya ─────────────────────")
                for k, v in extra_keys.items():
                    val_str = str(v)[:80] + ("..." if len(str(v)) > 80 else "")
                    log.info(f"  │    {k:<24}: {val_str}")

            log.info(f"  └─ ✅ detail OK via {method}")
            return detail

        except Exception as e:
            log.warning(f"  │  ❌ {method} {path}: {e}")

    log.warning(f"  └─ ⚠️  Semua endpoint gagal, detail kosong")
    return {}


# ─── Ekstrak field penting dari order + detail ────────────────
def extract_fields(order: dict, detail: dict) -> dict:
    """
    Kumpulkan semua field penting dari kedua sumber (order list & detail).
    Binance kadang menaruh data di field yang berbeda tergantung endpoint.
    """
    # Counterpart — cari dari semua kemungkinan field
    counterpart = first_val(
        order.get("counterPartNickName"),
        detail.get("buyerNickname"),
        detail.get("sellerNickname"),
        detail.get("counterPartNickName"),
        detail.get("nickName"),
        detail.get("makerNickname"),
        detail.get("takerNickname"),
    ) or "—"

    # Batas bayar — cari dari semua kemungkinan field
    create_ms = first_val(order.get("createTime"), detail.get("createTime")) or 0
    end_pay   = first_val(
        detail.get("notifyPayEndTime"),
        order.get("notifyPayEndTime"),
        detail.get("payEndTime"),
        order.get("payEndTime"),
    )
    pay_limit_min = first_val(
        detail.get("payTimeLimit"),
        detail.get("payTimeOut"),
        order.get("payTimeLimit"),
        order.get("payTimeOut"),
        detail.get("paymentTimeLimit"),
        order.get("paymentTimeLimit"),
    )

    if pay_limit_min:
        try:
            deadline_ms   = int(create_ms) + int(pay_limit_min) * 60 * 1000
            pay_limit_str = f"{pay_limit_min} menit  ({fmt_time(deadline_ms)})"
        except Exception:
            pay_limit_str = f"{pay_limit_min} menit"
    elif end_pay:
        pay_limit_str = fmt_time(end_pay)
    else:
        pay_limit_str = "—"

    return {
        "no":          first_val(order.get("orderNumber"), detail.get("orderNo")) or "—",
        "asset":       first_val(order.get("asset"), detail.get("asset")) or "—",
        "fiat":        first_val(order.get("fiat"), detail.get("fiatUnit"), detail.get("fiat")) or "IDR",
        "amount":      first_val(order.get("amount"), detail.get("amount")) or "0",
        "total":       first_val(order.get("totalPrice"), detail.get("totalPrice")) or "0",
        "unit_price":  first_val(order.get("unitPrice"), detail.get("price"), detail.get("unitPrice")) or "0",
        "trade_raw":   first_val(order.get("tradeType"), detail.get("tradeType")) or "",
        "status_cd":   str(first_val(order.get("orderStatus"), detail.get("orderStatus")) or ""),
        "create_ms":   create_ms,
        "adv_no":      first_val(order.get("advertisementNo"), detail.get("advNo")) or "—",
        "counterpart": counterpart,
        "notify_pay":  first_val(detail.get("notifyPayTime"), order.get("notifyPayTime")),
        "confirm_pay": first_val(detail.get("confirmPayTime"), order.get("confirmPayTime")),
        "commission":  detail.get("commission", ""),
        "comm_rate":   detail.get("commissionRate", ""),
        "pay_limit_str": pay_limit_str,
    }



# ─── Fetch: Detail Iklan ──────────────────────────────────────
def fetch_ad_detail(adv_no: str) -> dict:
    """
    POST /sapi/v1/c2c/agent/ads/getDetailByNo
    Sesuai SKILL.md Scene 2.4 — View Ad Detail
    """
    log.info(f"  ┌─ fetch_ad_detail: {adv_no}")
    data   = _post(SAPI_BASE, "/sapi/v1/c2c/agent/ads/getDetailByNo", {"advNo": adv_no})
    code   = str(data.get("code", "—"))
    msg    = data.get("msg", "")
    detail = data.get("data") or {}

    log.info(f"  │  code        : {code}")
    log.info(f"  │  msg         : {msg or '(kosong)'}")

    if not detail:
        log.warning(f"  └─ ⚠️  data kosong (code={code} msg={msg})")
        return {}

    # Log semua field penting
    price_type_map = {"1": "Fixed", "2": "Floating"}
    status_map     = {"1": "Online", "2": "Offline", "4": "Closed"}

    log.info(f"  │  ── Field Ad Detail ───────────────────")
    log.info(f"  │  advNo              : {detail.get('advNo', '—')}")
    log.info(f"  │  tradeType          : {detail.get('tradeType', '—')}")
    log.info(f"  │  asset              : {detail.get('asset', '—')}")
    log.info(f"  │  fiatUnit           : {detail.get('fiatUnit', '—')}")
    log.info(f"  │  priceType          : {detail.get('priceType', '—')} ({price_type_map.get(str(detail.get('priceType','')),'—')})")
    log.info(f"  │  price              : {detail.get('price', '—')}")
    log.info(f"  │  priceFloatingRatio : {detail.get('priceFloatingRatio', '—')}")
    log.info(f"  │  initAmount         : {detail.get('initAmount', '—')}")
    log.info(f"  │  surplusAmount      : {detail.get('surplusAmount', '—')}")
    log.info(f"  │  minSingleTrans     : {detail.get('minSingleTransAmount', '—')}")
    log.info(f"  │  maxSingleTrans     : {detail.get('maxSingleTransAmount', '—')}")
    log.info(f"  │  payTimeLimit       : {detail.get('payTimeLimit', '—')} menit")
    log.info(f"  │  status             : {detail.get('advStatus', detail.get('status', '—'))} ({status_map.get(str(detail.get('advStatus', detail.get('status',''))),'—')})")
    log.info(f"  │  buyerKycLimit      : {detail.get('buyerKycLimit', '—')}")
    log.info(f"  │  buyerRegDaysLimit  : {detail.get('buyerRegDaysLimit', '—')}")
    log.info(f"  │  takerAddKyc        : {detail.get('takerAdditionalKycRequired', '—')}")
    log.info(f"  │  remarks            : {str(detail.get('remarks', '—'))[:80]}")
    log.info(f"  │  autoReplyMsg       : {str(detail.get('autoReplyMsg', '—'))[:80]}")

    methods = detail.get("tradeMethods") or []
    log.info(f"  │  ── Payment Methods ({len(methods)}) ──────────────")
    for m in methods:
        log.info(f"  │    {m.get('tradeMethodName', '—')} (id={m.get('identifier', '—')} payId={m.get('payId', '—')})")

    # Field tak terduga
    covered = {
        'advNo','tradeType','asset','fiatUnit','priceType','price',
        'priceFloatingRatio','initAmount','surplusAmount',
        'minSingleTransAmount','maxSingleTransAmount','payTimeLimit',
        'advStatus','status','buyerKycLimit','buyerRegDaysLimit',
        'takerAdditionalKycRequired','remarks','autoReplyMsg','tradeMethods',
    }
    extra = {k: v for k, v in detail.items() if k not in covered}
    if extra:
        log.info(f"  │  ── Field Lainnya ─────────────────────")
        for k, v in extra.items():
            log.info(f"  │    {k:<26}: {str(v)[:70]}")

    log.info(f"  └─ ✅ ad detail OK")
    return detail


# ─── Format: Ad Detail (sesuai SKILL.md) ─────────────────────
def format_ad_detail(detail: dict, send_tg: bool = True) -> str:
    """
    Format output sesuai SKILL.md Scene 2.4 View Ad Detail.
    Tampil di terminal + opsional kirim Telegram.
    """
    price_type_map = {"1": "Fixed", "2": "Floating"}
    status_map     = {"1": "🟢 Online", "2": "🔴 Offline", "4": "⛔ Closed"}
    trade_map      = {"BUY": "BUY 🟢", "SELL": "SELL 🔴", "0": "BUY 🟢", "1": "SELL 🔴"}

    adv_no      = detail.get("advNo", "—")
    trade_raw   = str(detail.get("tradeType", ""))
    asset       = detail.get("asset", "—")
    fiat        = detail.get("fiatUnit", detail.get("fiat", "—"))
    sym         = FIAT_SYM.get(fiat, fiat + " ")
    price_type  = str(detail.get("priceType", ""))
    price       = detail.get("price", "—")
    floating    = detail.get("priceFloatingRatio", "")
    init_amt    = detail.get("initAmount", "—")
    surplus     = detail.get("surplusAmount", "—")
    min_trans   = detail.get("minSingleTransAmount", "—")
    max_trans   = detail.get("maxSingleTransAmount", "—")
    pay_limit   = detail.get("payTimeLimit", "—")
    status_raw  = str(detail.get("advStatus", detail.get("status", "")))
    remarks     = detail.get("remarks") or "No terms set"
    auto_reply  = detail.get("autoReplyMsg") or "No auto-reply set"
    kyc         = "Yes" if detail.get("buyerKycLimit") in (1, "1", True) else "No"
    reg_days    = detail.get("buyerRegDaysLimit") or "—"
    extra_verify= "Yes" if detail.get("takerAdditionalKycRequired") in (1, "1", True) else "No"

    price_str = (
        f"{sym}{fmt_num(price)}"
        f" ({price_type_map.get(price_type, '—')})"
        + (f" | Floating: {floating}%" if floating else "")
    )

    methods = detail.get("tradeMethods") or []
    method_names = ", ".join(m.get("tradeMethodName", "—") for m in methods) or "—"

    # ── Terminal output ──────────────────────────────────────
    SEP = "─" * 55
    lines_terminal = [
        f"",
        f"  📄 Ad Detail: {adv_no}",
        f"  {SEP}",
        f"  ├─ Type           : {trade_map.get(trade_raw, trade_raw)} {asset}/{fiat}",
        f"  ├─ Price          : {price_str}",
        f"  ├─ Remaining      : {surplus} / {init_amt} {asset}",
        f"  ├─ Limit          : {sym}{fmt_num(min_trans)} ~ {sym}{fmt_num(max_trans)}",
        f"  ├─ Payment        : {method_names}",
        f"  ├─ Status         : {status_map.get(status_raw, status_raw)}",
        f"  ├─ Pay Timeout    : {pay_limit} menit",
        f"  │",
        f"  ├─ Trading Terms  :",
        f"  │  {remarks}",
        f"  │",
        f"  ├─ Auto-Reply     :",
        f"  │  {auto_reply}",
        f"  │",
        f"  └─ Advanced:",
        f"     ├─ Buyer KYC   : {kyc}",
        f"     ├─ Min Reg Days: {reg_days}",
        f"     └─ Extra Verify: {extra_verify}",
        f"  {SEP}",
        f"  🔗 {C2C_WEB}/en/adv?code={adv_no}",
        f"",
    ]
    for line in lines_terminal:
        print(line)

    # ── Telegram message ─────────────────────────────────────
    url_iklan = f"{C2C_WEB}/en/adv?code={adv_no}"
    tg_lines = [
        f"📄 <b>Ad Detail: <code>{adv_no}</code></b>",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"├─ <b>Type    :</b> {trade_map.get(trade_raw, trade_raw)} {asset}/{fiat}",
        f"├─ <b>Price   :</b> {price_str}",
        f"├─ <b>Sisa    :</b> {fmt_num(surplus, 6)} / {fmt_num(init_amt, 6)} {asset}",
        f"├─ <b>Limit   :</b> {sym}{fmt_num(min_trans)} ~ {sym}{fmt_num(max_trans)}",
        f"├─ <b>Payment :</b> {method_names}",
        f"├─ <b>Status  :</b> {status_map.get(status_raw, status_raw)}",
        f"├─ <b>Timeout :</b> {pay_limit} menit",
        "│",
        "├─ <b>Trading Terms:</b>",
        f"│  <i>{remarks}</i>",
        "│",
        "├─ <b>Auto-Reply:</b>",
        f"│  <i>{auto_reply}</i>",
        "│",
        "└─ <b>Advanced:</b>",
        f"   ├─ Buyer KYC    : {kyc}",
        f"   ├─ Min Reg Days : {reg_days}",
        f"   └─ Extra Verify : {extra_verify}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f'🔗 <a href="{url_iklan}">Buka Iklan di Binance</a>',
    ]
    tg_msg = "\n".join(tg_lines)

    if send_tg:
        ok = send_telegram(tg_msg)
        log.info(f"  Ad Detail Telegram: {'✅ Terkirim' if ok else '❌ Gagal'}")

    return tg_msg

# ─── Format: Seksi pembayaran ─────────────────────────────────
def format_payment_section(detail: dict, trade_type: str) -> str:
    trade_methods = (
        detail.get("tradeMethods") or detail.get("tradeMethodList")
        or detail.get("buyerPaymentList") or detail.get("paymentList") or []
    )
    if not trade_methods:
        pay_info = detail.get("payInfo") or detail.get("paymentInfo")
        if isinstance(pay_info, dict):   trade_methods = [pay_info]
        elif isinstance(pay_info, list): trade_methods = pay_info

    if not trade_methods:
        return ("⚠️ <i>Info rekening tidak tersedia via API.\n"
                "   Buka Binance App untuk melihat rekening.</i>")

    header = ("💳 <b>Rekening Buyer</b> (buyer transfer ke rekening ini):"
              if trade_type == "SELL" else
              "💳 <b>Rekening Seller</b> (kamu harus transfer ke sini):")
    lines = [header, ""]

    for idx, method in enumerate(trade_methods, 1):
        identifier   = method.get("identifier", "")
        method_name  = (method.get("tradeMethodName") or method.get("payType")
                        or identifier or "—")
        account_no   = (method.get("payAccount") or method.get("accountNo")
                        or method.get("account") or "")
        bank_name    = (method.get("payBank") or method.get("bankName")
                        or method.get("bank") or "")
        sub_bank     = method.get("paySubBank") or method.get("branchName") or ""
        account_name = (method.get("realName") or method.get("accountName")
                        or method.get("name") or "")

        # Field dinamis dari endpoint agent
        if not any([account_no, bank_name, account_name]):
            for field in (method.get("fields") or []):
                fname = (field.get("fieldName") or "").lower()
                fval  = field.get("fieldValue") or ""
                if not fval: continue
                if any(k in fname for k in ["account", "rekening", "number", "no"]):
                    account_no = fval
                elif any(k in fname for k in ["bank", "nama bank"]):
                    bank_name = fval
                elif any(k in fname for k in ["name", "nama", "owner", "atas nama"]):
                    account_name = fval

        icon   = payment_icon(identifier or method_name)
        prefix = f"[{idx}] " if len(trade_methods) > 1 else ""
        lines.append(f"{prefix}{icon} <b>{method_name}</b>")
        if account_no:
            lines.append(f"      📋 No. Rekening : <code>{account_no}</code>")
        if bank_name:
            lines.append(f"      🏛 Bank         : {bank_name + (' – ' + sub_bank if sub_bank else '')}")
        if account_name:
            lines.append(f"      👤 Atas Nama    : <b>{account_name}</b>")
        if not any([account_no, bank_name, account_name]):
            lines.append("      ℹ️ <i>Detail rekening belum tersedia. Cek Binance App.</i>")

    return "\n".join(lines)


# ─── Format pesan ─────────────────────────────────────────────
def format_message(order: dict, detail: dict, is_update: bool = False) -> str:
    f          = extract_fields(order, detail)
    sym        = FIAT_SYM.get(f["fiat"], f["fiat"] + " ")
    status_str = ORDER_STATUS.get(f["status_cd"], f"Status {f['status_cd']}")
    trade_label= "🟢 JUAL" if f["trade_raw"] == "SELL" else "🔴 BELI"

    # Banner
    if is_update:
        banner = f"🔄 <b>UPDATE STATUS ORDER</b>\n🔖 Status terbaru: <b>{status_str}</b>"
    elif f["trade_raw"] == "SELL":
        banner = (
            "🟢🟢🟢 <b>ORDER MASUK — TUNGGU PEMBAYARAN</b> 🟢🟢🟢\n"
            "Buyer akan transfer ke rekening kamu.\n"
            "Setelah uang masuk → tekan <b>Konfirmasi &amp; Rilis Koin</b>.\n"
            "🚫 <b>JANGAN rilis sebelum uang benar-benar masuk!</b>"
        )
    else:
        banner = (
            "🔴🔴🔴 <b>SEGERA TRANSFER!</b> 🔴🔴🔴\n"
            "Kamu harus transfer ke rekening seller di bawah.\n"
            "Setelah transfer → tekan <b>Sudah Bayar / Transferred</b>.\n"
            f"⏰ Batas waktu: <b>{f['pay_limit_str']}</b>"
        )

    title = "🔄 <b>UPDATE ORDER P2P</b>" if is_update else "🔔 <b>ORDER P2P BARU MASUK!</b>"

    msg = (
        f"{title}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{banner}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📌 <b>No. Order   :</b> <code>{f['no']}</code>\n"
        f"📋 <b>No. Iklan   :</b> <code>{f['adv_no']}</code>\n"
        f"💱 <b>Tipe        :</b> {trade_label}\n"
        f"💎 <b>Aset        :</b> {f['asset']}\n"
        f"💵 <b>Fiat        :</b> {f['fiat']}\n\n"
        f"── 💰 TRANSAKSI ──\n"
        f"📦 <b>Jumlah      :</b> {fmt_num(f['amount'], 6)} {f['asset']}\n"
        f"💲 <b>Harga/unit  :</b> {sym}{fmt_num(f['unit_price'])}\n"
        f"💸 <b>Total       :</b> <b>{sym}{fmt_num(f['total'])}</b>\n\n"
        f"── 📅 WAKTU ──\n"
        f"🕐 <b>Masuk       :</b> {fmt_time(f['create_ms'])}\n"
        f"⏰ <b>Batas bayar :</b> {f['pay_limit_str']}\n"
    )

    if f["notify_pay"]:
        msg += f"✅ <b>Dibayar     :</b> {fmt_time(f['notify_pay'])}\n"
        msg += f"⏱ <b>Durasi bayar:</b> {fmt_duration(f['create_ms'], f['notify_pay'])}\n"
    if f["confirm_pay"]:
        msg += f"🔓 <b>Dikonfirmasi:</b> {fmt_time(f['confirm_pay'])}\n"

    # Mitra — selalu tampilkan meski "—"
    role = "Buyer" if f["trade_raw"] == "SELL" else "Seller"
    msg += (
        f"\n── 👤 MITRA ──\n"
        f"🧑 <b>{role:<6} :</b> {f['counterpart']}\n"
    )

    if f["commission"] and f["comm_rate"]:
        msg += (
            f"\n── 💼 KOMISI ──\n"
            f"📉 <b>Rate   :</b> {f['comm_rate']}%\n"
            f"💰 <b>Jumlah :</b> {f['commission']} {f['asset']}\n"
        )

    msg += f"\n━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += format_payment_section(detail, f["trade_raw"])
    msg += f"\n━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += (
        f"\n🔖 <b>Status :</b> {status_str}\n"
        f"🌐 <b>Proxy  :</b> {'🟢 ON' if get_proxy() else '🔴 OFF'}\n"
        f"🔗 <a href=\"{C2C_WEB}/id/order/{f['no']}\">Buka Order di Binance</a>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )
    return msg


# ─── Telegram ─────────────────────────────────────────────────
def send_telegram(text: str) -> int | None:
    """Kirim pesan, kembalikan message_id jika berhasil, None jika gagal."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id":    TELEGRAM_CHAT_ID,
            "text":       text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, proxies=get_proxy(), timeout=20)
        r.raise_for_status()
        return r.json().get("result", {}).get("message_id")
    except Exception as e:
        log.error(f"Telegram send error: {e}")
        return None


def delete_telegram(message_id: int) -> bool:
    """Hapus pesan Telegram berdasarkan message_id."""
    if not message_id:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteMessage"
    try:
        r = requests.post(url, json={
            "chat_id":    TELEGRAM_CHAT_ID,
            "message_id": message_id,
        }, proxies=get_proxy(), timeout=10)
        ok = r.json().get("result", False)
        if ok:
            log.info(f"  🗑  Pesan lama dihapus (id={message_id})")
        else:
            log.warning(f"  ⚠️  Gagal hapus pesan id={message_id}: {r.json().get('description','')}")
        return ok
    except Exception as e:
        log.error(f"Telegram delete error: {e}")
        return False


# ─── Cek server Binance (tanpa proxy, tanpa auth) ─────────────
def check_server_connection() -> bool:
    SEP = "─" * 48
    print(f"  {SEP}")
    print("  🌐 CEK KONEKSI SERVER BINANCE (tanpa proxy)")
    print(f"  {SEP}")
    print("  Menghubungi api.binance.com...", end=" ", flush=True)
    try:
        r = requests.get(f"{SAPI_BASE}/api/v3/time", proxies=None, timeout=20)
        if r.status_code == 200:
            drift_s = abs(r.json().get("serverTime", 0) - _ts()) // 1000
            print(f"✅  OK  (drift: {drift_s}d)")
            print(f"  {SEP}\n")
            return True
        elif r.status_code == 451:
            print(f"❌  HTTP 451 — Diblokir geografis")
            print(f"  {SEP}")
            print("  ⚠️  Aktifkan proxy agar bisa terhubung.\n")
            return False
        else:
            print(f"❌  HTTP {r.status_code}")
            print(f"  {SEP}\n")
            return False
    except requests.exceptions.ReadTimeout:
        print(f"❌  Timeout")
        print(f"  {SEP}\n")
        return False
    except Exception as e:
        print(f"❌  {type(e).__name__}: {str(e)[:70]}")
        print(f"  {SEP}\n")
        return False


# ─── Cek API lengkap (dengan proxy jika aktif) ────────────────
def check_api() -> bool:
    SEP = "─" * 48
    print(f"  {SEP}")
    print("  🔍 CEK KONEKSI API BINANCE")
    print(f"  {SEP}")
    results = {}

    # 1. Server
    print("  [1/3] Koneksi ke server Binance...", end=" ", flush=True)
    try:
        r = requests.get(f"{SAPI_BASE}/api/v3/time", proxies=get_proxy(), timeout=20)
        if r.status_code == 200:
            drift_s = abs(r.json().get("serverTime", 0) - _ts()) // 1000
            print(f"✅  (drift: {drift_s}d)")
            results["server"] = True
        elif r.status_code == 451:
            print(f"❌  HTTP 451 — Diblokir geografis")
            results["server"] = False
        else:
            print(f"❌  HTTP {r.status_code}")
            results["server"] = False
    except requests.exceptions.ReadTimeout:
        print(f"❌  Timeout — proxy lambat / bermasalah")
        results["server"] = False
    except requests.exceptions.ProxyError:
        print(f"❌  ProxyError — proxy tidak bisa terhubung")
        results["server"] = False
    except Exception as e:
        print(f"❌  {type(e).__name__}: {str(e)[:60]}")
        results["server"] = False

    # 2. API Key — semua params SEBELUM sign
    print("  [2/3] Validasi API Key...", end=" ", flush=True)
    try:
        params = {"page": 1, "rows": 1, "timestamp": _ts()}
        params["signature"] = _sign(params)
        r = requests.get(
            f"{SAPI_BASE}/sapi/v1/c2c/orderMatch/listUserOrderHistory",
            params=params, headers=_headers(), proxies=get_proxy(), timeout=20,
        )
        data = r.json()
        code = str(data.get("code", ""))
        msg  = data.get("msg", "")
        if r.status_code == 451:
            print(f"❌  HTTP 451 — Diblokir geografis")
            results["apikey"] = False
        elif code in ("000000", "0", "") or r.status_code == 200:
            print(f"✅  API Key valid")
            results["apikey"] = True
        elif code in ("-2015",) or r.status_code == 401:
            print(f"❌  API Key tidak valid / tidak ada izin Reading")
            results["apikey"] = False
        elif code == "-1021":
            print(f"⚠️   Timestamp tidak sinkron — sinkronkan waktu sistem")
            results["apikey"] = False
        elif code == "-1022":
            print(f"❌  Signature gagal — cek SECRET_KEY di .env")
            results["apikey"] = False
        else:
            print(f"⚠️   code={code} msg={msg}")
            results["apikey"] = False
    except requests.exceptions.ReadTimeout:
        print(f"❌  Timeout — proxy lambat, coba ganti proxy")
        results["apikey"] = False
    except requests.exceptions.ProxyError:
        print(f"❌  ProxyError — proxy gagal terhubung ke Binance")
        results["apikey"] = False
    except Exception as e:
        print(f"❌  {type(e).__name__}: {str(e)[:60]}")
        results["apikey"] = False

    # 3. Telegram
    print("  [3/3] Koneksi Telegram Bot...", end=" ", flush=True)
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getMe",
            proxies=get_proxy(), timeout=20,
        )
        data = r.json()
        if data.get("ok"):
            print(f"✅  @{data['result'].get('username', '—')}")
            results["telegram"] = True
        else:
            print(f"❌  {data.get('description', 'Token tidak valid')}")
            results["telegram"] = False
    except requests.exceptions.ReadTimeout:
        print(f"❌  Timeout")
        results["telegram"] = False
    except Exception as e:
        print(f"❌  {type(e).__name__}: {str(e)[:60]}")
        results["telegram"] = False

    # Ringkasan
    print(f"  {SEP}")
    all_ok = all(results.values())
    if all_ok:
        print("  ✅  Semua cek lolos — bot siap dijalankan!")
    else:
        failed = [k for k, v in results.items() if not v]
        print(f"  ⚠️   Gagal: {', '.join(failed)}")
        print()
        print("  Lanjutkan meski ada kegagalan? [y/n]: ", end="", flush=True)
        ans = input().strip().lower()
        if ans not in ("y", "yes", "1"):
            print("  Bot dihentikan.")
            return False
    print(f"  {SEP}\n")
    return True


# ─── Pilihan proxy saat startup ───────────────────────────────
def ask_proxy_on_startup() -> bool:
    if not _PROXY_DICT:
        print("  ⚠️  Tidak ada proxy di .env — proxy dinonaktifkan.\n")
        return False
    host = (_PROXY_HTTPS or _PROXY_HTTP).split("@")[-1]
    print(f"  Proxy tersedia: {host}")
    while True:
        choice = input("  Aktifkan proxy? [y/n]: ").strip().lower()
        if choice in ("y", "yes", "1"): return True
        if choice in ("n", "no", "0"):  return False
        print("  Ketik y atau n.")


# ─── Kontrol keyboard ─────────────────────────────────────────
_stop_event = threading.Event()

def print_controls():
    print()
    print("  ┌──────────────────────────────────────────────┐")
    print("  │  KONTROL BOT (ketik + Enter)                 │")
    print("  │  p          → toggle proxy ON/OFF            │")
    print("  │  s          → status proxy sekarang          │")
    print("  │  ad <advNo> → cek detail iklan (+ Telegram)  │")
    print("  │  q          → keluar                         │")
    print("  └──────────────────────────────────────────────┘")
    print()

def input_listener():
    while not _stop_event.is_set():
        try:
            cmd = input().strip().lower()
        except EOFError:
            break
        if cmd == "p":
            with _proxy_lock:
                new_state = not _proxy_enabled
            set_proxy(new_state)
            state_str = "🟢 ON" if new_state else "🔴 OFF"
            log.info(f"Proxy → {state_str}  ({proxy_status_str()})")
            send_telegram(
                f"⚙️ <b>Proxy Status Diubah</b>\n"
                f"Status baru: <b>{state_str}</b>\n"
                f"Host: {(_PROXY_HTTPS or _PROXY_HTTP or '—').split('@')[-1]}"
            )
        elif cmd == "s":
            log.info(f"Proxy: {proxy_status_str()}")
        elif cmd == "q":
            log.info("Keluar...")
            _stop_event.set()
            break
        elif cmd.startswith("ad "):
            adv_no = cmd[3:].strip()
            if not adv_no:
                print("  ⚠️  Format: ad <advNo>  contoh: ad 11234567890")
            else:
                log.info(f"Mencari detail iklan: {adv_no}")
                detail = fetch_ad_detail(adv_no)
                if detail:
                    format_ad_detail(detail, send_tg=True)
                else:
                    print(f"  ❌ Iklan {adv_no} tidak ditemukan atau tidak ada akses.")
        elif cmd:
            print("  ⚠️  Perintah tidak dikenal. Ketik p / s / ad <advNo> / q")


# ─── Main loop ────────────────────────────────────────────────
def main():
    print()
    print("╔══════════════════════════════════════════════╗")
    print("║   Binance P2P Order Notifier v3 — MULAI     ║")
    print("╚══════════════════════════════════════════════╝")
    print(f"  C2C_WEB  : {C2C_WEB}")
    print(f"  SAPI     : {SAPI_BASE}")
    print(f"  Interval : {POLL_INTERVAL} detik")
    print()

    if not all([BINANCE_API_KEY, BINANCE_SECRET_KEY, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
        log.error("⛔ Konfigurasi tidak lengkap! Cek file .env")
        sys.exit(1)

    # Step 1: Cek server tanpa proxy
    check_server_connection()

    # Step 2: Pilih proxy
    enabled = ask_proxy_on_startup()
    set_proxy(enabled)
    print()
    log.info(f"Proxy: {proxy_status_str()}")
    print()

    # Step 3: Cek API lengkap (pakai proxy jika aktif)
    if not check_api():
        sys.exit(1)

    # Step 4: Start keyboard listener
    t = threading.Thread(target=input_listener, daemon=True)
    t.start()
    print_controls()

    send_telegram(
        "🤖 <b>Binance P2P Notifier v3 — AKTIF!</b>\n\n"
        "✅ Bot terhubung &amp; mulai memantau order P2P.\n"
        f"🔄 Polling setiap <b>{POLL_INTERVAL} detik</b>\n"
        f"🌐 Proxy: <b>{'🟢 ON' if enabled else '🔴 OFF'}</b>\n"
        f"🕐 Mulai: {fmt_time(_ts())}\n\n"
        "📬 Notifikasi order baru + update status aktif dikirim otomatis!"
    )

    log.info("Bot siap — langsung memantau order baru...")
    log.info("(Ketik p=proxy, s=status, ad <advNo>=iklan, q=keluar)")
    print()

    # Ambil order terbaru sebagai baseline — semua dimasukkan ke existing
    # agar tidak dinotifikasi ulang saat bot restart
    log.info("Mengambil baseline order (tidak akan dinotifikasi)...")
    _baseline    = fetch_orders(20)
    existing     = {o.get("orderNumber") for o in _baseline if o.get("orderNumber")}
    active_orders: dict = {}

    for o in _baseline:
        no = o.get("orderNumber")
        sc = str(o.get("orderStatus") or "")
        if not no:
            continue
        if sc in ACTIVE_STATUSES:
            # Order aktif saat bot start → dipantau tanpa notif, message_id=None
            active_orders[no] = {"status": sc, "msg_id": None}
            log.info(f"  ⏳ Baseline aktif: {no} (status={sc}) — dipantau tanpa notif")
        else:
            log.info(f"  ✅ Baseline final: {no} (status={sc}) — diabaikan")

    log.info(f"✔ Baseline: {len(existing)} order diketahui, {len(active_orders)} dipantau aktif.")
    log.info("Bot berjalan... (ketik p=proxy, s=status, ad <advNo>=iklan, q=keluar)")
    print()

    while not _stop_event.is_set():
        try:
            orders = fetch_orders(20)
            log.info(
                f"Polling... | proxy: {proxy_status_str()} | "
                f"known: {len(existing)} | aktif: {len(active_orders)}"
            )

            for order in reversed(orders):
                no        = order.get("orderNumber")
                status_cd = str(order.get("orderStatus") or "")
                if not no:
                    continue

                # ── Order baru ──────────────────────────────────
                if no not in existing:
                    existing.add(no)
                    log.info(f"  🔔 Order baru: {no} (status={status_cd})")

                    detail = fetch_order_detail(no)
                    msg    = format_message(order, detail, is_update=False)
                    msg_id = send_telegram(msg)
                    log.info(f"  {'✅ Terkirim' if msg_id else '❌ Gagal'} (msg_id={msg_id}) — {no}")

                    # Auto fetch Ad Detail
                    adv_no = (order.get("advertisementNo")
                              or detail.get("advNo")
                              or extract_fields(order, detail).get("adv_no"))
                    if adv_no and adv_no != "—":
                        log.info(f"  📋 Auto fetch Ad Detail: {adv_no}")
                        ad_detail = fetch_ad_detail(adv_no)
                        if ad_detail:
                            format_ad_detail(ad_detail, send_tg=True)
                        else:
                            log.warning(f"  ⚠️  Ad Detail tidak tersedia untuk {adv_no}")
                    else:
                        log.info(f"  ℹ️  advNo tidak tersedia — skip Ad Detail")

                    # Masukkan ke pantauan aktif
                    if status_cd in ACTIVE_STATUSES and status_cd not in FINAL_STATUSES:
                        active_orders[no] = {"status": status_cd, "msg_id": msg_id}
                        log.info(f"  ⏳ Dipantau: {no} (status={status_cd})")
                    else:
                        log.info(f"  🏁 Order langsung final: {no} (status={status_cd}) — tidak dipantau")

                # ── Update status order aktif ───────────────────
                elif no in active_orders:
                    entry       = active_orders[no]
                    prev_status = entry["status"]
                    prev_msg_id = entry["msg_id"]
                    is_final    = status_cd in FINAL_STATUSES or status_cd not in ACTIVE_STATUSES

                    if status_cd != prev_status:
                        log.info(f"  🔄 Status berubah: {no}  {prev_status} → {status_cd}")

                        # Hapus pesan lama sebelum kirim yang baru
                        if prev_msg_id:
                            delete_telegram(prev_msg_id)

                        detail = fetch_order_detail(no)
                        msg    = format_message(order, detail, is_update=True)
                        msg_id = send_telegram(msg)
                        log.info(f"  {'✅ Update terkirim' if msg_id else '❌ Gagal'} (msg_id={msg_id}) — {no}")

                        active_orders[no] = {"status": status_cd, "msg_id": msg_id}
                    else:
                        log.debug(f"  ⏳ Masih aktif: {no} (status={status_cd})")

                    # Selesai dipantau jika sudah final
                    if is_final:
                        log.info(f"  🏁 Order selesai dipantau: {no} → status={status_cd}")
                        active_orders.pop(no, None)

            time.sleep(1)

        except KeyboardInterrupt:
            log.info("Bot dihentikan (Ctrl+C).")
            break
        except Exception as e:
            log.error(f"Loop error: {e}")

        _stop_event.wait(timeout=POLL_INTERVAL)

    log.info("Bot selesai.")


if __name__ == "__main__":
    main()
