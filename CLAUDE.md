# croll_MFDS 프로젝트

## 개요

식품의약품안전처(MFDS) 및 관련 기관의 공지사항을 자동 크롤링하여 웹 대시보드로 제공하는 서비스.

- **라이브 URL**: https://croll-mfds.pages.dev/
- **GitHub**: https://github.com/barnanacle/croll_mfds
- **배포**: Cloudflare Pages (GitHub main 브랜치 push 시 자동 배포)

---

## 아키텍처

```
GitHub Actions (매일 KST 21:00)
  → croll_mfds.py 실행 (Python 3.12)
  → data.json 생성
  → git commit & push
  → Cloudflare Pages 자동 배포
  → index.html이 data.json을 fetch하여 렌더링
```

### 핵심 흐름

1. **크롤링**: GitHub Actions가 cron 스케줄(`0 12 * * *`, UTC 12:00 = KST 21:00)로 `croll_mfds.py` 실행
2. **데이터 저장**: 크롤링 결과를 `data.json`에 JSON 형식으로 저장
3. **자동 커밋**: 변경사항이 있을 때만 `data.json`, `crawl_log.txt`를 커밋 & 푸시
4. **배포**: main 브랜치에 push되면 Cloudflare Pages가 자동으로 정적 사이트 배포
5. **웹 표시**: `index.html`이 `data.json`을 fetch하여 카드 형태로 렌더링

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
└── CLAUDE.md              # 이 파일
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

- **필터링**: 현재 월 + 지난 월의 게시물만 수집
- **상세 내용**: 각 게시물의 상세 페이지까지 진입하여 본문 텍스트 추출
- **재시도**: 최대 3회, exponential backoff (2s → 4s → 8s), 5xx 에러 시 자동 재시도
- **요청 간격**: 0.5초 딜레이 (서버 부하 방지)
- **타임아웃**: 목록 페이지 15초, 상세 페이지 10초

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
      "상세내용": "게시물 본문 텍스트 (없을 수 있음)"
    }
  ]
}
```

- `등록일` 기준 내림차순 정렬
- 한글 필드명 사용 (프론트엔드와 직접 바인딩)

---

## 웹 프론트엔드 (index.html)

- **프레임워크 없음**: 순수 HTML/CSS/JavaScript (Vanilla)
- **디자인**: 다크모드, Pretendard 폰트, glassmorphism 카드
- **기능**:
  - 정렬: 최신순 / 오래된순 / 상세내용 있는 것 우선
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
| 자동 실행 | 매일 UTC 12:00 (KST 21:00) |
| 수동 실행 | workflow_dispatch (GitHub 웹/모바일 앱) |
| Python | 3.12 (pip 캐시 활성화) |
| 타임아웃 | 10분 |
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
```

---

## 개발 참고사항

- **정적 사이트**: Cloudflare Pages는 빌드 과정 없이 정적 파일만 서빙 (wrangler.toml 없음)
- **데이터 갱신 주기**: 하루 1회 (KST 21:00), 필요시 GitHub에서 수동 트리거 가능
- **크롤링 범위**: 현재 월 + 직전 월만 수집하므로 data.json은 항상 최근 2개월 데이터
- **한글 필드명**: data.json의 키가 한글 (`구분`, `제목`, `등록일`, `URL`, `상세내용`) — 프론트엔드에서 직접 참조
- **MFDS 사이트 구조 변경 시**: `process_mfds()`의 CSS 셀렉터(`div.center_column > a.title`, `div.right_column`, `div.bv_cont`) 확인 필요
- **KCIA 사이트 구조 변경 시**: `process_kcia()`의 CSS 셀렉터(`td.left > a.link`, `div.view_area`) 확인 필요

---

## 변경 이력

### 2026-03-31

- **crawl.yml**: 자동 크롤링 스케줄 변경 — KST 09:00 → KST 21:00 (`cron: '0 0 * * *'` → `'0 12 * * *'`)
- **index.html**: 최신순 정렬 시 동일 날짜 카드 시드 기반 셔플 기능 추가
  - `last_updated` 타임스탬프를 시드로 사용하여 크롤링마다 카드 배치가 달라짐
  - 날짜 간 내림차순은 유지, 같은 날짜 그룹 내에서만 Fisher-Yates 셔플 적용
  - 결정론적 셔플: 같은 `last_updated`이면 새로고침해도 동일 순서, 크롤링 실행 후 변경
  - 관련 함수: `hashSeed()`, `seededRandom()`, `shuffleByDateGroup()`
