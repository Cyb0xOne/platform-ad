# ad-platform

Platform **Attack-Defense (A/D) internal** untuk latihan tim — satu ekosistem terpadu
(dashboard + checker + scoring) yang menyatukan soal dari banyak framework berbeda.

## Ide inti
Bank soal A/D (`~/workspaces/cylab/ctf/attack-defense/`) berisi service dari **5 framework
checker yang tidak kompatibel** (FAUST `checkerlib`, saarCTF `gamelib`, ENOWARS `enochecker`,
blitz `check.py`, omctf `checker.py`). Platform ini menyatukannya dengan cara:

1. **Adopsi [ForcAD](https://github.com/pomo-mondreganto/ForcAD)** sebagai game engine
   (tick, flag, submit, scoreboard, scheduler checker).
2. **Lapisan adapter checker** — menjembatani checker asli tiap service ke format ForcAD.
3. **Dashboard custom** — scoreboard + detail serang/bertahan + panel kontrol admin, membaca
   database ForcAD.

Target deploy: server `reky@192.168.43.136` (Docker 29.4, 8c/15GB). MVP: 1 service per framework, 2 tim.

## Struktur
```
adapters/   # adapter checker per framework (saar/faust/eno) → format ForcAD
dashboard/  # app dashboard custom (backend FastAPI + frontend)
deploy/     # skrip deploy ke server (git-driven; PATH SSH eksplisit)
forcad/     # config.yml & override untuk engine ForcAD
docs/       # docs/plan.md — desain lengkap (untuk disempurnakan Ultraplan)
```

## Status
🚧 Bootstrap. Desain lengkap ada di [`docs/plan.md`](docs/plan.md), menunggu penyempurnaan
via Ultraplan sebelum implementasi. Fase awal: Fase 0 = hidupkan ForcAD + 2 tim di server.

## Catatan ops
- Shell SSH non-interaktif di server **PATH kosong** → skrip via SSH wajib set PATH / `bash -lc`.
- `docker` di server ada di `/usr/sbin/docker`; user `reky` di grup `docker` (tanpa sudo).
