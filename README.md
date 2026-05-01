<div align="center">

# 🤖 Binance P2P Order Notifier Bot

**Bot Telegram otomatis untuk memantau & notifikasi order P2P Binance secara real-time**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python)](https://python.org)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?style=for-the-badge&logo=telegram)](https://core.telegram.org/bots)
[![Binance](https://img.shields.io/badge/Binance-P2P-F0B90B?style=for-the-badge&logo=binance)](https://binance.com)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

---

*Tidak perlu buka Binance App terus-terusan — bot ini yang akan memberitahu kamu!*


Jika kalian butuh  Crypto ecer , bisa mampir ke telegram Bot : [LAPAK SWAP BOT](https://t.me/LapakSwap_bot) : Pembayaran QRIS , dan sudah pasti INSTANT
</div>

---

## 📋 Daftar Isi

- [✨ Fitur](#-fitur)
- [📸 Preview](#-preview)
- [⚙️ Cara Kerja](#️-cara-kerja)
- [🚀 Instalasi](#-instalasi)
- [🔑 Konfigurasi `.env`](#-konfigurasi-env)
- [▶️ Menjalankan Bot](#️-menjalankan-bot)
- [🎮 Kontrol Bot](#-kontrol-bot)
- [📲 Contoh Notifikasi Telegram](#-contoh-notifikasi-telegram)
- [🔄 Alur Status Order](#-alur-status-order)
- [❓ FAQ & Troubleshooting](#-faq--troubleshooting)
- [📁 Struktur Proyek](#-struktur-proyek)

---

## ✨ Fitur

| Fitur | Keterangan |
|-------|-----------|
| 🔔 **Notifikasi Order Baru** | Langsung dapat notif Telegram saat ada order P2P masuk |
| 🔄 **Pantau Status Real-time** | Bot looping setiap N detik, deteksi perubahan status otomatis |
| 🗑️ **Auto Hapus Pesan Lama** | Saat status berubah, pesan lama dihapus → diganti pesan baru |
| 💳 **Info Rekening Lengkap** | Nomor rekening, nama bank, atas nama ditampilkan di notif |
| 📋 **Detail Iklan (Ad Detail)** | Fetch & kirim info iklan P2P secara otomatis |
| 🌐 **Proxy Support** | Dukung proxy HTTP/HTTPS — bisa di-toggle ON/OFF tanpa restart |
| 🔍 **Cek API Saat Startup** | Validasi koneksi Binance, API Key, dan Telegram sebelum mulai |
| 📊 **Log Terminal Detail** | Semua response API ditampilkan lengkap di terminal untuk debugging |
| 🎮 **Kontrol via Keyboard** | Toggle proxy, cek status, query iklan — semua dari terminal |
| 🏷️ **Pesan Unik per Status** | Setiap perubahan status punya banner & pesan yang berbeda |

---

## 📸 Preview

### Notifikasi Order Baru (SELL)
```
🔔 ORDER P2P BARU MASUK!
━━━━━━━━━━━━━━━━━━━━━━
🟢🟢🟢 ORDER MASUK — TUNGGU PEMBAYARAN 🟢🟢🟢
Buyer akan transfer ke rekening kamu.
Setelah uang masuk → tekan Konfirmasi & Rilis Koin.
🚫 JANGAN rilis sebelum uang benar-benar masuk!
━━━━━━━━━━━━━━━━━━━━━━

📌 No. Order   : 22883478277666422784
📋 No. Iklan   : 11823456789012345678
💱 Tipe        : 🟢 JUAL
💎 Aset        : USDT
💵 Fiat        : IDR

── 💰 TRANSAKSI ──
📦 Jumlah      : 100.000000 USDT
💲 Harga/unit  : Rp17,350.00
💸 Total       : Rp1,735,000.00

── 📅 WAKTU ──
🕐 Masuk       : 01 May 2026  17:30:00 WIB
⏰ Batas bayar : 15 menit  (01 May 2026  17:45:00 WIB)

── 👤 MITRA ──
🧑 Buyer  : BuyerXYZ123

━━━━━━━━━━━━━━━━━━━━━━
🔖 Status : 💰 Belum Bayar / Aktif
🌐 Proxy  : 🟢 ON
🔗 Buka Order di Binance
━━━━━━━━━━━━━━━━━━━━━━
```

### Update Status Otomatis
```
✅ UPDATE — BUYER SUDAH BAYAR!
━━━━━━━━━━━━━━━━━━━━━━
✅✅✅ BUYER SUDAH BAYAR! ✅✅✅
Segera cek rekening kamu.
Jika uang sudah masuk → tekan Konfirmasi & Rilis Koin.
🚫 JANGAN rilis sebelum benar-benar cek saldo!
```

---

## ⚙️ Cara Kerja

```
Bot Start
   │
   ├─ [1] Cek koneksi Binance (tanpa proxy)
   ├─ [2] Pilih proxy ON/OFF
   ├─ [3] Validasi API Key + Telegram Bot
   └─ [4] Mulai polling loop
           │
           ├─ Setiap N detik fetch daftar order terbaru
           │
           ├─ Order BARU? ──────────────────────────────┐
           │                                            ▼
           │                              Kirim notif Telegram
           │                              Simpan message_id
           │                              Fetch & kirim Ad Detail
           │                              Masukkan ke active_orders
           │
           └─ Status BERUBAH? ──────────────────────────┐
                                                        ▼
                                        Hapus pesan lama (deleteMessage)
                                        Kirim pesan baru dengan status terkini
                                        Update message_id
                                        Jika FINAL → hentikan pemantauan
```

### Status yang Dipantau

| Status | Keterangan | Dipantau? |
|--------|-----------|-----------|
| `TRADING` | Order aktif / belum bayar | ✅ Ya |
| `BUYER_PAYED` | Buyer sudah bayar | ✅ Ya |
| `PAID` / `2` | Sudah dibayar | ✅ Ya |
| `RELEASING` / `3` | Proses rilis koin | ✅ Ya |
| `IN_APPEAL` / `5` | Dalam banding | ✅ Ya |
| `COMPLETED` / `4` | Selesai | 🏁 Final |
| `CANCELLED` / `6` | Dibatalkan | 🏁 Final |
| `EXPIRED` / `7` | Kedaluwarsa | 🏁 Final |

---

## 🚀 Instalasi

### Prasyarat

- Python **3.10+**
- Akun Binance dengan P2P aktif
- Telegram Bot Token
- (Opsional) Proxy HTTP/HTTPS jika akses Binance diblokir di wilayah kamu

### Langkah Instalasi

**1. Clone repository**
```bash
git clone https://github.com/shareithub/p2p-notify.git
cd binance-p2p-notifier
```

**2. Buat virtual environment** *(disarankan)*
```bash
python3 -m venv venv
source venv/bin/activate        # Linux/Mac
# atau
venv\Scripts\activate           # Windows
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

Isi `requirements.txt`:
```
requests
python-dotenv
python-telegram-bot
```

**4. Buat file `.env`** *(lihat bagian konfigurasi di bawah)*

**5. Jalankan bot**
```bash
python3 bot.py
```

---

## 🔑 Konfigurasi `.env`

Buat file `.env` di folder yang sama dengan `bot.py`:

```env
# ─── Binance API ───────────────────────────────────────────────
BINANCE_API_KEY=your_api_key_here
BINANCE_SECRET_KEY=your_secret_key_here

# ─── Telegram ──────────────────────────────────────────────────
TELEGRAM_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=987654321

# ─── Pengaturan Bot ────────────────────────────────────────────
POLL_INTERVAL=10

# ─── Proxy (opsional) ──────────────────────────────────────────
PROXY_HTTP=http://username:password@host:port
PROXY_HTTPS=http://username:password@host:port
```

### Cara Mendapatkan Setiap Value

#### 🔐 `BINANCE_API_KEY` & `BINANCE_SECRET_KEY`

1. Login ke [Binance.com](https://binance.com)
2. Klik foto profil → **API Management**
3. Klik **Create API** → pilih **System Generated**
4. Beri nama (misal: `p2p-notifier`)
5. Di halaman edit API:
   - ✅ Centang **Enable Reading**
   - ❌ Jangan centang lainnya (tidak perlu)
6. Selesaikan verifikasi → salin API Key & Secret Key

> ⚠️ **Secret Key hanya muncul sekali!** Simpan baik-baik sebelum tutup halaman.

#### 🤖 `TELEGRAM_TOKEN`

1. Buka Telegram, cari **@BotFather**
2. Ketik `/newbot`
3. Ikuti instruksi (masukkan nama & username bot)
4. Salin token yang diberikan

#### 💬 `TELEGRAM_CHAT_ID`

1. Buka Telegram, cari **@userinfobot**
2. Klik Start / ketik `/start`
3. Bot akan membalas dengan **Chat ID** kamu
4. Salin angka tersebut

#### ⏱️ `POLL_INTERVAL`

Interval polling dalam detik. Semakin kecil = semakin cepat tapi lebih banyak request ke API.

| Value | Keterangan |
|-------|-----------|
| `5` | Sangat cepat (disarankan untuk trader aktif) |
| `10` | Default — seimbang antara kecepatan & efisiensi |
| `30` | Hemat request, cocok untuk pemantauan ringan |

#### 🌐 `PROXY_HTTP` & `PROXY_HTTPS` *(opsional)*

Diperlukan jika akses Binance API diblokir di wilayahmu (error 451).

Format: `http://username:password@host:port`

Contoh:
```env
PROXY_HTTP=http://user123:pass456@proxy.example.com:10000
PROXY_HTTPS=http://user123:pass456@proxy.example.com:10000
```

> Jika tidak punya proxy, kosongkan kedua baris ini. Bot akan tanya saat startup.

---

## ▶️ Menjalankan Bot

```bash
python3 bot.py
```

### Tampilan Startup

```
╔══════════════════════════════════════════════╗
║   Binance P2P Order Notifier v3 — MULAI     ║
╚══════════════════════════════════════════════╝
  C2C_WEB  : https://c2c.binance.com
  SAPI     : https://api.binance.com
  Interval : 10 detik

  ────────────────────────────────────────────────
  🌐 CEK KONEKSI SERVER BINANCE (tanpa proxy)
  ────────────────────────────────────────────────
  Menghubungi api.binance.com... ❌  HTTP 451 — Diblokir geografis
  ⚠️  Aktifkan proxy agar bisa terhubung.

  Proxy tersedia: res.proxy-seller.com:10000
  Aktifkan proxy? [y/n]: y

  ────────────────────────────────────────────────
  🔍 CEK KONEKSI API BINANCE
  ────────────────────────────────────────────────
  [1/3] Koneksi ke server Binance... ✅  (drift: 0d)
  [2/3] Validasi API Key...          ✅  API Key valid
  [3/3] Koneksi Telegram Bot...      ✅  @NamaBotKamu
  ────────────────────────────────────────────────
  ✅  Semua cek lolos — bot siap dijalankan!

  ┌──────────────────────────────────────────────┐
  │  KONTROL BOT (ketik + Enter)                 │
  │  p          → toggle proxy ON/OFF            │
  │  s          → status proxy sekarang          │
  │  ad <advNo> → cek detail iklan (+ Telegram)  │
  │  q          → keluar                         │
  └──────────────────────────────────────────────┘

2026-05-01 17:30:00 [INFO] Bot berjalan...
2026-05-01 17:30:00 [INFO] Polling... | proxy: 🟢 ON | known: 20 | aktif: 0
```

### Menjalankan di Background (Linux/VPS)

**Menggunakan `screen`:**
```bash
screen -S p2p-bot
python3 bot.py
# Tekan Ctrl+A lalu D untuk detach
# Kembali ke session: screen -r p2p-bot
```

**Menggunakan `nohup`:**
```bash
nohup python3 bot.py > bot.log 2>&1 &
echo $! > bot.pid
# Untuk menghentikan: kill $(cat bot.pid)
```

**Menggunakan `systemd` (auto-start):**

Buat file `/etc/systemd/system/p2p-bot.service`:
```ini
[Unit]
Description=Binance P2P Notifier Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/p2p-notif
ExecStart=/root/p2p-notif/venv/bin/python3 bot.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable p2p-bot
systemctl start p2p-bot
systemctl status p2p-bot
```

---

## 🎮 Kontrol Bot

Saat bot berjalan, ketik perintah di terminal lalu tekan **Enter**:

| Perintah | Fungsi |
|----------|--------|
| `p` | Toggle proxy **ON ↔ OFF** (berlaku langsung, kirim notif Telegram) |
| `s` | Tampilkan status proxy saat ini |
| `ad <advNo>` | Fetch & kirim detail iklan ke Telegram |
| `q` | Hentikan bot dengan aman |

**Contoh penggunaan:**
```bash
# Toggle proxy
p

# Cek status proxy
s

# Lihat detail iklan tertentu
ad 11823456789012345678

# Keluar
q
```

---

## 📲 Contoh Notifikasi Telegram

### 🟢 Order SELL — Baru Masuk
> Kamu jual USDT, menunggu buyer transfer IDR ke rekeningmu

```
🔔 ORDER P2P BARU MASUK!
━━━━━━━━━━━━━━━━━━━━━━
🟢🟢🟢 ORDER MASUK — TUNGGU PEMBAYARAN 🟢🟢🟢
Buyer akan transfer ke rekening kamu.
Setelah uang masuk → tekan Konfirmasi & Rilis Koin.
🚫 JANGAN rilis sebelum uang benar-benar masuk!
```

### 🔴 Order BUY — Baru Masuk
> Kamu beli USDT, harus transfer IDR ke rekening seller

```
🔔 ORDER P2P BARU MASUK!
━━━━━━━━━━━━━━━━━━━━━━
🔴🔴🔴 SEGERA TRANSFER! 🔴🔴🔴
Kamu harus transfer ke rekening seller di bawah.
Setelah transfer → tekan Sudah Bayar / Transferred.
⏰ Batas waktu: 15 menit (01 May 2026  17:45:00 WIB)
```

### ✅ Update — Buyer Sudah Bayar
```
✅ UPDATE — BUYER SUDAH BAYAR!
━━━━━━━━━━━━━━━━━━━━━━
✅✅✅ BUYER SUDAH BAYAR! ✅✅✅
Segera cek rekening kamu.
Jika uang sudah masuk → tekan Konfirmasi & Rilis Koin.
🚫 JANGAN rilis sebelum benar-benar cek saldo!
```

### 🎉 Order Selesai
```
🎉 ORDER SELESAI!
━━━━━━━━━━━━━━━━━━━━━━
🎉🎉🎉 TRANSAKSI BERHASIL! 🎉🎉🎉
Order telah selesai dan koin berhasil dirilis.
✅ Pemantauan order ini dihentikan.
```

### ⚠️ Dalam Banding
```
⚠️ UPDATE — ORDER DALAM BANDING!
━━━━━━━━━━━━━━━━━━━━━━
⚠️⚠️⚠️ ADA BANDING / DISPUTE! ⚠️⚠️⚠️
Order sedang dalam proses banding.
Segera buka Binance App untuk menangani dispute.
```

---

## 🔄 Alur Status Order

```
Order Baru
    │
    ▼
TRADING / 1 (Belum Bayar)
    │
    ▼
BUYER_PAYED / 2 (Buyer Sudah Bayar) ──── 5 / IN_APPEAL (Banding)
    │                                           │
    ▼                                           ▼
RELEASING / 3 (Proses Rilis)          CS Review & Mediasi
    │                                           │
    ▼                                           ▼
COMPLETED / 4 ◄─────────────────────── Selesai / CANCELLED
   🎉 Selesai                              ❌ Batal
```

> 🏁 Status **COMPLETED**, **CANCELLED**, dan **EXPIRED** adalah status **final** — bot akan berhenti memantau order tersebut secara otomatis.

---

## ❓ FAQ & Troubleshooting

### ❌ Error 451 — Diblokir Geografis

Binance memblokir akses API dari beberapa negara termasuk Indonesia.

**Solusi:**
1. Aktifkan proxy di file `.env`:
   ```env
   PROXY_HTTP=http://user:pass@host:port
   PROXY_HTTPS=http://user:pass@host:port
   ```
2. Atau gunakan VPN sebelum menjalankan bot
3. Saat startup bot, jawab `y` saat ditanya proxy

---

### ❌ Error `-1022` — Signature Failed

API Key atau Secret Key salah / tidak cocok.

**Solusi:**
- Periksa kembali `BINANCE_API_KEY` dan `BINANCE_SECRET_KEY` di file `.env`
- Pastikan tidak ada spasi atau karakter tersembunyi
- Coba buat ulang API Key di Binance

---

### ❌ Error `-2015` — Invalid API Key

API Key tidak valid atau tidak memiliki izin yang cukup.

**Solusi:**
- Pastikan API Key sudah diaktifkan **Enable Reading**
- Pastikan API Key belum expired atau dihapus
- Pastikan IP kamu tidak diblokir oleh Binance (jika menggunakan IP whitelist)

---

### ❌ Error `-1021` — Timestamp Not Synced

Waktu sistem kamu tidak sinkron dengan server Binance.

**Solusi:**
```bash
# Linux/VPS
sudo timedatectl set-ntp true
sudo systemctl restart systemd-timesyncd

# atau manual
sudo ntpdate pool.ntp.org
```

---

### ⚠️ Info Rekening Tidak Tersedia

Bot menampilkan *"Info rekening tidak tersedia via API"*.

**Kemungkinan penyebab:**
- Order baru dibuat dan info rekening belum tersedia di API
- Endpoint `getUserOrderDetail` memerlukan izin tambahan
- Coba cek langsung di Binance App

---

### 🔄 Order Lama Muncul Sebagai "Baru" Saat Restart

Bot mengambil 20 order terbaru sebagai baseline saat startup.

**Solusi:**
- Jangan sering restart bot
- Jika perlu restart, tunggu beberapa detik agar baseline terambil sempurna

---

### 📵 Notifikasi Telegram Tidak Terkirim

**Cek:**
1. `TELEGRAM_TOKEN` dan `TELEGRAM_CHAT_ID` sudah benar?
2. Sudah kirim pesan ke bot Telegram terlebih dahulu? (bot tidak bisa mulai kirim duluan)
3. Jika pakai proxy, pastikan proxy juga bisa akses `api.telegram.org`

---

## 📁 Struktur Proyek

```
binance-p2p-notifier/
│
├── bot.py              # File utama bot
├── .env                # Konfigurasi (jangan di-commit ke GitHub!)
├── .env.example        # Contoh file .env (aman untuk di-commit)
├── requirements.txt    # Daftar dependency Python
├── README.md           # Dokumentasi ini
└── .gitignore          # Abaikan file sensitif
```

### `.gitignore` yang Disarankan

```gitignore
.env
__pycache__/
*.pyc
*.pyo
venv/
.venv/
*.log
```

---

## ⚠️ Disclaimer

- Bot ini dibuat untuk keperluan pribadi dan edukasi
- Gunakan dengan bijak sesuai [Terms of Service Binance](https://binance.com/en/terms)
- Jangan pernah commit file `.env` ke repository publik
- Penulis tidak bertanggung jawab atas segala kerugian yang timbul dari penggunaan bot ini

---

## 📄 License

MIT License — bebas digunakan, dimodifikasi, dan didistribusikan dengan menyertakan atribusi.

---

<div align="center">

**Dibuat dengan ❤️ untuk trader P2P Indonesia**

⭐ Jika bermanfaat, jangan lupa kasih bintang di GitHub!

</div>
