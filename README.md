# 🎮 Peripheral Hub (Universal Gaming Gear & Peripheral Controller)

[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078D6?logo=windows)](https://github.com/Andrejayas/Peripheral-Hub)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![RAM Usage](https://img.shields.io/badge/RAM%20Usage-~30MB-brightgreen)](#-performa--filosofi)
[![CPU Usage](https://img.shields.io/badge/CPU%20Usage-0.0%25%20(Gaming)-brightgreen)](#-performa--filosofi)

> **"One Lightweight Hub to Rule Them All."**  
> Hentikan kebiasaan menginstal 4-5 software bawaan pabrikan (G HUB, Razer Synapse, iCUE, Armoury Crate, dan software OEM China) yang memakan ratusan MB hingga gigabyte RAM hanya untuk cek baterai dan ubah warna. **Peripheral Hub** adalah controller perifer all-in-one open-source untuk Windows yang super ringan (~30–45 MB RAM, 0% CPU saat gaming) untuk menyatukan Gamepad, Keyboard Mechanical, Mouse, Headset, dan Audio Enhancer dalam satu dashboard terpadu.

---

## 🌟 Ekosistem Periferal yang Didukung

Peripheral Hub dirancang dengan **Arsitektur Driver Modular** sehingga semua jenis elektronik gaming dapat disatukan ke dalam satu kontroler:

### 1. 🎮 Gamepads & Stik Controller (PlayStation / Xbox / Switch / 3rd Party)
* **Dukungan Universal**: Sony DualSense (PS5), DualShock 4 (PS4), Xbox One / Series X|S Wireless, Nintendo Switch Pro Controller, 8BitDo, HORI Gamepad (XInput, DirectInput, dan HID Vendor).
* **Monitoring Baterai**: Pantau persentase daya baterai stik secara akurat tanpa perlu software terpisah seperti DS4Windows.
* **Kalibrasi & Pengujian**: Tes getaran motor (*rumble*), pemicu adaptif (*adaptive trigger/haptics*), dan kalibrasi zona mati (*deadzone*) analog stik.

### 2. ⌨️ Mechanical Keyboards (AULA, QMK/VIA, Sonix, Custom)
* **Live Hardware Control**: Kontrol langsung melalui mode USB Cable (*Sonix bidirectional ACK handshake*) dan 2.4G Wireless Dongle.
* **20 Efek Lighting & Custom RGB**: Pilihan 20 mode pencahayaan fisik (Static, SingleOn, Glittering, Colourful, Breath, Spectrum, Explode, dll.) serta 9 tombol palet warna kustom (*Red, Blue, Green, Cyan, Purple, White, Rainbow, dll.*).
* **Slider Brightness & Speed**: Atur tingkat kecerahan LED (Level 1–5) dan kecepatan animasi efek (Speed 1–5).
* **Sinkronisasi Database Driver**: Tersinkronisasi otomatis dengan database konfigurasi resmi AULA S75 Pro (`S75Pro_datav1.db`).

### 3. 🖱️ Gaming Mice (Noir, PixArt PAW3395/3370/3311, Universal)
* **Baterai Akurat Real-Time**: Pembacaan voltase (mV), persentase baterai %, dan status pengisian daya (*charging*) langsung dari hardware.
* **Quick DPI Selector**: Pengubah DPI instan dengan preset 400, 800, 1200, 2400, 3200, 5000, hingga 10000+ DPI.
* **Deteksi Sleep / Online**: Deteksi otomatis saat mouse sedang aktif atau masuk ke mode hemat daya (*sleep mode*).

### 4. 🎧 Headsets & Audio Hardware (dbE Kumo, Wireless 2.4G)
* **Status Dongle 2.4G**: Memantau koneksi wireless dongle headset secara real-time.
* **Smart Battery Estimator**: Pelacak estimasi jam pemakaian aktif cerdas dengan pengingat cas otomatis saat headset tersambung kembali.
* **Volume Slider Terintegrasi**: Pengatur volume master Windows khusus output headset langsung dari panel.

### 5. 🔊 Built-in DSP Audio Enhancer (Equalizer APO & FxSound Engine)
* **FPS Step Booster**: Filter parametric EQ khusus yang mendongkrak frekuensi langkah kaki (316Hz, 1288Hz, 2432Hz, 4140Hz, 6800Hz) untuk keunggulan kompetitif di game FPS (CS2, Valorant, Apex Legends, PUBG).
* **Gaming Surround**: Menghasilkan *soundstage* yang lebih lebar untuk akurasi arah tembakan.
* **Music / Movie Preset**: Suara vokal jernih dengan *warm sub-bass*.
* **Flat Mode**: Mengembalikan suara ke kondisi netral/asli.

---

## 🖥️ Antarmuka & System Tray

* **Ikon Tray Dinamis (Adaptive Multi-Device Battery)**:
  - 🟢 **Hijau**: Semua baterai perangkat di atas 50%.
  - 🟠 **Oranye**: Ada perangkat yang tersisa 20% – 50%.
  - 🔴 **Merah**: Peringatan baterai lemah (< 20%) pada salah satu perangkat aktif.
* **Modern Connection Popup**: Notifikasi mengambang (*floating toast*) di pojok kanan bawah layar saat ada perangkat yang terhubung atau terputus.
* **Dark Dashboard Kompak**: Panel kontrol modern (420×580 px) bertema gelap dengan scroll yang mulus dan kontrol responsif.

---

## ⚡ Performa & Filosofi Desain

1. **Ultra Low Footprint**: Dibuat murni menggunakan Python native, Tkinter, ctypes, dan Win32 HID API. **Bebas Electron / Chromium**. Memori yang digunakan hanya berkisar **~30–45 MB RAM** (dibandingkan software pabrikan yang memakan 500MB – 1.5GB).
2. **0.0% CPU Impact**: Threading asynchronous dengan sleep adaptif memastikan nol beban pada prosesor saat bermain game berat.
3. **Fail-Safe & Plug-and-Play**: Semua komunikasi hardware dibungkus dalam proteksi penanganan error. Mencabut atau memasang perangkat tidak akan membuat aplikasi crash.
4. **Privasi 100%**: Tanpa akun login, tanpa internet, dan tanpa pengiriman telemetri/analitik apa pun ke server luar.

---

## 🚀 Cara Menjalankan

### Persyaratan Sistem
* Windows 10 atau Windows 11 (64-bit)
* Python 3.10 atau versi yang lebih baru

### 1. Instalasi Cepat
Clone repositori dan pasang dependensi:
```bash
git clone https://github.com/Andrejayas/Peripheral-Hub.git
cd Peripheral-Hub
pip install -r requirements.txt
```

### 2. Jalankan Aplikasi
Cukup klik ganda berkas:
```bash
run.bat
```
Atau melalui terminal:
```bash
python main.py
```

### 3. Jalankan Otomatis saat Windows Menyala (Auto-Start)
1. Tekan `Win + R` pada keyboard.
2. Ketik `shell:startup` lalu tekan Enter.
3. Buat *shortcut* dari berkas `run.bat` dan letakkan di dalam folder startup tersebut.

---

## 📂 Struktur Repositori

```
Peripheral-Hub/
├── main.py                  # Entry point aplikasi & background task scheduler
├── dashboard.py             # Dashboard utama (Tkinter Dark Mode)
├── popup.py                 # Toast popup notifikasi koneksi perangkat
├── tray.py                  # Ikon System Tray & menu kontrol
├── run.bat                  # Script peluncur 1-klik
├── config.json              # Konfigurasi profil & penyimpanan state
├── requirements.txt         # Daftar pustaka Python
├── assets/
│   ├── icon_generator.py    # Pembuat ikon dinamis
│   └── *.png                # Aset visual perangkat & tray
├── audio/
│   ├── equalizer_apo.py     # Interface parametric filter Equalizer APO
│   └── fxsound.py           # Interface audio controller FxSound
└── devices/
    ├── keyboard.py          # Driver Keyboard (AULA S75 Pro / Sonix HID)
    ├── mouse.py             # Driver Mouse (Noir M1 Nex / PixArt PAW HID)
    └── headset.py           # Driver Headset & Smart Battery Tracker
```

---

## 🤝 Kontribusi & Menambahkan Perangkat Baru

Proyek ini sangat terbuka untuk kontribusi komunitas! Siapa pun dapat menambahkan driver untuk periferal baru (misal stik PS5, stik Xbox, mouse Logitech, keyboard kustom lainnya):

1. **Fork** repositori ini.
2. Buat berkas driver baru di folder `devices/` (misal: `devices/controller_dualsense.py`).
3. Buat class dengan interface standar:
   - `scan_and_connect()` $\rightarrow$ deteksi VID/PID atau XInput/DirectInput.
   - `get_status()` $\rightarrow$ kembalikan dictionary status (baterai, koneksi, profile).
   - Method khusus fitur (misal `set_rgb()`, `set_dpi()`, `trigger_rumble()`).
4. Hubungkan ke `main.py` dan buat kartu kontrol di `dashboard.py`.
5. Kirimkan **Pull Request**!

---

## 📜 Lisensi

Proyek ini dirilis di bawah lisensi [MIT License](LICENSE) — bebas digunakan, dimodifikasi, dan didistribusikan oleh siapa saja untuk kepentingan pribadi maupun pengembangan lebih lanjut.
