# grok-suite

Factory akun + panen **credential Grok (xAI)** otomatis, plus sinkronisasi ke
gateway OpenAI-compatible (grok2api). Jalan di **Windows / Linux / macOS**.

Ringan: 12 file, ~1.100 LOC, 2 dependensi (`patchright`, `camoufox`).

---

## Instalasi

**Windows (PowerShell)**

```powershell
git clone https://github.com/hudalilsabrina/grok-suite.git
cd grok-suite
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

**Linux / macOS**

```bash
git clone https://github.com/hudalilsabrina/grok-suite.git
cd grok-suite
bash setup.sh
```

`setup` membuat venv, memasang `patchright` + `camoufox`, lalu mengunduh browser
Chromium (solver Turnstile) dan Firefox Camoufox (engine harvest).

## Pemakaian

**Windows**

```bat
grok.bat harvest                 :: 1 akun
grok.bat harvest -n 3            :: 3 akun, jeda 2 menit
grok.bat list
grok.bat probe
grok.bat sync
grok.bat test
```

**Linux / macOS**

```bash
.venv/bin/python grok.py harvest -n 3
```

Di **Linux headless** browser butuh display — bungkus dengan `xvfb-run`:

```bash
xvfb-run -a .venv/bin/python grok.py harvest
```

Di Windows tidak perlu apa-apa (browser jalan headed).

### Opsi `harvest`

| Opsi | Arti |
|---|---|
| `-n, --count` | jumlah akun (default 1) |
| `--delay` | jeda antar akun, detik (default 120) |
| `--timeout` | timeout tunggu kode OTP, detik (default 180) |
| `--stop-on-gate` | berhenti kalau gate `email-signup-unavailable` / rate-limit |
| `--headless` | mode headless (Linux: tetap perlu xvfb-run) |

### Konfigurasi

```bash
cp config.example.toml config.toml
```

```toml
[api]
tempmail_base = "https://<host-tempik-anda>/api"   # API kompatibel tempik

[router]
url = "http://127.0.0.1:20127"
password = ""
```

| Env | Fungsi |
|---|---|
| `TEMPIK_BASE` | base API temp-mail (menimpa config.toml) |
| `GROK_MAIL` | `tempik` (default) atau `mailtm` |
| `GROK_DOMAIN` | paksa satu domain tempik tertentu |
| `TS_PYTHON` | python yang punya `patchright` (kalau beda venv) |
| `G2A` | base grok2api (default `http://127.0.0.1:8000`) |
| `G2A_ADMIN_PASS` / `G2A_ADMIN_USER` | kredensial admin grok2api |
| `G2A_ADMIN_FILE` | file berisi `admin user:` / `admin pass:` (default `~/.grok2api-admin.txt`) |
| `G2A_CLIENT_KEY` / `G2A_CLIENTKEY_FILE` | client key untuk `/v1` |

## Alur (reverse-engineered)

```
1. buka accounts.x.ai/sign-up (Camoufox, Firefox)
2. "Sign up with email" -> isi email temp-mail -> Continue
   └─ Castle SDK di halaman asli menyertakan `castleRequestToken`
      (tanpa itu server balas 200 {"ok":true} tapi email TIDAK dikirim)
3. kode OTP masuk inbox (subject "SpaceXAI confirmation code: NNN-NNN")
4. POST /api/auth/sign-up/verify-email
5. form "Complete your sign up": nama + password
6. Turnstile -> token dari patchright (Chromium), di-inject ke halaman
7. POST /api/auth/sign-up/create-account   <-- langkah penentu
8. cookie `sso` -> accounts.txt
```

### Tiga temuan yang menentukan

1. **Jangan klik tombol `Complete sign up`.** Tombol React-nya tidak memicu
   request apa pun ketika token Turnstile di-inject dari luar (token ada di DOM,
   tapi tidak masuk state React). Tembak API-nya langsung dari konteks halaman
   supaya cookie sesi ikut:
   ```js
   fetch('/api/auth/sign-up/create-account', {
     method: 'POST', credentials: 'include',
     headers: {'Content-Type': 'application/json'},
     body: JSON.stringify({email, password, givenName, familyName,
                           emailValidationCode: code, turnstileToken: tok})
   })
   ```
2. **Camoufox tidak bisa Turnstile.** Di Firefox `window.turnstile` tak pernah
   terdefinisi dan iframe challenge tidak muncul (postMessage antar-iframe gagal).
   Tapi **Camoufox yang menembus gate signup**. Jadi: halaman di Camoufox, token
   di-solve di patchright, lalu inject. Kombinasi keduanya yang menang.
3. **`castleRequestToken` wajib** pada langkah kirim kode.

## Yang penting soal egress

**`grok.com` memblokir IP datacenter (403)** — SSO yang valid pun tidak melayani
request dari IP DC. Yang bekerja: **egress residensial**.

Di grok2api, pasang proxy residensial sebagai *egress node* lalu assign akun:

```bash
# 1) profil proxy
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

# 4) uji
curl -b jar -X POST $G2A/api/admin/v1/egress-nodes/1/test -d '{}'
```

> Token admin grok2api dikirim sebagai **HttpOnly cookie**, dan `accessToken` di
> body JSON sengaja dipotong — pakai cookie jar, jangan Bearer dari body.

## Format akun (`accounts.txt`)

```
email:password:sso
```

Parser memakai `split(":", 2)` karena password bisa mengandung `:`.

## Struktur

```
grok.py               CLI (harvest / list / probe / sync / test)
harvest_camoufox.py   engine harvest (Camoufox + submit via API)
ts_solve_cli.py       solver Turnstile (patchright, halaman minimal)
src/common.py         helper: password, nama, OTP, simpan akun/inbox
src/mail.py           klien temp-mail (tempik + mail.tm)
src/turnstile.py      pembungkus solver + inject token
setup.sh / setup.ps1  instalasi (Linux-macOS / Windows)
grok.bat              wrapper Windows
scan-secrets.sh       gerbang rahasia sebelum publish (+ self-test)
```

## Pitfall

- **Jangan publish** `config.toml`, `accounts.txt`, `proxies*.txt`, `data/`.
  Jalankan `./scan-secrets.sh` (working tree + git history) sebelum push.
- **Gate `email-signup-unavailable` bukan soal domain.** Uji A/B: gmail, domain
  tempik, dan domain tanpa MX sama-sama ditolak saat gate tutup, dan sama-sama
  lolos saat gate buka. Pembedanya **waktu** dan **egress**. Gate buka-tutup
  (teramati jendela beberapa menit s/d ~30 menit), jadi retry pelan lebih baik
  daripada hammer.
- **`mail.tm` diblokir xAI** (`form-invalid:disposable-email`); tempik tidak.
- **Rate limit kirim kode per-IP** (`Too many code requests`): beri jeda.
- **Rotasi proxy per-request bisa mematahkan `cf_clearance`** di tengah flow —
  sisakan sebagian percobaan tanpa proxy.

## Kredit

- [Camoufox](https://github.com/daijro/camoufox) — Firefox anti-detect (engine harvest)
- [patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright) — Chromium stealth (solver Turnstile)
- [tempik](https://github.com/hirotomasato/tempik) — layanan temp-mail
- [grok2api](https://github.com/chenyme/grok2api) — gateway multi-akun Grok
