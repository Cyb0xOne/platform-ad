# Skema Platform A/D Internal

Skema visual pendamping [`plan.md`](plan.md). Lima diagram: arsitektur, jaringan, alur satu tick,
anatomi adapter, dan alur serang. Semua pakai Mermaid (render langsung di GitHub/VS Code).

---

## 1. Arsitektur keseluruhan

Empat lapis di satu host. Yang perlu diperhatikan: **checker tidak jalan sendiri** — dia hidup di
dalam container celery, dan dari sanalah semua panggilan keluar.

```mermaid
flowchart TB
    subgraph HOST["Server 192.168.43.136 - Arch, 8 core / 15 GB"]

        subgraph DK["Docker bridge"]
            subgraph FORCAD["LAPIS 1: Engine ForcAD"]
                CEL["celery worker<br/>berisi direktori checkers/<br/>+ adapter buatan sendiri"]
                ENG["engine tick / ronde"]
                RCV["flag receiver"]
                WEB["scoreboard :8080<br/>admin panel /admin/"]
                PG[("postgres")]
                RD[("redis")]
                MQ[("rabbitmq")]
            end

            subgraph SIDE["Sidecar ENOWARS"]
                ENO["enochecker3<br/>service HTTP"]
                MON[("mongodb<br/>ChainDB")]
            end

            subgraph D4["LAPIS 4: Dashboard custom"]
                API["Backend FastAPI"]
                SPA["Frontend SPA"]
            end
        end

        subgraph VIRT["libvirt - virbr0"]
            subgraph VM1["LAPIS 2: VM team1 - 3 GB / 2 vCPU"]
                S1A["svc saarCTF"]
                S1B["svc FAUST"]
                S1C["svc ENOWARS"]
            end
            subgraph VM2["LAPIS 2: VM team2 - 3 GB / 2 vCPU"]
                S2A["svc saarCTF"]
                S2B["svc FAUST"]
                S2C["svc ENOWARS"]
            end
        end
    end

    CEL -->|"check / put / get"| VM1
    CEL -->|"check / put / get"| VM2
    CEL -->|"HTTP putflag / getflag"| ENO
    ENO --- MON
    CEL -->|"state saarCTF<br/>DB index terpisah"| RD
    MQ --- CEL
    ENG --- PG
    ENG --- MQ
    RCV -->|"validasi flag"| PG
    WEB --- PG
    API -->|"READ-ONLY"| PG
    API -->|"aksi admin<br/>via control.py / celery"| ENG
    SPA --- API

    style CEL fill:#fde68a,stroke:#b45309,color:#000
    style VIRT fill:#dbeafe,stroke:#1d4ed8,color:#000
    style D4 fill:#dcfce7,stroke:#15803d,color:#000
    style SIDE fill:#fee2e2,stroke:#b91c1c,color:#000
```

**LAPIS 3 (adapter)** tidak punya kotak sendiri di gambar — dia hidup *di dalam* `celery worker`
(kotak kuning). Itulah satu-satunya kode glue yang kita tulis untuk unifikasi.

---

## 2. Jaringan: dua bridge yang harus disambung

Ini titik rawan yang paling gampang bikin buntu berjam-jam.

```mermaid
flowchart LR
    subgraph B1["docker0 - contoh 172.17.0.0/16"]
        CEL["container celery<br/>tempat adapter jalan"]
    end
    subgraph B2["virbr0 - contoh 192.168.122.0/24"]
        V1["VM team1<br/>IP statis"]
        V2["VM team2<br/>IP statis"]
    end

    CEL -.->|"DIBLOKIR default<br/>iptables bawaan libvirt"| V1
    CEL ==>|"setelah rule forward<br/>docker0 ke virbr0"| V2

    GATE{{"GATE Fase 0.5<br/>docker exec celery curl IP-VM PORT<br/>harus berhasil untuk KEDUA VM"}}
    V1 --- GATE
    V2 --- GATE

    style GATE fill:#fef08a,stroke:#a16207,color:#000
```

IP kedua VM inilah yang masuk ke `teams[].ip` di `config.yml`. Selama gate ini belum lolos,
**jangan tulis satu baris adapter pun** — semua checker akan balik `DOWN 104` dan kamu akan
men-debug adapter untuk masalah yang sebenarnya ada di iptables.

---

## 3. Alur satu tick: dari mana `flag_id` berasal

Diagram paling penting. Yang dibawa ke GET selalu `private_flag_data` — **kanal mana yang mengisinya
ditentukan tag `checker_type`**: tanpa tag berarti stdout (privat, default kita), `pfr` berarti stdout
tampil publik dan stderr yang jadi state privat.

```mermaid
sequenceDiagram
    autonumber
    participant CEL as celery ForcAD
    participant AD as adapter
    participant LIB as checker asli
    participant SVC as service di VM tim
    participant PG as postgres

    rect rgb(240, 245, 255)
    Note over CEL,PG: Ronde N
    CEL->>AD: check HOST
    AD->>LIB: check_service / check_integrity
    LIB->>SVC: probe
    SVC-->>LIB: sehat
    AD-->>CEL: exit 101 OK
    end

    rect rgb(255, 250, 235)
    CEL->>AD: put HOST FLAG_ID FLAG VULN
    Note right of AD: tick = now dikurangi start_time<br/>dibagi round_time
    AD->>AD: INJEKSI FLAG<br/>monkeypatch get_flag<br/>agar pakai FLAG dari ForcAD
    AD->>LIB: place_flag tick / store_flags team tick
    LIB->>SVC: simpan flag
    SVC-->>LIB: id internal
    AD-->>CEL: stdout satu baris JSON<br/>tick + id internal<br/>exit 101
    CEL->>PG: simpan sesuai tag checker_type
    Note over PG: tanpa tag - stdout jadi private_flag_data, tidak tampil<br/>pfr - stdout jadi public_flag_data di scoreboard,<br/>stderr jadi private_flag_data
    end

    rect rgb(240, 255, 245)
    Note over CEL,PG: Ronde N+k, selama masih dalam flag_lifetime
    CEL->>AD: get HOST FLAG_ID FLAG VULN
    AD->>AD: baca tick dari FLAG_ID
    AD->>LIB: check_flag tick / retrieve_flags team tick
    LIB->>SVC: ambil flag
    SVC-->>LIB: flag
    alt flag cocok
        AD-->>CEL: exit 101 OK
    else flag hilang
        AD-->>CEL: exit 102 CORRUPT
    else service diam
        AD-->>CEL: exit 104 DOWN
    end
    CEL->>PG: catat SLA
    end
```

**Konsekuensi desain** — default ForcAD sudah privat, jadi state PUT→GET aman ditulis apa adanya di
stdout. Tag `pfr` dipakai hanya kalau service memang harus mempublikasikan flag id ke penyerang
(meniru perilaku asli saarCTF/ENOWARS); saat itu state privat pindah ke stderr.

---

## 4. Anatomi lapis adapter

Satu bentuk panggilan ForcAD, tiga cara berbeda menerjemahkannya. Perbedaan terpenting: **siapa
yang membuat flag**.

```mermaid
flowchart TB
    IN["ForcAD memanggil:<br/>checker.py AKSI HOST FLAG_ID FLAG VULN"]

    IN --> A1
    IN --> A2
    IN --> A3

    subgraph L3["LAPIS 3 - adapter buatan sendiri, di dalam container celery"]
        A1["adapter saar"]
        A2["adapter faust"]
        A3["adapter eno"]
    end

    A1 -->|"monkeypatch<br/>ServiceInterface.get_flag"| G1["gamelib<br/>store_flags / retrieve_flags<br/>check_integrity"]
    A2 -->|"monkeypatch<br/>checkerlib.get_flag<br/>JANGAN pakai run_check"| G2["checkerlib<br/>place_flag / check_flag<br/>check_service"]
    A3 -->|"flag ikut di payload<br/>tanpa patch"| G3["POST JSON ke<br/>enochecker3 HTTP"]

    G1 --- R[("redis<br/>state antar-tick")]
    G2 --- F[("volume per-tim<br/>_team_state.json")]
    G3 --- M[("mongodb<br/>ChainDB")]

    G1 --> OUT
    G2 --> OUT
    G3 --> OUT

    OUT["Normalisasi ke exit code ForcAD<br/>101 OK · 102 CORRUPT · 103 MUMBLE · 104 DOWN · 110 CHECKER_ERROR<br/>+ satu baris flag_id di stdout"]

    style L3 fill:#fde68a,stroke:#b45309,color:#000
    style OUT fill:#dcfce7,stroke:#15803d,color:#000
    style A3 fill:#fee2e2,stroke:#b91c1c,color:#000
```

Pemetaan status per framework:

| Kondisi | saarCTF | FAUST | ENOWARS | → ForcAD |
|---|---|---|---|---|
| sehat | tanpa exception | `CheckResult.OK` | `OK` | **101** |
| flag hilang | `FlagMissingException` | `FLAG_NOT_FOUND` | flag tidak cocok | **102** |
| perilaku salah | `MumbleException` | `FAULTY` / `RECOVERING` | `MUMBLE` | **103** |
| tak terhubung | `OfflineException` | `DOWN` | `OFFLINE` | **104** |
| bug checker | exception lain | exception | `INTERNAL_ERROR` | **110** |

---

## 5. Alur serang & skor

```mermaid
sequenceDiagram
    autonumber
    participant T1 as Tim 1 - penyerang
    participant V2 as Service tim 2 di VM team2
    participant RCV as flag receiver ForcAD
    participant PG as postgres
    participant DSH as dashboard custom

    T1->>V2: jalankan exploit
    V2-->>T1: flag curian
    T1->>RCV: submit flag
    RCV->>PG: cek - masih dalam flag_lifetime?<br/>bukan flag sendiri?<br/>belum pernah disubmit?
    alt valid
        PG-->>RCV: diterima
        RCV->>PG: poin serang tim1 naik<br/>poin tim2 turun
    else ditolak
        PG-->>RCV: kedaluwarsa / duplikat / milik sendiri
    end
    DSH->>PG: query READ-ONLY
    PG-->>DSH: skor, SLA, riwayat curi-flag
```

Sisi bertahan berjalan paralel: kalau service tim 2 mati atau salah di-patch, checker dari
[diagram 3](#3-alur-satu-tick-dari-mana-flag_id-berasal) mengembalikan 103/104 dan **SLA tim 2 turun**
— jadi menambal dengan cara mematikan service tetap merugikan.

---

## 6. Urutan fase & gate

Tiap panah bercabang adalah titik di mana kamu berhenti dan memverifikasi sebelum lanjut.

```mermaid
flowchart TD
    START(["Mulai"]) --> CHK{"id reky memuat grup libvirt?<br/>virsh -c qemu:///system list jalan?"}
    CHK -->|"tidak"| FB["FALLBACK: batalkan rencana VM<br/>pakai container per tim<br/>di satu bridge adnet"]
    CHK -->|"ya"| P0["Fase 0<br/>base image + virt-clone jadi 2 VM<br/>ForcAD + example service"]
    FB --> P0

    P0 --> V0{"scoreboard :8080 tampil?<br/>tick jalan?<br/>example service OK?"}
    V0 -->|"belum"| P0
    V0 -->|"ya"| G05{"GATE Fase 0.5<br/>docker exec celery curl IP-VM<br/>berhasil di KEDUA VM?"}

    G05 -->|"gagal"| FWD["tambah rule forward<br/>docker0 ke virbr0"] --> G05
    G05 -->|"lolos"| P1["Fase 1<br/>rebuild image celery + dependency<br/>sidecar enochecker + mongo<br/>deploy 3 service ke 2 VM<br/>tulis 3 adapter"]

    P1 --> V1{"GATE per adapter<br/>put lalu get manual dari CLI<br/>exit 101 dua kali?"}
    V1 -->|"gagal"| P1
    V1 -->|"lolos"| P2["Fase 2 - jalur serang<br/>exploit asli curi flag, submit, skor bergerak"]

    P2 --> P3["Fase 3 - dashboard read-only"]
    P3 --> P4["Fase 4 - panel admin"]
    P4 --> P5["Fase 5 - perluasan framework<br/>blitz, omctf, service lain"]

    style CHK fill:#fecaca,stroke:#b91c1c,color:#000
    style G05 fill:#fef08a,stroke:#a16207,color:#000
    style V1 fill:#fef08a,stroke:#a16207,color:#000
    style FB fill:#e5e7eb,stroke:#6b7280,color:#000
```
