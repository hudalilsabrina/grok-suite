# Grok Suite — Status & Temuan Lapangan

## ✅ Terbukti end-to-end (akun jadi + inference jalan)

```
inbox   ratnaayu26@xentranetwork.me        (tempik)
kode    "059187" masuk ~6 detik            (subject "SpaceXAI confirmation code: NNN-NNN")
form    "Complete your sign up" muncul
Turnstile 816 char (patchright) → di-inject ke halaman Camoufox
POST /api/auth/sign-up/create-account → 200
        {"session":{"userId":"…","email":"ratnaayu26@…"}}
cookies sso, sso-rw, last-logged-in-with   → SUKSES
```

Lalu lewat grok2api (egress residensial):

```
POST /v1/chat/completions  model=grok-chat-fast
→ {"content":"GROK-LIVE"}  status 200
```

| Komponen | Status | Catatan |
|---|---|---|
| Camoufox (Firefox) tembus gate signup | ✅ | Chromium/Playwright sering ditolak di titik yang sama |
| Kode OTP via **tempik** | ✅ | masuk ~6 detik |
| `castleRequestToken` | ✅ wajib | di-generate halaman asli; tanpa itu email tidak dikirim |
| Turnstile | ✅ | Camoufox 0 token → **patchright** 816 char → inject |
| Submit form akhir | ✅ **via API**, bukan klik tombol | lihat di bawah |
| SSO → grok2api pool | ✅ | provider `grok_web` |
| Inference | ✅ | **wajib egress residensial** (grok.com 403 dari IP DC) |

## 🔑 Temuan kunci

1. **Klik `Complete sign up` tidak memicu request apa pun** saat token Turnstile
   di-inject dari luar — token ada di DOM tapi tidak masuk React state. Yang
   bekerja: `fetch('/api/auth/sign-up/create-account', {credentials:'include', ...})`
   langsung dari konteks halaman.
2. **Camoufox tidak bisa Turnstile** (Firefox: `window.turnstile` undefined),
   **patchright bisa** (816 char). Kombinasi keduanya yang menang.
3. **grok.com blokir IP datacenter** (403, bahkan dengan SSO valid); lewat
   residensial 200. Pasang egress node di grok2api + assign akun.

## 🔴 Gate `email-signup-unavailable` (bukan bug kita)

```
POST /api/auth/send-verification-code → 400
{"code":"account:email-signup-unavailable"}
UI: "Email sign-up isn't available right now. Sign up another way."
```

**Bukan soal domain.** Uji A/B pada menit yang sama:

| Email | Hasil saat gate tutup |
|---|---|
| `@fantech.tech` (tempik) | `account:email-signup-unavailable` |
| `@gmail.com` (kontrol) | `account:email-signup-unavailable` (identik) |
| `@<domain tanpa MX>` | `account:email-signup-unavailable` (identik) |
| `@maxxspace.com` (mail.tm) | `form-invalid:disposable-email` ← ini blokir domain |

Dan saat gate buka, tempik **dan** gmail dua-duanya lolos. Jadi pembedanya
**waktu** dan **egress**, bukan domain. `mail.tm` memang masuk daftar hitam xAI;
tempik tidak.

**Pola buka-tutup:** teramati jendela ±beberapa menit sampai ±30 menit
(mis. 04:08–04:10, 04:30, 05:03–05:36, 09:18 UTC), sisanya tutup.

**Rate limit terpisah:** `Too many code requests. Please wait a few minutes` —
hambatan per-IP; retry rapat memperpanjang blokir. Beri jeda.

## 🔄 Proxy

- Proxy residensial **menaikkan peluang** saat gate buka (uji A/B: 2/2 sukses
  lewat residensial sementara IP DC dapat 400 di menit yang sama).
- Proxy gratis datacenter: lolos `curl` tapi sering gagal di browser
  (`ERR_TIMED_OUT` / `CONNECTION_RESET`).
- Rotasi per-request **mematahkan `cf_clearance`** di tengah flow — sisakan
  sebagian attempt tanpa proxy.

## Struktur

```
grok.py               CLI (harvest / list / probe / sync / test)
harvest_camoufox.py   engine harvest (Camoufox + submit via API)
ts_solve_cli.py       solver Turnstile (patchright)
src/common.py         helper bersama
src/mail.py           klien temp-mail (tempik + mail.tm)
src/turnstile.py      pembungkus solver + inject token
setup.sh / setup.ps1  instalasi (Linux-macOS / Windows)
grok.bat              wrapper Windows
```

## Langkah berikutnya

1. Nambah akun: `grok.py harvest -n 5 --stop-on-gate` (Windows: `grok.bat ...`).
   Biarkan retry pelan; jangan hammer.
2. Untuk batch besar, siapkan **pool egress residensial** dan assign akun ke
   node-nya di grok2api.
3. Jalankan dari **VPS** kalau mau memakai proxy di port non-standar.
