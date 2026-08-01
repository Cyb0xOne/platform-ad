# Cara Submit Flag

Panduan submit flag ke game engine (ForcAD). Untuk peserta.

## Ringkas

```bash
curl -X PUT http://100.87.29.122:8080/flags/ \
  -H 'X-Team-Token: <TOKEN_TIM>' \
  -H 'Content-Type: application/json' \
  -d '["DSBVVFE0GWVBZVKYETCGR5S1XQIGLRB="]'
```

`PUT /flags/` di gameserver, header token tim, body **array JSON** berisi flag.

## Yang kamu butuhkan

- **Token tim** — kredensial submit tim kamu, dibagikan operator. Ini bukti "aku tim X".
  Tidak tampil di dashboard dan berganti tiap game di-reset.
- **Flag** curian dari vulnbox lawan — 31 karakter `[A-Z0-9]` diakhiri `=`, contoh
  `DSBVVFE0GWVBZVKYETCGR5S1XQIGLRB=`.

## Endpoint

```
PUT http://100.87.29.122:8080/flags/
```

| Bagian | Nilai |
|---|---|
| Header | `X-Team-Token: <token tim>` **dan** `Content-Type: application/json` |
| Body | array JSON string flag, mis. `["FLAG1=","FLAG2="]` |
| Balasan | HTTP 200 + array hasil per flag |

`100.87.29.122` = gameserver via Tailscale. Kalau kamu se-LAN dengan server,
`192.168.43.136` juga jalan.

## Submit banyak flag sekaligus (maks 100)

**Gabungkan flag ke satu request.** Jangan memberondong request terpisah — nginx
membalas `429 Too Many Requests` kalau request datang beruntun.

```bash
curl -X PUT http://100.87.29.122:8080/flags/ \
  -H 'X-Team-Token: <TOKEN_TIM>' \
  -H 'Content-Type: application/json' \
  -d '["FLAG1AAAAAAAAAAAAAAAAAAAAAAAAAA=","FLAG2AAAAAAAAAAAAAAAAAAAAAAAAAA="]'
```

Dari file (satu flag per baris), pecah per-100 dengan jeda antar-batch:

```bash
# flags.txt: satu flag per baris
split -l 100 flags.txt _batch_
for b in _batch_*; do
  jq -R -s 'split("\n") | map(select(length > 0))' "$b" \
  | curl -s -X PUT http://100.87.29.122:8080/flags/ \
      -H 'X-Team-Token: <TOKEN_TIM>' \
      -H 'Content-Type: application/json' -d @-
  echo; sleep 1
done
```

## Arti balasan

Balasan 200 berisi satu objek per flag: `[{"flag":"...","msg":"..."}]`. Pesan
diawali `[<flag>] `. Sumber: ForcAD `lib/helpers/exceptions.py` + `lib/storage/attacks.py`.

| Kondisi | Pesan |
|---|---|
| **Diterima, dapat poin** | `Flag accepted! Earned N flag points!` |
| Flag milik tim sendiri | `Flag is your own` |
| Sudah pernah dicuri (duplikat) | `Flag already stolen` |
| Salah / kedaluwarsa | `Flag is invalid or too old.` |
| Terlalu tua | `Flag is too old` |
| Service korban sedang DOWN | `Cannot submit flags while service is down` |
| Game belum jalan | `Game is not available.` |
| **Token salah** (bukan per-flag) | `{"error":"Invalid team token."}` |
| **Kena rate limit** | HTML `429 Too Many Requests` — gabungkan ke satu request |

## Umur flag

Flag dirotasi **tiap ronde** (`round_time` 120 detik) dan hanya valid selama
`flag_lifetime = 5` ronde ≈ **10 menit**. Curi lalu submit dalam jendela itu;
lewat dari situ balasannya `Flag is invalid or too old.`

## Token (operator)

Token **tidak** ada di dashboard `:8090` dan berganti tiap game di-reset. Operator
mengambil langsung dari DB engine lalu membagikan ke tim lewat kanal terpisah:

```bash
ssh adlab 'export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin; \
  docker exec -i adlab-dashboard python3' <<'PY'
import os, psycopg2
c = psycopg2.connect(os.environ['FORCAD_DSN']); cur = c.cursor()
cur.execute("SELECT name, token FROM teams ORDER BY id")
for n, t in cur.fetchall(): print(f"{n}\t{t}")
PY
```
