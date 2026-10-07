# 작업 지시서 — CompCore 대기 서버(B)의 작업 워커 끄기와 꼬인 작업 되살리기 (v0.11.0 반영)

> **받는 대상: 사내 서버 A · B 에 접근할 수 있는 AI 에이전트**
> 함께 받는 것: `compcore-v0.11.0.tar.gz` · `.sha256` (사람이 A · B 의 홈 폴더에 넣어 준다)
> 이 고침은 **v0.10.2 부터** 들어 있다. 더 새 번들을 받았으면 아래의 `v0.11.0` 을 그 번호로 바꿔 친다.
> 이 문서 하나로 충분하다 — 조사 스크립트는 부록에 있다.
> 작성 2026-10-07 · 근거: 저장소 `deploy/README_OPERATOR.md` 8.1c · `docs/adr/0007`

---

## 0. 당신이 할 일 (한 줄)

CompCore 의 **대기 서버(B)에서 작업 워커를 끄고**, 두 서버를 v0.11.0 으로 올린 뒤, **B 가 그동안 대신
처리한 작업의 결과 파일을 A 로 옮긴다.** 다시 돌려야 하는 작업은 목록으로 만들어 사람에게 넘긴다.

**멈춤 지점은 하나다** — 2단계(조사) 뒤에 보고하고 **승인을 받은 뒤** 3단계로 간다.
1단계(B 워커 끄기)는 승인 없이 바로 한다. 안전하고 되돌릴 수 있다.

---

## 1. 이 시스템을 모르는 채로 시작하지 않도록 — 최소한의 사실

| | |
|---|---|
| **무엇** | 부품 CAD · 지그 · 실험계획(DOE) 웹 플랫폼. FastAPI + PostgreSQL |
| **어떻게 도나** | `app.sif`(Apptainer) 안에서 돈다. systemd 유닛: `compcore`(앱) · `compcore-worker`(작업 워커) · `compcore-mcp` · `compcore-cleanup.timer` · `compcore-backup.timer` |
| **서버 둘** | **A = 주**(DB 주, 포탈이 여기로만 보낸다), **B = 대기**(DB 는 A 의 복제본, B 의 앱은 A 의 DB 를 본다). 공용 저장소(`/data`)는 없다 — 파일은 서버마다 따로 |
| **설치 위치** | 보통 `/home/<계정>/apps/compcore`. 실제 값은 `/etc/platform-instances/compcore.conf` 의 `INSTALL_DIR` |

### 무엇이 잘못돼 있었나 — 이걸 이해하면 나머지는 쉽다

```
          DB (A 에 하나, B 는 복제)          작업물 파일 (서버마다 따로)
          ┌──────────────────────┐         A: <A 설치>/filestore/{imports,jobs,doe}
 A 화면 ─▶│ jobs 표 = 작업 줄(큐)  │◀── A 워커   (올린 STEP 은 여기 있다)
          │                      │◀── B 워커   ← 이게 문제. B 도 같은 줄에서 집는다
          └──────────────────────┘         B: <B 설치>/filestore/{jobs,doe}
                                              (B 가 만든 결과는 여기만 있다)
```

- B 의 워커가 집은 작업은 **A 에 올린 STEP 을 못 찾아 실패**했거나,
- 성공했어도 **결과(STEP · glTF)가 B 에만 있어** A 화면에서 「작업물 파일이 저장소에 존재하지 않습니다」 다.
- 실험계획(DOE)은 B 가 만든 폴더가 B 에만 있다. A 에 옛 사본이 있으면 「내보내기」 가 **옛 설계점**을 해석으로 보낸다.

v0.10.2 부터는 **앞으로** B 의 워커가 꺼진 채로 있게 한다(`update` 해도 다시 안 켜진다). v0.11.0 에는
시험 규격 확장도 들어 있지만 이 작업과는 상관없고, **DB 마이그레이션은 없다**(v0.10.1 과 같은 0034). **이미 꼬인 것은
업데이트가 고치지 않는다** — 그래서 3 · 4 · 6 단계가 있다.

### 이 작업에서 하지 **않는** 것

| | 이유 |
|---|---|
| **DB 에 쓰기**(UPDATE · DELETE · INSERT) | 조회(SELECT)만 한다. 다시 돌리는 일은 사람이 화면에서 한다 |
| **B 의 filestore 지우기** | 복사만 한다. 원본 정리는 나중에 사람이 판단한다 |
| **실험계획 폴더(`filestore/doe/`) 옮기기** | A · B 에 서로 다른 때의 사본이 있을 수 있다. 파일 단위로 섞으면 표와 STEP 이 어긋난다. 「재생성」 으로 다시 만든다(6단계) |
| **A 의 워커 끄기** | A 가 일을 하는 서버다 |
| **`.env` · `/etc/platform-ha.conf` 고치기** | 이 작업과 관계없다 |
| **A 를 먼저 업데이트** | 순서는 늘 **B → A** |

---

## 2. 반드시 지킬 것 (하드 룰)

1. **명령마다 [A] · [B] 를 확인하고 친다.** 먼저 `hostname` 으로 지금 어느 서버인지 본다. 서버를 헷갈리면
   주 서버의 워커를 끄게 된다.
2. **`rm` · `mv` 를 쓰지 않는다.** 복사는 `rsync --ignore-existing` — 이미 있는 파일은 건드리지 않는다.
3. **`rsync` 는 미리보기(`-n`)를 먼저** 돌려 개수를 보고, 그 수를 보고에 적는다.
4. **두 서버의 워커가 동시에 켜진 순간을 만들지 않는다.** B 를 끄는 일이 늘 먼저다.
5. **비밀번호 · 토큰을 출력하거나 전달하지 않는다.** `.env` 를 통째로 읽지 않는다.
6. **`pkill` 로 프로세스를 죽이지 않는다.** 서비스는 `systemctl` 로만 다룬다.
7. **판단이 서지 않으면 멈추고 묻는다.** 특히 §4 의 「멈춰야 할 신호」.

---

## 3. 진행 순서

### 1단계 — [B] 역할 확인 후 워커 끄기 (지금 바로. 승인 불필요)

```bash
# [B]
hostname                                                     # B 의 호스트명 — 2단계에 쓴다
grep -m1 '^HA_ROLE=' /etc/platform-ha.conf                   # HA_ROLE=backup 이어야 한다
sudo -u postgres psql -tAc 'select pg_is_in_recovery()'      # t (대기 DB) 이어야 한다
systemctl is-active compcore-worker                          # 지금 상태 — 보고에 적는다
```

위 둘(`backup` · `t`)이 **맞을 때만** 끈다. 아니면 멈추고 보고한다(서버가 뒤바뀌었을 수 있다).

```bash
# [B]
sudo systemctl disable --now compcore-worker compcore-cleanup.timer
systemctl is-active compcore-worker        # inactive
systemctl is-enabled compcore-worker       # disabled
```

`disable --now` 는 돌던 작업을 끝까지 기다린 뒤 멈춘다(길면 몇 분). 멈추지 않고 오래 걸리면 기다린다 —
강제로 죽이지 않는다.

```bash
# [A] — A 의 워커는 켜져 있어야 한다
systemctl is-active compcore-worker        # active
```

### 2단계 — 조사 (읽기만. 여기까지 하고 보고 · 멈춤)

**[B]** 에서 세 줄만 본다:

```bash
# [B]
hostname
grep -o -- '--bind [^ ]*:/data/filestore' /etc/systemd/system/compcore.service   # B 의 filestore 경로
findmnt -n -o FSTYPE -T "$(grep -o -- '--bind [^ ]*:/data/filestore' /etc/systemd/system/compcore.service | sed -e 's/^--bind //' -e 's#:/data/filestore$##')"
```

**[A]** 에서 부록의 `cc_survey.sh` 를 돌린다(B 의 호스트명을 준다):

```bash
# [A]
sudo bash cc_survey.sh <B의 호스트명>
```

스크립트는 아무것도 바꾸지 않는다. 사람에게 넘길 목록 두 개를 `~/cc-fix/` 에 남긴다
(`rerun.txt` · `doe-regenerate.txt`) — 이 파일은 **옮겨 적지 않는다**, 서버에 두면 사람이 본다.

### ⚠️ 보고 형식 — **아래 14줄만** 채워서 준다

이 결과는 **사람이 손으로 옮겨 적어** 밖으로 나간다. 길면 그 자체가 문제다. 상세 출력을 붙이지 않는다.
`cc_survey.sh` 가 1 · 4 · 7~14 를 찍는다. 2 · 3 · 5 · 6 은 1단계 · B 조사에서 채운다.

```
CC-SURVEY v1  <오늘 날짜>
1  A역할      = <master> / DB주 <f>
2  B역할      = <backup> / DB대기 <t>
3  B워커전    = <active 또는 inactive — 1단계에서 끄기 전>
4  A워커      = <active>
5  B호스트    = <hostname>
6  B저장소    = <경로> (<ext4 등>)
7  A저장소    = <경로> (<ext4 등>)
8  A버전      = <v0.10.1 등>
9  작업호스트 = <A호스트 n / B호스트 m>  (inline 이 있으면 그대로 적는다)
10 B작업      = 완료 <n> · 실패 <n> · 도는중 <n>
11 A누락결과  = <B 작업의 결과 파일 중 A 에 없는 수>
12 A누락업로드 = <올린 STEP 중 A 에 없는 수>
13 B DOE      = <B 가 마지막으로 만든 실험계획 수>
14 목록       = ~/cc-fix/rerun.txt <줄수> · doe-regenerate.txt <줄수>
```

**값을 못 구했으면 `?` 로 둔다.** 추측해서 채우지 않는다.
**10 의 「도는중」 이 0 이 아니면** 3분 뒤 다시 본다 — A 의 워커가 넘겨받아 0 이 돼야 한다.

**여기서 멈춘다.** 사람의 승인을 받고 3단계로 간다.

### 3단계 — 업데이트: **B 먼저, 그다음 A** (승인 후)

```bash
# [B] — 번들이 홈 폴더에 있다
cd ~ && sha256sum -c compcore-v0.11.0.tar.gz.sha256
tar xzf compcore-v0.11.0.tar.gz && cd compcore-v0.11.0
sudo ./deploy.sh update
sudo ./deploy.sh worker                  # 「작업 워커: 끔 (대기 서버)」 이어야 한다
curl -s http://127.0.0.1:8060/api/health # "version":"v0.11.0" · "status":"ok"
```

`worker` 가 **「켬」** 으로 나오면 `sudo ./deploy.sh worker off` 를 한 번 치고 다시 확인한다(한 번 치면
기억한다). 그 사실을 보고에 적는다.

```bash
# [A] — B 가 끝난 뒤에
cd ~ && sha256sum -c compcore-v0.11.0.tar.gz.sha256
tar xzf compcore-v0.11.0.tar.gz && cd compcore-v0.11.0
sudo ./deploy.sh update
sudo ./deploy.sh worker                  # 「작업 워커: 켬」
curl -s http://127.0.0.1:8060/api/health # v0.11.0 · ok
```

### 4단계 — [B → A] B 가 만든 파일을 A 로 복사 (승인 후)

**[B] 에서, 운영 계정으로(sudo 없이)** 친다 — 복사된 파일이 A 에서도 운영 계정 것이 되게.
`<B저장소>` · `<A저장소>` 는 2단계의 6 · 7 줄, `<A>` 는 A 의 IP, `<계정>` 은 운영 계정.

```bash
# [B] 미리보기 — 개수만 본다. 아무것도 안 바뀐다
rsync -an --ignore-existing --itemize-changes <B저장소>/jobs/    <계정>@<A>:<A저장소>/jobs/    | grep -c '^<f'
rsync -an --ignore-existing --itemize-changes <B저장소>/imports/ <계정>@<A>:<A저장소>/imports/ | grep -c '^<f'
```

```bash
# [B] 실제 복사 — 이미 있는 파일은 건너뛴다
rsync -a --ignore-existing <B저장소>/jobs/    <계정>@<A>:<A저장소>/jobs/
rsync -a --ignore-existing <B저장소>/imports/ <계정>@<A>:<A저장소>/imports/
```

- `imports/` 가 B 에 없다는 오류가 나면 정상이다(B 화면에서 올린 사람이 없었다) — 그 줄만 건너뛴다.
- A 계정의 비밀번호를 물으면 **사람에게 입력을 부탁한다.** 비밀번호를 받아 적지 않는다.
- **서버끼리 ssh 가 안 되면** 묶어서 사람이 옮긴다:
  ```bash
  # [B]
  tar czf ~/cc-from-b.tgz -C <B저장소> jobs imports
  # (사람이 A 로 옮긴 뒤) [A], 운영 계정으로 — 이미 있는 파일은 덮지 않는다
  tar xzf ~/cc-from-b.tgz --skip-old-files -C <A저장소>
  ```

### 5단계 — [A] 확인

```bash
# [A]
sudo bash cc_survey.sh <B의 호스트명>     # 11 · 12 줄이 0 이어야 한다
```

### 6단계 — 사람에게 넘길 것 (화면에서 할 일)

`[A] ~/cc-fix/` 의 두 목록이다. **당신은 화면 작업을 하지 않는다** — 목록이 있다는 것과 줄 수만 보고한다.

| 목록 | 사람이 화면에서 할 일 |
|---|---|
| `rerun.txt` — B 에서 **실패한** 작업(날짜 · 종류 · 작업 이름 · 오류) | 종류가 `cad` 면 그 작업의 해당 버전에서 「이 버전으로 복원」, `jig` 면 「부품에서 지그 생성」 을 다시, `doe` 면 그 DOE 에서 「남은 설계점 이어서 생성」. 이미 A 에서 다시 돌린 것은 건너뛴다 |
| `doe-regenerate.txt` — B 가 **마지막으로 만든** 실험계획(이름 · 설계점 수 · 내보낸 날) | DOE 화면에서 **「재생성」.** A 화면에 정상으로 보여도 한다(옛 사본일 수 있다). 「내보낸 날」 이 있으면 재생성 뒤 **「공유 폴더로 내보내기」 를 다시** 하고, 해석(SimEngBay) 쪽에 그 스터디를 다시 돌려 달라고 알린다 |

---

## 4. 멈춰야 할 신호

아래 중 하나라도 해당하면 **작업을 중단하고 사람에게 보고**한다.

| 신호 | 왜 |
|---|---|
| B 의 `HA_ROLE` 이 `backup` 이 아니거나 `pg_is_in_recovery` 가 `t` 가 아니다 | 서버가 뒤바뀌었다(전환 중일 수 있다). 주 서버의 워커를 끄게 된다 |
| A 의 DB 가 주(`f`)가 아니다 | 조사 쿼리가 엉뚱한 DB 를 본다 |
| A · B 의 저장소 종류(6 · 7 줄)가 `nfs` 등 네트워크다 | 이 지시서의 전제(서버마다 따로)가 아니다 |
| 9 줄에 **A · B 말고 다른 호스트**가 보인다(`inline` 은 빼고 — 워커 없이 요청 안에서 돈 작업이다) | 세 번째 워커가 있다. 그것도 같은 문제다 |
| 업데이트 뒤 B 의 `worker` 가 「켬」 이고 `worker off` 로도 안 꺼진다 | 배포 스크립트가 예상과 다르다 |
| `update` 가 실패하거나 health 가 `ok` 가 아니다 | `journalctl -u compcore -n 50` 의 마지막 몇 줄만 보고한다 |
| rsync 미리보기 수와 실제로 늘어난 수가 다르다, 또는 5단계에서 11 · 12 가 0 이 아니다 | 복사가 불완전하다 |
| 예상과 **다른 구조**를 발견했다 | 추측해서 진행하지 않는다 |

---

## 5. 끝난 뒤 보고할 것

이것도 손으로 옮겨 적는다 — 짧게.

```
CC-FIX v1  <오늘 날짜>
A B워커끔    = 완료 (disabled · inactive)
B B업데이트  = v0.11.0 · worker 끔
C A업데이트  = v0.11.0 · worker 켬
D 복사       = jobs <미리보기 수>/<실제 수> · imports <미리보기 수>/<실제 수>
E 재확인     = A누락결과 0 · A누락업로드 0
F 사람에게   = rerun <줄수> · doe-regenerate <줄수>  (A ~/cc-fix/)
G 원본       = B filestore 그대로 둠
```

실패한 항목이 있으면 그 줄만 `실패` 로 적고 이유를 한두 줄 덧붙인다.

---

## 부록 — `cc_survey.sh` (A 에서 실행. 읽기만 한다)

아래를 그대로 `cc_survey.sh` 로 저장해 `sudo bash cc_survey.sh <B의 호스트명>` 으로 돌린다.

```bash
#!/usr/bin/env bash
# CompCore — 대기 서버(B)가 집은 작업 조사. **읽기만 한다. 아무것도 바꾸지 않는다.**
# 쓰는 법(주 서버 A 에서):  sudo bash cc_survey.sh <B의 호스트명>
set -u
B="${1:?B 의 호스트명을 주세요 — B 에서 hostname 으로 본다}"
SLUG="${SLUG:-compcore}"
DB="${DB:-$SLUG}"
UNIT="/etc/systemd/system/$SLUG.service"
OWNER="${SUDO_USER:-$USER}"
OUT="$(getent passwd "$OWNER" | cut -d: -f6)/cc-fix"
mkdir -p "$OUT" && chown "$OWNER:" "$OUT"

q() { sudo -u postgres psql -d "$DB" -tAX -c "$1"; }

FS="$(grep -o -- '--bind [^ ]*:/data/filestore' "$UNIT" | head -1 | sed -e 's/^--bind //' -e 's#:/data/filestore$##')"
[ -d "$FS" ] || { echo "filestore 경로를 못 찾았습니다($UNIT) — 멈추고 보고하세요"; exit 1; }

ROLE="$(grep -m1 '^HA_ROLE=' /etc/platform-ha.conf 2>/dev/null | cut -d= -f2)"
RECOV="$(q 'select pg_is_in_recovery()')"
WORKER="$(systemctl is-active "$SLUG-worker" 2>/dev/null)"
FSTYPE="$(findmnt -n -o FSTYPE -T "$FS" 2>/dev/null)"
VER="$(curl -s http://127.0.0.1:8060/api/health | grep -o '"version":"[^"]*"' | cut -d'"' -f4)"
HOSTS="$(q "select h || ' ' || n from (select split_part(worker_id, ':', 1) as h, count(*) as n from jobs where worker_id is not null group by 1) t order by h" | paste -sd'/' -)"

cnt() { q "select count(*) from jobs where split_part(worker_id, ':', 1) = '$B' and status = '$1'"; }
DONE="$(cnt done)"; FAILED="$(cnt failed)"; RUNNING="$(cnt running)"

# B 작업의 결과 파일 중 A 에 없는 것
MISS_OUT=0; : > "$OUT/missing-results.txt"
while IFS= read -r p; do
    [ -n "$p" ] || continue
    [ -e "$FS/$p" ] || { MISS_OUT=$((MISS_OUT + 1)); echo "$p" >> "$OUT/missing-results.txt"; }
done < <(q "select a.path from artifacts a join jobs j on j.id = a.job_id where split_part(j.worker_id, ':', 1) = '$B'")

# 올린 STEP 중 A 에 없는 것(B 화면에서 올렸다면 B 에 있다)
MISS_UP=0; : > "$OUT/missing-uploads.txt"
while IFS= read -r p; do
    [ -n "$p" ] || continue
    [ -e "$FS/$p" ] || { MISS_UP=$((MISS_UP + 1)); echo "$p" >> "$OUT/missing-uploads.txt"; }
done < <(q "select path from artifacts where kind = 'import_step'")

# 사람에게 넘길 목록
q "select j.created_at::date || ' | ' || j.kind || ' | ' || coalesce(w.name, '-') || ' | ' ||
          left(regexp_replace(coalesce(j.error, ''), '\s+', ' ', 'g'), 120)
     from jobs j left join works w on w.id = j.work_id
    where split_part(j.worker_id, ':', 1) = '$B' and j.status = 'failed'
    order by j.created_at" > "$OUT/rerun.txt"
q "select s.name || ' | 설계점 ' || s.point_count || ' | 내보낸 날 ' || coalesce(to_char(s.exported_at, 'YYYY-MM-DD'), '-')
     from doe_studies s join jobs j on j.id = s.job_id
    where split_part(j.worker_id, ':', 1) = '$B'
    order by s.created_at" > "$OUT/doe-regenerate.txt"
chown "$OWNER:" "$OUT"/*.txt

cat <<EOF
############ 전달용 — 1 · 4 · 7~14 줄 ############
1  A역할      = ${ROLE:-?} / DB주 ${RECOV:-?}
4  A워커      = ${WORKER:-?}
7  A저장소    = $FS (${FSTYPE:-?})
8  A버전      = ${VER:-?}
9  작업호스트 = ${HOSTS:-?}
10 B작업      = 완료 ${DONE:-?} · 실패 ${FAILED:-?} · 도는중 ${RUNNING:-?}
11 A누락결과  = $MISS_OUT
12 A누락업로드 = $MISS_UP
13 B DOE      = $(grep -c . "$OUT/doe-regenerate.txt")
14 목록       = $OUT/rerun.txt $(grep -c . "$OUT/rerun.txt") · doe-regenerate.txt $(grep -c . "$OUT/doe-regenerate.txt")
############################ 여기까지 ############################
EOF
```
