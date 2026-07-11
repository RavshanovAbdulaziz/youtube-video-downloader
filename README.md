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
2. **`start.bat`** faylini ikki marta bosing — server ishga tushadi va
   brauzer avtomatik ochiladi.
3. Ishni tugatgach, **`stop.bat`** faylini ikki marta bosing — server
   to'xtatiladi (yoki shunchaki `start.bat` ochgan qora oynani yoping).

Shu fayllardan boshqa hech narsa qo'lda qilish shart emas.

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
- **Telegram bot**: har doim serverning o'z kuchidan foydalanadi (foydalanuvchi
  kompyuteriga hech qachon ulanmaydi). YouTube havolasini yuboring — bot
  sifat/audio/ajratish tanlovlarini tugmalar bilan taklif qiladi. Telegram'ning
  oddiy Bot API orqali fayl yuborish chegarasi ~50MB — undan katta fayllar
  uchun bot Web UI havolasini taklif qiladi.

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

## Loyiha fayllari

```
you tube video downloander/
├── start.bat            # Serverni ishga tushirish (bosish bilan)
├── stop.bat             # Serverni to'xtatish (bosish bilan)
├── stop.ps1             # stop.bat ichida ishlatiladigan PowerShell skripti
├── setup.bat            # Birinchi marta o'rnatish (bosish bilan)
├── install_ai.bat       # "Ovozni ajratish" (AI) qo'shimcha o'rnatish
├── Dockerfile           # Serverga (Linux/ARM) joylashtirish uchun image
├── docker-compose.yml   # api + bot xizmatlari
├── .env.example         # BOT_TOKEN va boshqa muhit o'zgaruvchilari namunasi
├── backend/
│   ├── main.py             # FastAPI endpointlari
│   ├── downloader.py       # yt-dlp bilan video/audio yuklab olish logikasi
│   ├── separator.py        # Demucs/UVR bilan audio ajratish logikasi
│   ├── bot.py               # Telegram bot (aiogram)
│   ├── requirements.txt     # Asosiy kutubxonalar
│   ├── requirements-ai.txt  # AI (Demucs/UVR) kutubxonalari — Linux/Docker uchun
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
