# croll_MFDS 프로젝트

## 개요

식품의약품안전처(MFDS) 및 관련 기관의 공지사항을 자동 크롤링하여 웹 대시보드로 제공하는 서비스.

- **라이브 URL**: https://croll-mfds.pages.dev/
- **GitHub**: https://github.com/barnanacle/croll_mfds
- **배포**: Cloudflare Pages (GitHub main 브랜치 push 시 자동 배포)

---

## 아키텍처

```
GitHub Actions (매일 KST 05:00)
  → croll_mfds.py 실행 (Python 3.12)
  → data.json 생성
  → git commit & push
  → Cloudflare Pages 자동 배포
  → index.html이 data.json을 fetch하여 렌더링
```

### 핵심 흐름

1. **크롤링**: GitHub Actions가 cron 스케줄(`0 20 * * *`, UTC 20:00 = KST 05:00)로 `croll_mfds.py` 실행
2. **데이터 저장**: 크롤링 결과를 `data.json`에 JSON 형식으로 저장
3. **자동 커밋**: 변경사항이 있을 때만 `data.json`, `crawl_log.txt`를 커밋 & 푸시
4. **배포**: main 브랜치에 push되면 Cloudflare Pages가 자동으로 정적 사이트 배포
5. **웹 표시**: `index.html`이 `data.json`을 fetch하여 카드 형태로 렌더링

---

## Codex/Claude 교대 작업 규칙

이 저장소의 프로젝트 설명과 운영 규칙은 `CLAUDE.md`를 기준 문서(source of truth)로 유지한다. Codex용 `AGENTS.md`는 이 문서를 읽도록 안내하는 얇은 진입점이며, 프로젝트 세부 내용을 중복해서 늘리지 않는다.

1. **작업 시작 전 동기화**: `git fetch origin` 후 `git status --short --branch`로 현재 브랜치와 ahead/behind 상태를 확인한다. `main`이 `origin/main`보다 뒤처져 있으면 코드 수정 전에 `git merge --ff-only origin/main` 또는 동등한 fast-forward 방식으로 먼저 맞춘다.
2. **브랜치 분리**: 기능 수정과 UI/크롤러 변경은 `codex/<topic>` 또는 `claude/<topic>` 같은 작업 브랜치에서 진행한다. `main` 직접 수정은 사용자가 명시적으로 요청한 긴급 수정이나 자동 크롤 커밋 처리에 한정한다.
3. **자동 데이터 커밋 주의**: `data.json`과 `crawl_log.txt`는 GitHub Actions가 매일 갱신한다. 코드 변경 커밋에 이 두 파일의 우발적 로컬 크롤 결과를 섞지 말고, 데이터 갱신이 필요한 작업일 때만 의도적으로 포함한다.
4. **배포 직전 재확인**: `main`에 병합하거나 push하기 직전에 다시 `git fetch origin`과 `git status --short --branch`를 확인한다. 원격에 새 자동 크롤 커밋이 생겼다면 먼저 rebase/fast-forward 후 push한다.
5. **핸드오프 기록**: 작업 종료 메시지에는 브랜치, 변경 파일, 검증 명령, 배포 여부, 남은 확인사항을 간단히 남긴다. 다른 에이전트가 이어받을 때 같은 조사를 반복하지 않게 하기 위함이다.

---

## 파일 구조

```
croll_MFDS/
├── .github/workflows/
│   └── crawl.yml          # GitHub Actions 워크플로우 (자동 크롤링 + 커밋)
├── croll_mfds.py          # 크롤러 메인 스크립트
├── index.html             # 웹 프론트엔드 (정적 SPA)
├── index_example.html     # 이전 버전 백업
├── data.json              # 크롤링 결과 데이터 (자동 생성/갱신)
├── crawl_log.txt          # 크롤링 실행 로그 (자동 append)
├── requirements.txt       # Python 의존성
├── .gitignore
├── CLAUDE.md              # 프로젝트 기준 문서
└── AGENTS.md              # Codex용 진입점 (CLAUDE.md 참조)
```

---

## 크롤링 대상 (9개 소스)

| 구분 | URL 패턴 | 파싱 함수 |
|------|-----------|-----------|
| 서울지방 식약청 | mfds.go.kr/brd/m_824 | `process_mfds()` |
| 경인지방 식약청 | mfds.go.kr/brd/m_841 | `process_mfds()` |
| 부산지방 식약청 | mfds.go.kr/brd/m_765 | `process_mfds()` |
| 대전지방 식약청 | mfds.go.kr/brd/m_891 | `process_mfds()` |
| 광주지방 식약청 | mfds.go.kr/brd/m_875 | `process_mfds()` |
| 대구지방 식약청 | mfds.go.kr/brd/m_857 | `process_mfds()` |
| 대한화장품협회 | kcia.or.kr/home/notice | `process_kcia()` |
| 식약처 공무원지침서 | mfds.go.kr/brd/m_1059 | `process_mfds()` |
| 식약처 민원인안내서 | mfds.go.kr/brd/m_1060 | `process_mfds()` |

### 크롤링 로직 상세

- **필터링**: 현재 월 + 지난 월의 게시물만 수집 (연도 인식 — 1월↔12월 경계 안전)
- **상세 내용**: 각 게시물의 상세 페이지까지 진입하여 본문 텍스트 추출
- **재시도**: 최대 2회, backoff (1s → 2s), 5xx 에러 시 자동 재시도
- **요청 간격**: 0.5초 딜레이 (서버 부하 방지)
- **타임아웃**: 목록 페이지 (connect 5s, read 12s), 상세 페이지 (connect 5s, read 8s)
- **시간 예산**: 상세 수집 누적 360초 초과 시 남은 상세는 생략하고 목록 정보만 저장 (부분 갱신 → CI 타임아웃 방지)
- **데이터 안전가드**: 크롤 결과가 비었거나 기존 data.json의 50% 미만이면 덮어쓰지 않음 (크롤 실패 시 라이브 페이지 보존)
- **첨부파일**: 게시물당 목록 최대 5개(이름+절대URL) 수집, 그중 2개까지 텍스트 추출(PDF→pypdf 앞4페이지 / HWP→olefile PrvText / HWPX→zip PrvText, 각 1200자) 후 `상세내용`에 `[첨부: 파일명]` 구분자로 append. 파일당 8MB 다운로드 캡, 0.45s 딜레이, 360s 시간예산 공유, 실패 시 해당 파일만 skip(fail-soft)

---

## data.json 스키마

```json
{
  "last_updated": "2026-03-09 10:37:11",
  "data": [
    {
      "구분": "서울지방 식약청",
      "제목": "게시물 제목",
      "등록일": "2026-03-05",
      "URL": "https://www.mfds.go.kr/...",
      "상세내용": "게시물 본문 + 첨부 추출 텍스트('[첨부: 파일명]' 구분자로 append, 없을 수 있음)",
      "첨부파일": [{"이름": "파일명.pdf", "URL": "https://...(절대 URL)"}]
    }
  ]
}
```

- `등록일` 기준 내림차순 정렬
- 한글 필드명 사용 (프론트엔드와 직접 바인딩)
- `첨부파일` 키는 2026-06-10 이후 생성분에만 존재 — 프론트엔드는 `Array.isArray` 가드로 결측 허용(안전가드 발동 시 옛 data.json이 유지될 수 있음)

---

## 웹 프론트엔드 (index.html)

- **프레임워크 없음**: 순수 HTML/CSS/JavaScript (Vanilla)
- **디자인**: 다크모드, Pretendard 폰트, glassmorphism 카드
- **기능**:
  - 정렬: 최신순 / 오래된순 / 상세내용 있는 것 우선
  - 최신순 = 3-tier 랭킹: ①상세O+최근 5일(관심도 점수 가중 룰렛 — 새로고침마다 변동) ②상세O 과거(등록일 desc) ③상세X 맨 뒤. 관심도 점수 = HIGH/LOW 키워드(제목 3배 가중) + 상세 길이 + 첨부 보너스 + 최근성
  - 첨부파일 칩: 카드에 📎 칩(새 탭, https만 링크), 복사 텍스트에 `첨부파일:` 줄 포함
  - 소스 필터: 드롭다운으로 출처별 필터링
  - 검색: 실시간 검색 (280ms 디바운스), 제목·출처·상세내용 대상
  - 체크 표시: localStorage(`mfds_checked_links`)에 읽음 상태 저장
  - 복사 버튼: 카드 내용을 클립보드에 복사
  - 상세내용 토글: 기본 4줄, 클릭 시 전체 펼침
- **렌더링**: 청크 렌더링 (80개 단위) - 대량 데이터 처리 최적화
- **반응형**: 모바일 대응 (600px 이하 단일 컬럼)

---

## GitHub Actions 워크플로우

**파일**: `.github/workflows/crawl.yml`

| 항목 | 설정 |
|------|------|
| 자동 실행 | 매일 UTC 20:00 (KST 05:00) |
| 수동 실행 | workflow_dispatch (GitHub 웹/모바일 앱) |
| Python | 3.12 (pip 캐시 활성화) |
| 타임아웃 | 25분 (크롤러 자체 시간예산 360초로 조기 종료) |
| 동시성 | `concurrency: mfds-crawl` (중복 실행 방지, 진행 중 미취소) |
| 커밋 사용자 | github-actions[bot] |
| 커밋 대상 | data.json, crawl_log.txt |
| 환경변수 | `GITHUB_ACTIONS_CRAWL=true` (로컬 git push 스킵용) |

### 로컬 vs Actions 실행 차이

- **로컬 실행** (`python croll_mfds.py`): 크롤링 후 자동으로 git add → commit → push 수행
- **Actions 실행**: `GITHUB_ACTIONS_CRAWL=true`로 스크립트 내 git push 스킵, 워크플로우가 커밋/푸시 처리

---

## 의존성

```
requests          # HTTP 요청
beautifulsoup4    # HTML 파싱
pandas            # 데이터 정렬/변환
urllib3           # 재시도 로직
pypdf             # PDF 첨부 텍스트 추출 (pure-python)
olefile           # HWP(v5) PrvText 추출 (pure-python)
```

---

## 개발 참고사항

- **정적 사이트**: Cloudflare Pages는 빌드 과정 없이 정적 파일만 서빙 (wrangler.toml 없음)
- **데이터 갱신 주기**: 하루 1회 (KST 05:00), 필요시 GitHub에서 수동 트리거 가능
- **크롤링 범위**: 현재 월 + 직전 월만 수집하므로 data.json은 항상 최근 2개월 데이터
- **한글 필드명**: data.json의 키가 한글 (`구분`, `제목`, `등록일`, `URL`, `상세내용`, `첨부파일`) — 프론트엔드에서 직접 참조
- **MFDS 사이트 구조 변경 시**: `process_mfds()`의 CSS 셀렉터(`div.center_column > a.title`, `div.right_column`, `div.bv_cont`) 확인 필요
- **KCIA 사이트 구조 변경 시**: `process_kcia()`의 CSS 셀렉터(`td.left > a.link`, `div.view_area`) 확인 필요

---

## 변경 이력

### 2026-07-09

- **crawl.yml**: 자동 크롤링 스케줄 변경 — KST 21:00 → KST 05:00 (`cron: '0 12 * * *'` → `'0 20 * * *'`)

### 2026-06-10

#### 첨부파일 텍스트 추출 + 관심도 가중 최신순 (Claude Code Fable 5, ultracode 다중에이전트 검증)

**목표**: ① 상세내용을 첨부파일(PDF/HWP/HWPX) 본문까지 확장해 숏츠 소재 풍부화, ② '최신순'을 최신 + 잠재고객(화장품·식품·의료기기 영업자) 유용성 + 대중 관심도 기준으로 고도화.

**크롤러 (croll_mfds.py)**:
- 첨부 수집: 실측 셀렉터(MFDS `div.bv_file_box ul.bbs_file_view_list li`의 `strong`+`a.bbs_icon_filedown`, KCIA `div.attach_box ul.attach_list a`) → `첨부파일` 필드([{이름,URL}], 추출형식 우선 5개)
- 텍스트 추출: PDF(pypdf 앞4페이지)·HWP(olefile PrvText)·HWPX(zip PrvText/section xml), 게시물당 2건·각 1200자, `상세내용`에 `[첨부: 파일명]`로 append. 8MB 캡(Content-Length 사전차단+스트리밍 누적차단+시간예산 중단), 0.45s politeness, 전부 fail-soft
- `_in_window` 달력 버그 수정: now-30일 근사 → `now.replace(day=1)-1일` (3년 스윕 27일 오차 실증: 31일에 지난달 통째 누락, 3/1~2에 1월 오인)
- requirements.txt += pypdf, olefile (pure-python, CI 변경 불필요)

**프론트엔드 (index.html)**:
- 관심도 점수 `scoreCard()`: HIGH 키워드(점검·감시·행정처분·회수·과대광고·개정·인허가·가이드라인·수출·NMPA·FDA·GMP 등, 제목 적중 3배) − LOW 키워드(뉴스레터·청년탐험단·설문조사 등, 오탐 방지형: 성과보고·인사발령) + 상세길이(최대 +8) + 첨부 보너스(+5) + 최근성(+0~5)
- tier1 풀을 Fisher-Yates → **점수 가중 룰렛 비복원 샘플링**으로 교체: 고관심 카드가 앞설 확률↑, 새로고침마다 순서 변동(다양성 유지, 측정 r≈-0.985)
- 첨부 칩(📎 새 탭, https 스킴만 링크, esc 이스케이프) + 복사 텍스트에 `첨부파일:` 줄. `첨부파일` 키 결측(옛 data.json) 안전

**검증**: 로컬 풀크롤 51건 — 첨부 목록 122건·텍스트 추출 54건, 상세있음 40→43(첨부로 구제 3건), 8MB 캡이 10/54/58/136MB PDF 차단 확인, data.json 190KB, 빈제목·중복 0, 안전가드 통과. node 단위검증: 상위점수=정기감시·과대광고사례집·GMP교육 / 하위=뉴스레터(-5), 가중셔플 순열 보존.

### 2026-06-09

#### 최신순 카드 배치 개선 + 일일 스케줄 재점검 (Claude Code Opus 4.8, ultracode 다중에이전트 검증)

**문제**: 라이브 '최신순' 첫 화면에 제목·상세 둘 다 빈 카드(KCIA no=17653)가 앞쪽에 노출되고, "★★★3번째…"(경인 6-04) 등이 중복 표시됨. 이 페이지 카드가 shotsforge(`barnanacle/video_posting`) 숏츠 입력(수동 복사 흐름)이라 무용·중복 카드가 앞에 오면 숏츠 품질이 저하됨.

**원인**: ① MFDS/KCIA 목록이 공지를 상단에 핀 고정 → 동일 URL이 "공지행+일반행"으로 2번 수집(중복 3쌍). ② KCIA 비밀글/일시적 빈 행이 제목 없이 수집됨.

**수정 (commit `e303049`)**:
- **croll_mfds.py**: 빈 제목 행 skip(상세요청·sleep 전 차단), 전역 URL 정규화 중복제거(`_norm_url`, seq/no 기준). `empty_skipped`는 시간예산용 `skipped`와 분리(CI 진단 보존).
- **index.html**: 로드 시 빈제목 방어필터 + '최신순'을 **3-tier 랭킹**으로 — ①상세O+최근(셔플=다양성) ②상세O 과거(등록일 desc) ③상세X 맨 뒤(최신이어도 앞으로 못 옴). 셔플 풀 상한 `RECENT_LIMIT=24`. 오래된순/상세있음/구분별/검색/체크 불변.
- **검증**: 로컬 54→51건(빈제목0·중복0), 라이브 DOM 51건·빈제목0·앞 12장 전부 상세有, 스크린샷 확인.

**일일 스케줄 재점검 — "완전차단" 정정**: 6/8 기록의 hard-block 결론은 단일 런(6/7, 차단된 IP) 기준이었음. 실제로는 **IP별 간헐 차단**으로 확인:
- 6/7 런 egress `48.217.177.228` → MFDS 전부 `ConnectTimeout` → **안전가드 발동**(KCIA 8건<54×50%) → 페이지 보존·미갱신.
- 6/8 런 egress `20.161.69.72` → MFDS 9소스 전부 200 성공 → **54건 커밋·배포**.
- GitHub Actions의 Azure egress IP가 회전하고 mfds.go.kr은 일부 IP만 차단 → **좋은 IP 날 갱신 / 막힌 IP 날 안전가드 보존**. 타임아웃 수정(`b93a60b`)으로 6/7·6/8 모두 2~3분 정상 종료(더는 10분 cancel 없음). 결론: **일일 스케줄 정상 작동(확률적 갱신)**. 100% 자동화가 필요하면 KR 셀프호스트 러너/프록시(인프라).

### 2026-06-07

#### 사건: 6/4 이후 자동 배포 정지 → 복구 (Claude Code Opus 4.8, ultracode 다중에이전트 검증)

**증상**: 라이브 페이지 `last_updated`가 2026-06-04에 고정 (6/5·6/6 갱신 안 됨).

**원인**: 6/5·6/6 GitHub Actions 스케줄 런이 `timeout-minutes: 10` 초과로 `cancelled` → 커밋/푸시 전 종료 → data.json 미갱신 → Cloudflare 재배포 없음. 작업량(54건)·코드·셀렉터·볼륨 모두 정상이고 로컬(한국 IP)에선 전체 크롤 약 1.5분. 같은 작업이 CI(GitHub Actions = Azure 해외 IP)에서만 6/5부터 10분 초과 → **mfds.go.kr의 해외/데이터센터 IP throttling/차단**이 유력 (확신 ~75%, CI 로그로 확정 예정). 부수 발견: CI에서 Python stdout 버퍼링으로 실패 로그 유실, `last_updated`가 러너 UTC 시각이라 페이지가 KST보다 ~9시간 뒤로 표시(그래서 "6/4").

**수정 (commit `b93a60b`)**:
- **croll_mfds.py**: 상세수집 **시간예산 360s**(초과 시 목록만 저장해 부분 갱신), 타임아웃 `(5,12)`/`(5,8)` 명시·재시도 3→2·백오프 2→1, **데이터 안전가드**(신규 0 또는 기존의 50% 미만이면 미갱신 → 페이지 보존), `last_updated`/로그/커밋 **KST 통일**, **무버퍼 진단로그**(egress IP·소스별 list/상세 시간), 등록일 필터 **연도 인식**(1월↔12월 경계 버그 수정).
- **crawl.yml**: `timeout-minutes` 10→25, `python -u`, `fetch-depth: 0`, `concurrency`(중복 실행 방지·진행 중 미취소), push 전 `git pull --rebase`, 스케줄 주석 정정(09시→21시).
- **index.html**: **2일 이상 갱신 지연 시 경고 배너**(무중단 정지 조기 인지), 제목/출처/링크 HTML 이스케이프(`esc()`), KST 표시.

**검증**: 로컬 크롤 54건/9소스 정상·KST·안전가드 통과(~80초). 라이브 `data.json` 6/7 데이터(`2026-06-07 12:25`) 반영 확인.

**남은 확인**: 다음 CI 런 로그의 egress IP·소스별 응답시간으로 throttle vs 완전차단 확정. 완전차단 시 인프라 대안 — ① 한국 셀프호스트 러너 ② KR 프록시(secret 주입) ③ KR 리전 스케줄러 (GitHub 호스트 러너는 한국 리전 없음). 참고: CI 수동 트리거(`gh workflow run`)는 현재 PAT에 Actions 쓰기 권한 없어 403 — GitHub 앱/웹에서만 가능.

### 2026-04-18

#### 점검 (Claude Code Opus 4.7 기준 전체 코드 리뷰)

- **크롤러 (`croll_mfds.py`)**: 정상 동작 확인
  - 재시도 로직(3회, exponential backoff), 타임아웃(목록 15s/상세 10s), 요청 간격(0.5s) 모두 적절
  - MFDS 9개 소스 셀렉터(`div.center_column > a.title`, `div.right_column`, `div.bv_cont`) 및 KCIA 셀렉터(`td.left > a.link`, `div.view_area`) 정상 파싱 확인
  - 알려진 경미 이슈: `post_date.month in [current_month, last_month]` 월 비교만 수행 (연도 미체크) — 1월 ↔ 12월 경계에서 전년도 게시물 혼입 가능성, 실사용 영향 낮음
- **프론트엔드 (`index.html`)**: 정상 동작 확인
  - 카드 렌더링(청크 80), 정렬(최신/오래된/상세있음), 소스 드롭다운, 검색(280ms 디바운스), 체크 상태(localStorage), 복사 버튼 모두 정상

#### 변경사항

- **index.html**: 최신순 정렬 셔플 로직 변경 — 시드 기반 동일 날짜 그룹 셔플 → 오늘 기준 5일 이내 카드 랜덤 셔플
  - 오늘 날짜(`Date.now()`) 기준으로 `RECENT_WINDOW_DAYS = 5`일 이내 `등록일` 카드만 대상
  - `Math.random()` 기반 Fisher-Yates 셔플 — 새로고침마다 순서 달라짐 (비결정론적)
  - 5일 초과 카드는 날짜 내림차순 유지, 최근 카드(셔플됨) 뒤에 배치
  - 기존 `hashSeed()`, `seededRandom()`, `shuffleByDateGroup()` 제거 → `shuffleRecentCards()` 로 대체

### 2026-03-31

- **crawl.yml**: 자동 크롤링 스케줄 변경 — KST 09:00 → KST 21:00 (`cron: '0 0 * * *'` → `'0 12 * * *'`)
- **index.html**: 최신순 정렬 시 동일 날짜 카드 시드 기반 셔플 기능 추가 (이후 2026-04-18 로직 변경으로 대체됨)
