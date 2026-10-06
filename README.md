# Grok Suite

Factory akun + panen **SSO/credential Grok (xAI)** otomatis — jalan dari IP
datacenter, **tanpa proxy residensial**.

Engine: **[patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright)** —
Playwright yang di-patch anti-deteksi. Ini satu-satunya cara lolos Cloudflare
Turnstile dari datacenter:

| Engine | Turnstile xAI |
|---|---|
| Playwright standar | ❌ bocor sinyal otomasi → 0 token |
| Camoufox (Firefox) | ❌ `turnstile` tak pernah ter-init (postMessage gagal) |
| **patchright (Chromium patched)** | ✅ **token 816 char, diterima xAI** |

## Alur (reverse-engineered)

Semua lewat **halaman asli** `accounts.x.ai` (bukan HTTP polos) — sebab Castle
SDK harus aktif:

```
1. Buka https://accounts.x.ai/sign-up (patchright, headed + Xvfb)
2. "Sign up with email" → isi email → Continue
   └─ Castle SDK otomatis menyertakan `castleRequestToken` (WAJIB!)
3. Kode verifikasi masuk ke inbox temp-mail
   (subject "SpaceXAI confirmation code: NNN-NNN")
4. Isi kode → Continue
5. Form "Complete your sign up": First/Last name + Password
6. Turnstile form akhir → token dari solver (halaman minimal, patchright)
7. Submit → akun dibuat → cookie `sso`
```

### 🔑 Dua temuan kunci

1. **`castleRequestToken` wajib.** Tanpa field ini, server balas
   `200 {"ok":true}` (anti-enumeration) tapi **email TIDAK dikirim**. Token
   di-generate otomatis oleh Castle SDK di halaman asli.
2. **Turnstile butuh patchright.** Playwright standar / Camoufox gagal;
   patchright (Chromium yang di-patch) mendapat token valid.

## Instalasi

```bash
python3 -m venv .venv
.venv/bin/pip install patchright rich requests
.venv/bin/patchright install chromium
```

Butuh Chrome/Chromium **headed** — di server headless pakai Xvfb:

```bash
xvfb-run -a ./run.sh harvest 1
```

## Konfigurasi

Salin `config.example.toml` → `config.toml`. Isi endpoint temp-mail Anda
(atau env `TEMPIK_BASE`), dan `[router]` untuk sync 9router.

## Command

```bash
xvfb-run -a ./run.sh harvest [n]   # buat n akun Grok
./run.sh test                      # daftar SSO tersimpan
./run.sh report                    # ringkasan akun
./run.sh sync                      # inject ke 9router
./run.sh probe                     # cek apakah email-signup xAI aktif
```

Batch runner:

```bash
xvfb-run -a .venv/bin/python batch.py <n>                 # berhenti rapi saat diblokir
xvfb-run -a .venv/bin/python batch.py <n> --cooldown-wait # tunggu 30 menit lalu lanjut
xvfb-run -a .venv/bin/python batch.py <n> --proxy-file proxies.txt  # rotasi IP (anti rate-limit)
```

## Rotasi IP dengan proxy (opsional)

Turnstile **sudah lolos tanpa proxy** (berkat patchright). Proxy berguna untuk
**menghindari rate-limit per-IP** saat batch besar:

```bash
# ekstrak proxy dari package JSON (hanya yang portnya bisa dijangkau)
.venv/bin/python extract_proxies.py <package.json> proxies.txt

# uji proxy mana yang hidup
.venv/bin/python test_proxies.py

# batch dengan rotasi proxy
xvfb-run -a .venv/bin/python batch.py 20 --proxy-file proxies.txt
```

**Catatan penting:** sebagian proxy di package memakai port non-standar
(4145, 1080, 3128, 9090, …) yang mungkin **diblokir firewall sandbox ini**
(hanya 80/443/8080 yang bisa keluar). Proxy di port 80/443/8080 dipakai
otomatis oleh `extract_proxies.py`.

Proxy yang terbukti hidup di browser (datacenter): `172.105.120.179:443`,
`4.144.146.21:80`, `138.68.60.8:80`, `209.97.150.167:80`.

## Format akun (`accounts.txt`)

```
email:password:sso
```

## ⚠️ Batasan & catatan

- **xAI kadang mematikan pendaftaran email sementara** →
  `{"code":"account:email-signup-unavailable"}` (UI: *"Email sign-up isn't
  available right now"*). Bukan bug kita; tunggu & coba lagi.
- **Rate-limit per-IP**: setelah ~8-10 percobaan beruntun, email berhenti
  masuk. Beri jeda (jam-an). Menghantam lebih keras → blokir lebih lama.
- Jalur alternatif bila email diblokir: "Sign up with X/Google/Apple".

## Temp-mail

Memakai **[tempik](https://github.com/hirotomasato/tempik)** — layanan
disposable email self-hosted. Klien di `src/tempmail.py`.

## Integrasi 9router

`./run.sh sync` membuat node `openai-compatible` bernama `grok-xai` dengan
prefix `grok` dan meng-inject SSO sebagai kredensial.

## Kredit

- **[patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright)** — stealth
  Playwright (engine solver Turnstile).
- **[turnaround](https://github.com/Body-Alhoha/turnaround)** &
  **[Turnstile-Solver](https://github.com/Theyka/Turnstile-Solver)** — teknik
  solver Turnstile (halaman minimal + route fulfill).
- **[tempik](https://github.com/hirotomasato/tempik)** — temp-mail service.

## 🔗 Integrasi dengan proxyscrape-suite

`grok-suite` bisa memakai proxy hasil `proxyscrape-suite` untuk **rotasi IP**:

```bash
# 1. tarik + filter proxy yang bisa capai accounts.x.ai (otomatis)
./run.sh refresh-proxies

# 2. harvest dengan rotasi proxy (fallback otomatis kalau proxy lambat)
xvfb-run -a ./run.sh harvest 5

# tanpa proxy (langsung):
xvfb-run -a ./run.sh harvest 1 --no-proxy
```

`refresh-proxies` menjalankan proxyscrape-suite (fetch → check → filter xAI) dan
menyalin hasilnya ke `proxies_xai.txt`. `harvest` otomatis membacanya + mencoba
proxy berikutnya bila ada timeout.

**Temuan penting:** blokir `account:email-signup-unavailable` dari xAI bersifat
**global** (bukan per-IP) — proxy dengan egress berbeda pun tetap diblokir.
Jadi rotasi proxy **tidak menolong** saat xAI mematikan email-signup; tunggu
sampai diaktifkan kembali.
