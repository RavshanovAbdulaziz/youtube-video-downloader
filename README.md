# YouTube Video Downloader

Shaxsiy/lokal foydalanish uchun YouTube video yuklab olish vositasi. Har qanday
resolyutsiyada, ovozli yoki ovozsiz, va istalgan tildagi audio trekda (shu
jumladan YouTube'ning avtomatik dublyaj qilingan audio treklarida) yuklab
olish imkonini beradi. Shuningdek audioni AI yordamida odam gapi va fon
tovushlariga (musiqa/effekt) ajratib berish imkoniyati bor — ikkita dvigatel
tanlash mumkin: **Demucs** (tezroq) yoki **UVR/BS-Roformer** (sifatliroq,
sekinroq).

## Tezkor boshlash (Windows)

1. **`setup.bat`** faylini ikki marta bosing — kerakli kutubxonalarni
   o'rnatadi (birinchi marta ishlatishda, bir marta bajarish kifoya).
2. **`start.bat`** faylini ikki marta bosing — brauzer avtomatik ochiladi,
   va soat yonidagi **tray sohasida ikonka** paydo bo'ladi. Qora konsol
   oynasi ochilmaydi.
3. Ishni tugatish uchun **tray ikonkasiga o'ng tugma** bilan bosib
   **"Chiqish"** ni tanlang.

Ixtiyoriy: **`create_shortcut.bat`** — ish stoliga yorliq yaratadi, shunda
loyiha papkasini har safar ochib o'tirish shart emas.

### Tray ikonkasi menyusi

Ikonka rangi holatni bildiradi: **qizil** — ishlayapti, **kulrang** —
to'xtatilgan. O'ng tugma bilan bosilganda:

| Menyu | Nima qiladi |
|---|---|
| Ochish (brauzerda) | Web UI'ni brauzerda ochadi |
| To'xtatish / Ishga tushirish | Serverni to'xtatadi yoki qayta yoqadi (dasturdan chiqmasdan) |
| Qayta ishga tushirish | Serverni to'xtatib, darhol qayta ko'taradi |
| Yuklamalar papkasi | Yuklab olingan fayllar papkasini ochadi |
| Loglar papkasi | Xato izlari yoziladigan papka (nosozlik qidirganda kerak) |
| Sozlamalar (bot token) | Telegram bot tokenini kiritish/o'zgartirish |
| Chiqish | Serverni ham, botni ham to'xtatib, dasturdan butunlay chiqadi |

Tray ikonkasi ko'rinmasa, u Windows'ning "yashirilgan ikonkalar" (`^`
strelka) ostida bo'lishi mumkin — uni strelkadan tortib chiqarib, doimiy
ko'rinadigan qilib qo'yish mumkin.

`stop.bat` ham ishlayveradi (zaxira usul) — u portni band qilgan jarayonni
majburan to'xtatadi.

## `.exe` sifatida qurish (tray ilova)

Python o'rnatilmagan boshqa kompyuterda ham ishlaydigan yagona `.exe` fayl
kerak bo'lsa:

1. **`build_exe.bat`** faylini ikki marta bosing (ffmpeg tizimda o'rnatilgan
   bo'lishi kerak — natijaviy `.exe` uni o'z ichiga oladi).
2. Natija: `dist/YouTubeDownloader/YouTubeDownloader.exe` — shu papkani
   (butunligicha) istalgan joyga ko'chirib ishlatish mumkin.
3. Ishga tushirilganda konsol oynasi ochilmaydi — dastur tizim tray'ida
   (soat yonidagi strelka ostida) ikonka sifatida ishlaydi va brauzer
   avtomatik ochiladi. Tray ikonkasiga sichqonchaning o'ng tugmasi bilan
   bosib: serverni to'xtatish/qayta ishga tushirish, Yuklamalar papkasini
   ochish, Telegram bot tokenini sozlash yoki dasturdan butunlay chiqish
   mumkin.

## Talablar

- Python 3.10+
- [ffmpeg](https://ffmpeg.org/) (PATH'da bo'lishi kerak — video/audio merge va mp3'ga
  o'girish uchun ishlatiladi)
- (Ixtiyoriy, "Ovozni ajratish" funksiyasi uchun) PyTorch + Demucs + audio-separator —
  GPU (NVIDIA/CUDA) bo'lsa ancha tezroq ishlaydi. `setup.bat` shuni ham so'raydi.

## Qo'lda o'rnatish (bat-fayllarsiz)

```bash
cd backend
pip install -r requirements.txt
```

"Ovozni ajratish" funksiyasi (ixtiyoriy) uchun loyiha papkasidagi
**`install_ai.bat`** faylini ishga tushiring (GPU/CPU tanlovini so'raydi va
kerakli hamma narsani — PyTorch, Demucs, audio-separator, muvofiqlik
tuzatishlarini — avtomatik o'rnatadi). Windows'siz muhitda shu faylning
ichidagi buyruqlarni qo'lda bajarishingiz mumkin.

**Eslatma**: Demucs va UVR natijalari `.mp3` formatida saqlanadi (`.wav` emas) —
chunki yangi `torchaudio` versiyalari `.wav` yozish uchun `torchcodec`
kutubxonasiga muhtoj, u esa Windows'da tizimdagi ffmpeg bilan mos DLL
topolmasligi mumkin. `.mp3` chiqishi bu muammoni butunlay chetlab o'tadi.

## Qo'lda ishga tushirish (bat-fayllarsiz)

```bash
cd backend
uvicorn main:app --host 127.0.0.1 --port 8000
```

Brauzerda oching: http://127.0.0.1:8000

## Kod ustida ishlash (development)

Kundalik ishlatish uchun `start.bat` (tray, konsolsiz) qulay, lekin kod
o'zgartirganda har safar tray'dan "Qayta ishga tushirish"ni bosish o'rniga
**`start_dev.bat`**ni ishlating:

- konsol oynasi ochiq qoladi — xatolar/loglar darhol ko'rinadi
- `.py` fayl saqlanganda server **o'zi qayta yuklanadi** (`--reload`)
- to'xtatish: shu oynada `Ctrl+C`

Testlar (`backend/tests/`, tarmoqqa chiqmaydi, ~5 soniyada tugaydi):

```bash
cd backend
py -3.14 -m pip install pytest pytest-asyncio httpx   # bir martalik
py -3.14 -m pytest
```

## Qanday ishlaydi

1. YouTube havolasini kiritib "Tekshirish" tugmasini bosing — video sarlavhasi,
   thumbnail, mavjud resolyutsiyalar va audio treklar (tillar) ro'yxati chiqadi.
2. **Video** bo'limida kerakli sifatni, ovoz bor/yo'qligini va (agar bir nechta
   til mavjud bo'lsa) audio tilini tanlab, "Videoni yuklab olish"ni bosing.
3. **Audio (alohida)** bo'limida faqat ovozni (tanlangan tilda, mp3 formatida)
   alohida yuklab olish mumkin.
4. **Ovozni ajratish** bo'limida audio AI yordamida ikkiga ajratiladi: faqat
   odam gapi va faqat fon tovushlari (musiqa, effektlar). Dvigatelni tanlash
   mumkin — **Demucs** (tezroq, masalan 19 soniyalik audio GPU'da ~2 soniyada)
   yoki **UVR/BS-Roformer** (sifatliroq, lekin ancha sekinroq, xuddi shu audio
   uchun ~35-40 soniya). Bu jarayon audio davomiyligi va GPU/CPU tezligiga
   qarab bir necha daqiqa vaqt olishi mumkin.

Har bir holatda progress ko'rsatiladi, tugagach fayl havolasi(lari) paydo bo'ladi.
Yuklab olingan fayllar `backend/downloads/` papkasida vaqtincha saqlanadi va
foydalanuvchi ularni yuklab olgach avtomatik o'chib ketadi.

## Server ustida ishlash (Web UI + Telegram bot)

Loyiha endi faqat lokal emas — ochiq serverga joylashtirilib, Web UI orqali ham,
Telegram bot orqali ham ishlatilishi mumkin.

- **Web UI**: birinchi marta ochilganda, kompyuteringiz kuchidan (CPU/GPU)
  foydalanishga ruxsat so'raladi. Rozi bo'lsangiz va shu kompyuterda
  `start.bat` orqali dastur ishlab tursa, yuklash/ajratish jarayonlari o'sha
  kompyuterda (tezroq) bajariladi. Rad etsangiz yoki mahalliy dastur
  topilmasa — hammasi serverda bajariladi. Tanlovingiz brauzeringizda
  eslab qolinadi, sahifadagi kichik yozuvni bosib istalgan vaqt
  o'zgartirishingiz mumkin. **Eslatma**: zamonaviy Chrome'da brauzer
  o'zining alohida "local tarmoqqa ruxsat berish" oynasini ham ko'rsatishi
  mumkin — shuni ham tasdiqlash kerak bo'ladi.
- **Telegram bot**: YouTube havolasini yuboring — bot sifat/audio/ajratish
  tanlovlarini tugmalar bilan taklif qiladi. Telegram'ning oddiy Bot API
  orqali fayl yuborish chegarasi ~50MB — undan katta fayllar uchun bot Web
  UI havolasini taklif qiladi (agar quyidagi ixtiyoriy lokal Bot API server
  sozlanmagan bo'lsa).

  **Ixtiyoriy: 2GB'gacha fayl yuborish.** Standart 50MB chegarani 2000MB'gacha
  ko'tarish uchun Telegram'ning rasmiy `telegram-bot-api` serverini `--local`
  rejimda lokal ishga tushirish mumkin (masalan WSL/Linux orqali, manba
  kodidan qurilib — https://github.com/tdlib/telegram-bot-api). Kerak
  bo'ladigan narsa: my.telegram.org/apps'dan `api_id`/`api_hash`, va
  serverni `--http-ip-address=127.0.0.1` bilan **faqat shu kompyuterga**
  bog'lab ishga tushirish (tashqi tarmoqqa ochiq qoldirmaslik kerak — u
  autentifikatsiyasiz, real bot tokenlarini ushlab turadi). So'ng
  `backend/.env`ga `LOCAL_API_BASE_URL=http://127.0.0.1:8081` qatorini
  qo'shing — bot avtomatik shu serverdan foydalanadi.

  **Muhim eslatma:** dastlab bot doimo bulut serverida ishlashi rejalashtirilgan
  edi, lekin amalda YouTube bulut serverlarning (Oracle, AWS, GCP va h.k.) IP
  diapazonlarini doimiy ravishda bloklaydi ("Sign in to confirm you're not a
  bot" xatosi — cookie, PO token, JS runtime kabi hech qanday workaround bilan
  ham barqaror hal bo'lmadi). Shuning uchun bot hozircha **shaxsiy
  kompyuterda** (rezidensial IP orqali, bloklanmaydi) ishlaydi:
  `start_bot.bat` faylini ishga tushiring (`backend/.env` ichida `BOT_TOKEN=...`
  qatori bo'lishi kerak — bu fayl git'ga qo'shilmaydi). Bot faqat shu
  kompyuter yoqiq va skript ishlab turgan vaqtda javob beradi.

### Oracle Cloud Always Free'ga joylashtirish

Bepul serverlardan aksariyati (Render, Railway va h.k.) uxlab qoladi yoki CPU
chegaralangan bo'lib, Demucs/UVR kabi bir necha daqiqa davom etadigan og'ir
jarayonlarga yaramaydi. **Oracle Cloud Always Free** (Ampere A1, ARM, masalan
4 OCPU / 24GB RAM) esa muddatsiz bepul va haqiqiy CPU beradi — shu tavsiya
etiladi.

1. Oracle Cloud'da hisob oching va **Always Free** Ampere A1 VM yarating
   (Ubuntu 22.04, aarch64).
2. VM'ga ulanib, Docker va Docker Compose plugin'ini o'rnating:
   ```bash
   sudo apt update && sudo apt install -y docker.io docker-compose-v2
   sudo usermod -aG docker $USER   # keyin qayta ulaning
   ```
3. **Portni ikkala qatlamda ham oching** (Oracle'da bu eng ko'p uchraydigan
   muammo — faqat birini ochish yetarli emas):
   - Console'da: VCN → Security List (yoki NSG) → Ingress Rules → `0.0.0.0/0`
     uchun TCP 80 portini qo'shing.
   - VM ichida:
     ```bash
     sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
     sudo netfilter-persistent save
     ```
4. VM'ning ochiq IP manzilini **Reserved Public IP**ga aylantiring (Console →
   Networking) — aks holda VM qayta ishga tushganda IP o'zgarib, hamma narsa
   buziladi.
5. Loyihani VM'ga klonlang, `.env` faylini yarating:
   ```bash
   git clone <repo-url> && cd <repo-dir>
   cp .env.example .env
   nano .env   # BOT_TOKEN va PUBLIC_ORIGIN (http://<vm-ip>) ni to'ldiring
   ```
6. Ishga tushiring:
   ```bash
   docker compose up -d --build
   ```
7. Brauzerda `http://<vm-ip>` manzilini oching — Web UI ishlashi kerak. Bot
   Telegram'da darhol javob bera boshlaydi.

**Eslatma**: hozircha domen yo'qligi sababli sayt oddiy HTTP orqali ochiladi
(HTTPS emas). Keyinchalik domen olsangiz, `Caddy` kabi reverse-proxy qo'shib
avtomatik Let's Encrypt sertifikat olish oson qo'shimcha qadam bo'ladi.

### YouTube "Sign in to confirm you're not a bot" xatoligi

Bulutli server (Oracle Cloud, AWS, GCP va h.k.) IP manzillaridan kelgan
so'rovlarni YouTube ko'pincha bot deb hisoblab bloklaydi. Loyihada bir nechta
workaround qo'shilgan (cookies.txt, Node.js JS runtime, PO token provider —
pastga qarang), lekin **amaliyotda bu workaround'larning hech biri Oracle
Cloud'ning bloklangan IP diapazoni uchun doimiy yechim bo'lmadi** — bir necha
soatlik/kunlik testdan so'ng ham xato saqlanib qoldi. Bu YouTube tomonidan
butun IP diapazonining doimiy bloklanganini ko'rsatadi, vaqtinchalik cheklov
emas.

**Amaldagi yechim:** Telegram bot va (agar ruxsat berilsa) Web UI'ning
yuklab olish/ajratish qismi **shaxsiy kompyuterda** (rezidensial IP orqali)
ishlaydi — bunda bu muammo ancha kamroq uchraydi, lekin **rezidensial
IP'larda ham to'liq yo'qolmagan** — YouTube tobora ko'proq holatlarda haqiqiy
PO (Proof-of-Origin) token talab qiladi.

**Lokal (Windows) ishga tushirishda ikkita himoya avtomatik ishlaydi, hech
qanday sozlash shart emas:**

1. **Lokal bgutil PO token serveri** — agar
   [bgutil-ytdlp-pot-provider](https://github.com/Brainicism/bgutil-ytdlp-pot-provider)
   repozitoriysi qo'lda klonlanib qurilgan bo'lsa (`git clone` + `server/`
   papkasida `npm ci && npx tsc`, standart joy: foydalanuvchi papkasidagi
   `bgutil-ytdlp-pot-provider\server`), `backend/pot_server.py` uni birinchi
   so'rovda avtomatik fon jarayoni sifatida ishga tushiradi (port 4416) va PO
   token'ni o'zi ta'minlaydi. Buni hali qurmagan bo'lsangiz, yuqoridagi
   havoladagi "Installation" bo'limiga qarang — bu ixtiyoriy, lekin eng
   barqaror yechim (cookie'ga bog'liq emas, hisob bekor qilinishidan
   ta'sirlanmaydi).
2. **cookies.txt** — `backend/cookies.txt` fayli mavjud bo'lsa (pastga
   qarang), hech qanday `.env` sozlamasisiz avtomatik topiladi va ishlatiladi.

Agar serverda (Oracle Cloud va h.k.) ham cookie orqali urinib ko'rmoqchi
bo'lsangiz:

1. Chrome/Firefox'ga "Get cookies.txt LOCALLY" kabi kengaytma o'rnating.
2. youtube.com'da tizimga kirgan holda cookie'larni `cookies.txt` (Netscape
   format) sifatida eksport qiling.
3. Faylni serverga yuklang: `scp cookies.txt ubuntu@<vm-ip>:~/youtube-video-downloader/backend/cookies.txt`
4. Serverda qayta ishga tushiring: `docker compose restart`

`backend/cookies.txt` — `.gitignore`'da, git'ga hech qachon qo'shilmaydi
(unda sizning sessiya ma'lumotlaringiz bor). Namuna uchun
`backend/cookies.txt.example`'ga qarang.

## Loyiha fayllari

```
you tube video downloander/
├── start.bat            # Kundalik ishlatish: tray rejimida ishga tushirish
├── start_dev.bat        # Kod ustida ishlash: konsol + auto-reload
├── create_shortcut.bat  # Ish stoliga "YouTube Downloader" yorlig'i yaratadi
├── start_bot.bat        # Telegram botni shu kompyuterda alohida ishga tushirish
├── stop.bat             # Serverni to'xtatish (tray ikonkasi ishlamasa, zaxira)
├── stop.ps1             # stop.bat ichida ishlatiladigan PowerShell skripti
├── setup.bat            # Birinchi marta o'rnatish (bosish bilan)
├── install_ai.bat       # "Ovozni ajratish" (AI) qo'shimcha o'rnatish
├── Dockerfile           # Serverga (Linux/ARM) joylashtirish uchun image
├── docker-compose.yml   # api + bot xizmatlari
├── .env.example         # BOT_TOKEN va boshqa muhit o'zgaruvchilari namunasi
├── launcher/
│   ├── tray_app.py         # Tray ikonkasi, server/bot jarayonlarini boshqaradi
│   └── token_dialog.py     # Birinchi ishga tushirishda bot token so'raydi
├── backend/
│   ├── main.py             # FastAPI endpointlari
│   ├── downloader.py       # yt-dlp bilan video/audio yuklab olish logikasi
│   ├── separator.py        # Demucs/UVR bilan audio ajratish logikasi
│   ├── bot.py               # Telegram bot (aiogram)
│   ├── requirements.txt     # Asosiy kutubxonalar
│   ├── requirements-ai.txt  # AI (Demucs/UVR) kutubxonalari — Linux/Docker uchun
│   ├── tests/               # pytest test to'plami (`py -3.14 -m pytest`)
│   └── downloads/          # Yuklab olingan fayllar vaqtincha shu yerda
└── frontend/
    ├── index.html
    ├── style.css
    └── app.js
```

## Eslatma

Bu vosita shaxsiy foydalanish uchun mo'ljallangan. YouTube'dan video yuklab
olish YouTube xizmat ko'rsatish shartlariga (ToS) zid bo'lishi mumkin —
faqat o'zingizga tegishli yoki ochiq litsenziyali kontent uchun ishlating.
