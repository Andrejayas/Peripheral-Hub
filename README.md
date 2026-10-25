# 🎧 Peripheral Hub (Windows All-in-One Controller)

Aplikasi terpadu berbasis **Windows System Tray** yang super ringan (~25–35 MB RAM, 0% CPU saat gaming) untuk memantau baterai, mengatur DPI/RGB, dan mengontrol audio untuk 3 perangkat gaming kamu sekaligus:

1. 🖱️ **Mouse**: Noir M1 Nex (2.4G Wireless)
2. ⌨️ **Keyboard**: AULA S75 Pro (USB / 2.4G)
3. 🎧 **Headset**: dbE Kumo GS1X Pro (2.4G USB Dongle)
4. 🔊 **Audio Enhancer**: Equalizer APO & FxSound (Preset FPS Step Booster, Movie/Music, dll.)

---

## ⚡ Fitur Utama

### 1. Mouse (Noir M1 Nex)
- **Baterai Akurat**: Dibaca langsung dari hardware via `hidusb.dll` (level %, voltase mV, dan status charging).
- **Quick DPI Selector**: Pilihan cepat 400, 800, 1200, 2400, 3200, 5000, 10000 DPI.
- **Deteksi Online/Sleep**: Mengetahui apakah mouse sedang aktif atau tidur (sleep mode).

### 2. Keyboard (AULA S75 Pro)
- **Live Hardware Control**: Mendukung kontrol langsung mode kabel USB (Sonix bidirectional ACK handshake) dan 2.4G Wireless Dongle.
- **20 Efek Lighting & Custom RGB**: Static, SingleOn, Glittering, Colourful, Breath, Spectrum, Explode, dll., serta 9 preset warna custom (Red, Blue, Green, Cyan, Purple, White, Rainbow, dll.).
- **Pengaturan Brightness & Speed**: Slider tingkat kecerahan (1–5) dan kecepatan efek (1–5).
- **Sinkronisasi Database**: Sinkron otomatis dengan SQLite database konfigurasi resmi AULA S75 Pro (`S75Pro_datav1.db`).

### 3. Headset (dbE Kumo GS1X Pro)
- **Status Koneksi 2.4G**: Memantau apakah dongle wireless aktif terhubung.
- **Smart Battery Tracker**: Estimator baterai pintar berdasarkan akumulasi jam pemakaian game aktif (kapasitas 16 jam).
- **Auto Reconnect / Charge Prompt**: Notifikasi saat headset dinyalakan kembali setelah lama mati untuk konfirmasi cas.
- **Volume Slider**: Pengatur volume master headset langsung dari dashboard.

### 4. Audio Control Center (Equalizer APO & FxSound)
- **FPS Step Booster**: Mengaktifkan filter parametric EQ (boost frekuensi 316Hz, 1288Hz, 2432Hz, 4140Hz, 6800Hz) untuk memperjelas suara langkah kaki musuh di game FPS (Valorant, CS2, Apex, dll.).
- **Music / Movie**: Preset warm bass + clear treble.
- **Gaming Surround**: Boost mid-high untuk arah suara yang lebih luas.
- **Flat**: Suara netral tanpa equalizer.

### 5. UI & System Tray
- **Ikon Tray Dinamis**:
  - 🟢 Hijau: Semua baterai perangkat > 50%
  - 🟠 Oranye: Salah satu perangkat 20% – 50%
  - 🔴 Merah: Salah satu perangkat < 20% (low battery warning)
- **Connection Popup**: Notifikasi popup modern bergaya EarFun Panel di pojok kanan bawah saat perangkat terkoneksi / terputus.
- **Dark Dashboard**: Panel kontrol kompak (420×580 px) bertema gelap (*dark mode*) yang muncul saat tray diklik.

---

## 🚀 Cara Menjalankan

### 1. Jalankan langsung
Cukup double-click file:
```
run.bat
```
Atau lewat terminal PowerShell / Command Prompt:
```bash
cd "E:\laragon\www\my project\peripheral-hub"
python main.py
```

### 2. Jalankan Otomatis saat Windows Menyala (Auto-Start)
Kamu bisa membuat shortcut `run.bat` dan meletakkannya di folder Windows Startup:
1. Tekan tombol `Win + R` di keyboard.
2. Ketik `shell:startup` lalu tekan Enter.
3. Tarik shortcut dari `run.bat` ke dalam folder tersebut.

---

## 📂 Struktur File

```
peripheral-hub/
├── main.py              # Entry point aplikasi & background poller
├── dashboard.py         # Jendela kontrol utama (Tkinter Dark Mode)
├── popup.py             # Animated connection popup
├── tray.py              # Ikon System Tray & menu klik kanan
├── run.bat              # Launcher 1-klik tanpa terminal
├── config.json          # Penyimpanan profil & state baterai
├── requirements.txt     # Dependensi Python
├── assets/
│   ├── icon_generator.py # Generator ikon otomatis
│   └── *.png            # Ikon-ikon UI & tray
├── audio/
│   ├── equalizer_apo.py # Interface konfigurasi Equalizer APO
│   └── fxsound.py       # Interface XML settings FxSound
└── devices/
    ├── mouse.py         # Driver Noir M1 Nex (ctypes + hidusb.dll)
    ├── keyboard.py      # Driver AULA S75 Pro (HID + SQLite)
    └── headset.py       # Interface Kumo GS1X Pro & Smart Estimator
```

---

## 🛠️ Catatan Teknis
- **Ringan**: Dibuat murni dengan Python native + Tkinter + Win32 API. Tidak menggunakan Electron atau browser webview yang memakan ratusan MB RAM.
- **Aman**: Semua panggilan hardware dibungkus dalam mekanisme *fail-safe* `try/except`. Jika salah satu perangkat dicabut, aplikasi tetap berjalan normal tanpa crash.
- **Lisensi**: MIT License.
