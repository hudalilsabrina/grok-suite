# Grok Suite

Factory akun + panen **credential Grok (xAI)** otomatis, plus jalur **OAuth Device
(Grok Build)** dan sinkronisasi ke gateway OpenAI-compatible (9router / grok2api).

Status: **berfungsi** — akun dibuat, SSO tersimpan, dan inference terverifikasi
lewat gateway. Lihat `STATUS.md` untuk catatan lapangan.

---

## Jalur yang terbukti

### 1. Harvest SSO (email + OTP) — **direkomendasikan**

Engine: **Camoufox** (Firefox anti-detect). Ini yang menembus anti-abuse xAI dari
IP datacenter; Chromium/Playwright standar sering dapat
`{"code":"account:email-signup-unavailable"}` di langkah yang sama.

```
harvest_camoufox.py
  buka accounts.x.ai/sign-up (Camoufox, headed + Xvfb)
  → "Sign up with email" → isi email temp-mail → Continue
     (Castle SDK di halaman asli menyertakan castleRequestToken — WAJIB;
      tanpa itu server balas 200 {"ok":true} tapi email TIDAK dikirim)
  → baca kode OTP dari inbox (subject "SpaceXAI confirmation code: NNN-NNN")
  → POST /api/auth/sign-up/verify-email
  → form "Complete your sign up" (nama + password)
  → Turnstile: coba self-pass Camoufox; kalau gagal → solver patchright (Chromium)
     lalu token di-inject ke halaman Camoufox
  → POST /api/auth/sign-up/create-account  ← KUNCI
     {email, password, givenName, familyName, emailValidationCode, turnstileToken}
  → cookie `sso` → accounts.txt
```

**Tiga temuan yang menentukan:**

1. **Jangan klik tombol `Complete sign up`.** Tombol React-nya tidak memicu request
   sama sekali saat token Turnstile di-inject dari luar (token ada di DOM, tapi
   tidak masuk state React). Tembak **API-nya langsung** dari konteks halaman
   supaya cookie sesi ikut terkirim:
   ```js
   fetch('/api/auth/sign-up/create-account', {
     method: 'POST', credentials: 'include',
     headers: {'Content-Type': 'application/json'},
     body: JSON.stringify({email, password, givenName, familyName,
                           emailValidationCode: code, turnstileToken: tok})
   })
   ```
2. **Camoufox tidak menerbitkan token Turnstile** (Firefox: `window.turnstile`
   tak pernah terdefinisi, iframe challenge tak muncul). Pakai **patchright**
   (Chromium patched) di halaman minimal untuk mendapat token 816 char, lalu
   inject ke halaman Camoufox. `ts_solve_cli.py` melakukan ini.
3. **`castleRequestToken` wajib** pada langkah kirim kode.

### 2. OAuth Device (Grok Build)

`grok2api` memulai device flow (`POST /accounts/device/start`) → dapat
`verificationUriComplete` + `user_code` → `device_auth2.py` membuka halaman
device dengan Camoufox, mendaftar akun baru via temp-mail, lalu meng-otorisasi.
Credential Build masuk ke pool `grok_build`.

> Langkah signup di dalam device flow tunduk pada gate yang sama
> (`email-signup-unavailable`), jadi kalau gate tutup, jalur ini juga tertutup.

### 3. Sync ke gateway

`sync_grok2api.py` meng-import `accounts.txt` (SSO) ke pool **Grok Web** grok2api
lewat `POST /api/admin/v1/accounts/web/import`, lalu membuat/mengambil client key
untuk `/v1`.

---

## Yang penting soal egress

**`grok.com` memblokir IP datacenter (403).** SSO yang valid pun tidak akan
melayani request dari IP DC. Yang bekerja: **egress residensial**.

Di grok2api, pasang sebagai *egress node* dan assign akun ke node itu:

```bash
# 1) profil proxy (URL residensial, mis. rotasi per-request)
curl -b jar -X POST $G2A/api/admin/v1/egress-proxy-profiles \
  -H 'Content-Type: application/json' \
  -d '{"name":"resid","proxyURL":"http://user:pass@host:port"}'

# 2) node untuk scope grok_web
curl -b jar -X POST $G2A/api/admin/v1/egress-nodes \
  -H 'Content-Type: application/json' \
  -d '{"name":"resid-web","scope":"grok_web","enabled":true,"proxyProfileId":"1","accountCapacity":50}'

# 3) assign akun (WAJIB sertakan provider + ids)
curl -b jar -X POST $G2A/api/admin/v1/egress-nodes/1/accounts \
  -H 'Content-Type: application/json' \
  -d '{"provider":"grok_web","ids":["1"],"mode":"manual"}'

# 4) uji node
curl -b jar -X POST $G2A/api/admin/v1/egress-nodes/1/test -d '{}'
```

Verifikasi end-to-end:

```bash
curl $G2A/v1/chat/completions -H "Authorization: Bearer $CLIENT_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"model":"grok-chat-fast","messages":[{"role":"user","content":"hi"}],"max_tokens":10}'
```

> Token admin grok2api dikirim sebagai **HttpOnly cookie**, dan nilai
> `accessToken` di body JSON sengaja dipotong — pakai cookie jar, jangan Bearer
> dari body.

---

## Instalasi

```bash
python3 -m venv .venv
.venv/bin/pip install patchright rich requests
.venv/bin/patchright install chromium

# Camoufox (engine harvest utama) — venv terpisah dianjurkan
python3 -m venv .venv-camo
.venv-camo/bin/pip install 'camoufox[geoip]'
.venv-camo/bin/python -m camoufox fetch
```

Butuh browser **headed** — di server headless pakai Xvfb:

```bash
xvfb-run -a .venv-camo/bin/python harvest_camoufox.py
```

## Konfigurasi

```bash
cp config.example.toml config.toml
```

```toml
[api]
tempmail_base = "https://<host-tempik-anda>/api"   # kompatibel API tempik

[router]
url = "http://127.0.0.1:20127"
password = ""            # password admin 9router
```

Env yang dipakai skrip:

| Env | Fungsi |
|---|---|
| `G2A` | base grok2api (default `http://127.0.0.1:8000`) |
| `G2A_PASS` | password admin grok2api (untuk `device_loop.sh`) |
| `G2A_ADMIN_FILE` | file berisi baris `admin user:` / `admin pass:` |
| `G2A_CLIENTKEY_FILE` | tempat menyimpan client key hasil sync |
| `GROK_RESID_PROXY` | proxy residensial untuk attempt device |
| `GROK_MAIL` | `tempik` (default) atau `mailtm` |
| `GROK_DOMAIN` | paksa satu domain tempik tertentu |
| `TS_PYTHON` | python yang punya `patchright` (solver Turnstile) |
| `CAMO_PY` | python yang punya `camoufox` (untuk `camo_shoot.sh`) |
| `PROXY_PACKAGE` | path JSON paket proxy untuk `extract_proxies.py` |

## Command

```bash
# harvest (engine Camoufox) — 1 akun
CAMO_PY=.venv-camo/bin/python xvfb-run -a .venv-camo/bin/python harvest_camoufox.py

# tembak berulang sampai dapat 1 akun (jeda 5 menit, 12 percobaan)
CAMO_PY=.venv-camo/bin/python ./camo_shoot.sh 12 300

# engine patchright (cadangan)
xvfb-run -a ./run.sh harvest [n]
./run.sh test|report|sync|probe|check-inbox

# device OAuth (Grok Build) via grok2api
G2A_PASS='...' ./device_loop.sh 60 60

# cek apakah gate email-signup sedang terbuka
./run.sh probe                                   # satu email acak
xvfb-run -a .venv/bin/python probe_domains.py a@b.com c@d.com   # per-domain/egress

# sync ke grok2api
G2A_ADMIN_FILE=~/.grok2api-admin.txt .venv/bin/python sync_grok2api.py
```

## Format akun (`accounts.txt`)

```
email:password:sso
```

Parser harus pakai `split(":", 2)` — password bisa mengandung `:`.

## Struktur

```
harvest_camoufox.py   engine utama (Camoufox) + fallback Turnstile patchright
ts_solve_cli.py       solver Turnstile (patchright, halaman minimal)
camo_shoot.sh         retry loop harvest
device_auth2.py       driver OAuth device (signup + authorize)
device_loop.sh        retry loop device
sync_grok2api.py      import SSO -> pool grok2api + client key
probe_domains.py      uji eligibility domain/egress ke endpoint signup
main.py               CLI (patchright): harvest/test/report/sync/probe
src/grok.py           engine patchright + tempik + turnstile
src/tempmail.py       klien temp-mail (API tempik)
src/mailtm.py         klien mail.tm (alternatif; sering diblokir xAI)
src/router9.py        adapter 9router
auto.sh / manual_gmail.py / ua_replay.py / dump_signup.py   utilitas riset
scan-secrets.sh + test-scan-secrets.sh   gerbang rahasia sebelum publish
```

## Pitfall

- **Jangan publish `config.toml`, `accounts.txt`, `proxies*.txt`, `data/`.**
  Jalankan `./scan-secrets.sh` (working tree + git history) sebelum push.
- **Gate `email-signup-unavailable` bukan soal domain.** Uji A/B: gmail, domain
  tempik, dan domain tanpa MX semuanya dapat kode yang sama saat gate tutup, dan
  semuanya lolos saat gate buka. Yang membedakan adalah **waktu** dan **egress**.
- **`mail.tm` diblokir xAI** (`form-invalid:disposable-email`); tempik tidak.
- **Jangan andalkan klik tombol React** untuk submit form akhir — pakai API.
- **Rate limit kirim kode per-IP** (`Too many code requests`): beri jeda, jangan
  retry rapat. Retry agresif justru memperpanjang blokir.
- **Rotasi proxy per-request bisa mematahkan `cf_clearance`** di tengah flow —
  sebagian attempt sebaiknya jalan tanpa proxy.

## Kredit

- [Camoufox](https://github.com/daijro/camoufox) — Firefox anti-detect (engine harvest)
- [patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright) — Chromium stealth (solver Turnstile)
- [tempik](https://github.com/hirotomasato/tempik) — layanan temp-mail
- [grok2api](https://github.com/chenyme/grok2api) — gateway multi-akun Grok
- [turnaround](https://github.com/Body-Alhoha/turnaround) /
  [Turnstile-Solver](https://github.com/Theyka/Turnstile-Solver) — teknik solver Turnstile
