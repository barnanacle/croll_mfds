import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs
import datetime
import pandas as pd
import re
import json

import time  # 딜레이를 위한 time 모듈 추가
import subprocess
import os
import zipfile
from io import BytesIO
from html import unescape

# 첨부 텍스트 추출용 선택 의존성 — 미설치 시 해당 형식 추출만 건너뜀(fail-soft).
# (requirements.txt에 포함되지만, 구버전 로컬 venv에서도 크롤 본체는 절대 죽지 않게 가드)
try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None
try:
    import olefile
except Exception:
    olefile = None

# ── KST(한국시간) 헬퍼 ──
# GitHub Actions 러너는 UTC이므로, 사용자에게 보이는 시각/날짜 필터는 KST 기준으로 통일한다.
KST = datetime.timezone(datetime.timedelta(hours=9))
def now_kst():
    return datetime.datetime.now(KST)

# ── 시간 예산 & 타임아웃 ──
# 상세페이지 수집 전체 시간 예산(초). 초과 시 남은 상세 수집은 건너뛰고 목록 정보만 저장 → 부분이라도 갱신.
DETAIL_DEADLINE_SEC = 360
LIST_TIMEOUT = (5, 12)    # (connect, read) 목록 페이지
DETAIL_TIMEOUT = (5, 8)   # (connect, read) 상세 페이지

# ── 첨부파일 수집/추출 상한 ──
ATTACH_LIST_MAX = 5                 # 게시물당 첨부 목록(이름+URL) 최대 개수
ATTACH_EXTRACT_MAX = 2              # 게시물당 텍스트 추출 시도 최대 개수(PDF 우선)
ATTACH_TEXT_CAP = 1200              # 첨부 1건당 추출 텍스트 최대 길이(자)
ATTACH_SIZE_CAP = 8 * 1024 * 1024   # 첨부 다운로드 상한(8MB)
ATTACH_SLEEP = 0.45                 # 첨부 다운로드 후 politeness 딜레이(초)
_START = time.monotonic()
def over_deadline():
    return (time.monotonic() - _START) > DETAIL_DEADLINE_SEC

# 공통 헤더
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.61 Safari/537.36'
}

# 재시도 로직이 포함된 세션 생성
# (throttling 환경에서 행이 누적되지 않도록 재시도/백오프를 완화)
session = requests.Session()
retry_strategy = Retry(
    total=2,                    # 최대 2회 재시도
    backoff_factor=1,           # 1초, 2초 간격으로 재시도
    status_forcelist=[500, 502, 503, 504],  # 서버 에러 시 재시도
    allowed_methods=["GET"],
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("https://", adapter)
session.mount("http://", adapter)
session.headers.update(headers)

# 식약처 관련 URL 목록
food_drug_urls = [
    {'url': 'https://www.mfds.go.kr/brd/m_824/list.do', '출처': '서울지방 식약청'},
    {'url': 'https://www.mfds.go.kr/brd/m_841/list.do', '출처': '경인지방 식약청'},
    {'url': 'https://www.mfds.go.kr/brd/m_765/list.do', '출처': '부산지방 식약청'},
    {'url': 'https://www.mfds.go.kr/brd/m_891/list.do', '출처': '대전지방 식약청'},
    {'url': 'https://www.mfds.go.kr/brd/m_875/list.do', '출처': '광주지방 식약청'},
    {'url': 'https://www.mfds.go.kr/brd/m_857/list.do', '출처': '대구지방 식약청'},
    {'url': 'https://kcia.or.kr/home/notice/notice.php?page=1', '출처': '대한화장품협회'},
    {'url': 'https://www.mfds.go.kr/brd/m_1059/list.do', '출처': '식약처 공무원지침서'},
    {'url': 'https://www.mfds.go.kr/brd/m_1060/list.do', '출처': '식약처 민원인안내서'}
]

# 게시물을 저장할 리스트
all_posts = []
# URL 기준 전역 중복 제거용 집합(모든 소스 공통).
# MFDS 지방청은 host(mfds.go.kr)는 같아도 게시판 path(m_824 vs m_841…)가 달라
# 정규화 키가 소스 간 충돌하지 않음을 실데이터로 확인함(0건) → 전역 set이 안전.
seen_urls = set()
# 첨부파일 수집 통계(전역 진단용 — 실행 말미에 1줄 출력)
attach_stats = {'listed': 0, 'extracted': 0}


def _in_window(post_date, now):
    """이번 달 + 지난 달 게시물만 통과(연도 인식, 달력 기준).
    now-30일 근사는 31일이 긴 달 말일(예: 5/31)에 지난달이 통째로 빠지고,
    3/1~3/2에는 2월 대신 1월이 잡히는 경계 버그가 있어 달력 계산으로 교체."""
    prev = now.replace(day=1) - datetime.timedelta(days=1)  # 지난달 말일
    return (post_date.year, post_date.month) in {(now.year, now.month), (prev.year, prev.month)}


def _norm_url(u):
    """게시물 고유 식별자(MFDS=seq, KCIA=no) 기준으로 URL을 정규화(중복 제거용).
    page/srch*/itm_seq*/ss 등은 네비게이션 노이즈이므로 제거하고, id가 없으면
    쿼리를 버린 base path로 대체한다."""
    if not u:
        return ''
    p = urlparse(u)
    q = parse_qs(p.query)
    ident = (q.get('seq', [None])[0]) or (q.get('no', [None])[0])
    base = (p.scheme + '://' + p.netloc + p.path).lower().rstrip('/')
    return base + '?' + ident if ident else base


def collect_attachments(soup, page_url, source):
    """상세페이지 soup에서 첨부파일 목록 전체를 수집한다.
    returns [{'이름': 파일명(확장자 포함), 'URL': 절대 다운로드 URL}, ...] (전체 — 상한 적용은 호출부에서)
    실패해도 빈 리스트 반환(fail-soft) — 본문 수집에 영향 없음."""
    out = []
    try:
        if 'mfds.go.kr' in page_url:
            # 검증된 마크업: div.bv_file_box > ul.bbs_file_view_list > li
            #   > div.bbs_file_cont > strong = 파일명 / a.bbs_icon_filedown href = ./down.do?...(상대)
            for li in soup.select('div.bv_file_box ul.bbs_file_view_list li'):
                name_tag = li.select_one('div.bbs_file_cont > strong')
                link_tag = li.select_one('a.bbs_icon_filedown')
                name = name_tag.get_text(strip=True) if name_tag else ''
                href = link_tag.get('href') if link_tag else None
                if not (name and href):
                    continue
                out.append({'이름': name, 'URL': urljoin(page_url, href)})
        elif 'kcia.or.kr' in page_url:
            # 검증된 마크업: div.attach_box > ul.attach_list, a 텍스트 = 파일명,
            #   href = /inc/down.php?dir=BOARD&file_name=...&rename=<urlencoded 파일명>
            for link_tag in soup.select('div.attach_box ul.attach_list a'):
                name = link_tag.get_text(strip=True)
                href = link_tag.get('href')
                if not (name and href):
                    continue
                out.append({'이름': name, 'URL': urljoin(page_url, href)})
    except Exception as e:
        print(f"  [attach] 목록 파싱 실패 ({source}) {page_url} - {type(e).__name__}", flush=True)
    return out


def _attach_ext(filename):
    return os.path.splitext(filename.lower().strip())[1]


def _pick_extract_targets(attachments):
    """텍스트 추출 대상 선정: PDF 우선, 그다음 HWP/HWPX(각각 등장 순서 유지), 최대 ATTACH_EXTRACT_MAX건."""
    pdfs = [a for a in attachments if _attach_ext(a['이름']) == '.pdf']
    hwps = [a for a in attachments if _attach_ext(a['이름']) in ('.hwp', '.hwpx')]
    return (pdfs + hwps)[:ATTACH_EXTRACT_MAX]


def _hwpx_text_from_zip(data):
    """HWPX(zip) 바이트에서 텍스트 추출: Preview/PrvText.txt 우선, 없으면 첫 Contents/section*.xml 태그 제거."""
    with zipfile.ZipFile(BytesIO(data)) as zf:
        names = zf.namelist()
        prv = next((n for n in names if n.lower().endswith('preview/prvtext.txt')), None)
        if prv:
            return zf.read(prv).decode('utf-8-sig', errors='ignore')
        sec = sorted(n for n in names if re.fullmatch(r'Contents/section\d+\.xml', n))
        if sec:
            xml = zf.read(sec[0]).decode('utf-8', errors='ignore')
            return unescape(re.sub(r'<[^>]+>', ' ', xml))
    return ''


def extract_attachment_text(url, filename):
    """첨부 1건을 스트리밍 다운로드(8MB 상한)해 텍스트를 추출한다(최대 ATTACH_TEXT_CAP자).
    지원: .pdf(pypdf 앞 4페이지) / .hwp(olefile PrvText, UTF-16-LE) / .hwpx(zip PrvText 또는 section xml).
    그 외 확장자(PNG/JPG/ZIP/XLSX 등)와 모든 예외는 '' 반환(fail-soft) — 실행을 절대 중단시키지 않는다."""
    ext = _attach_ext(filename)
    if ext not in ('.pdf', '.hwp', '.hwpx'):
        return ''
    if ext == '.pdf' and PdfReader is None:
        return ''
    if ext == '.hwp' and olefile is None:
        return ''
    try:
        # 스트리밍 다운로드: Content-Length 사전 차단 + iter_content 누적 8MB/시간예산 차단
        with session.get(url, stream=True, timeout=DETAIL_TIMEOUT) as r:
            r.raise_for_status()
            cl = r.headers.get('Content-Length')
            if cl and cl.isdigit() and int(cl) > ATTACH_SIZE_CAP:
                print(f"  [attach] 크기 초과 스킵 {filename[:40]} ({int(cl) // 1048576}MB)", flush=True)
                return ''
            chunks = []
            size = 0
            for chunk in r.iter_content(chunk_size=65536):
                size += len(chunk)
                if size > ATTACH_SIZE_CAP:
                    print(f"  [attach] 8MB 초과 다운로드 중단 {filename[:40]}", flush=True)
                    return ''
                if over_deadline():
                    print(f"  [attach] 시간예산 초과 다운로드 중단 {filename[:40]}", flush=True)
                    return ''
                chunks.append(chunk)
        data = b''.join(chunks)

        text = ''
        if ext == '.pdf':
            reader = PdfReader(BytesIO(data))
            text = '\n'.join((page.extract_text() or '') for page in reader.pages[:4])
        elif ext == '.hwp':
            if data[:4] == b'PK\x03\x04':
                text = _hwpx_text_from_zip(data)  # 확장자만 .hwp인 zip(HWPX) 방어
            else:
                ole = olefile.OleFileIO(BytesIO(data))
                try:
                    if ole.exists('PrvText'):
                        text = ole.openstream('PrvText').read().decode('utf-16-le', errors='ignore')
                finally:
                    ole.close()
        elif ext == '.hwpx':
            text = _hwpx_text_from_zip(data)

        text = re.sub(r'\s+', ' ', text.replace('\x00', ' ')).strip()
        return text[:ATTACH_TEXT_CAP]
    except Exception as e:
        print(f"  [attach] 추출 실패 {filename[:40]} - {type(e).__name__}: {str(e)[:50]}", flush=True)
        return ''


def get_detail_content(url):
    """
    게시글의 상세 내용 + 첨부파일을 크롤링하는 함수.
    returns (상세내용 텍스트(첨부 추출 텍스트 포함), 첨부파일 [{'이름','URL'}] 목록)
    """
    try:
        response = session.get(url, timeout=DETAIL_TIMEOUT)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # 식약청 지방청의 경우
        if "mfds.go.kr" in url:
            content_div = soup.find('div', class_='bv_cont')
        # 대한화장품협회의 경우
        elif "kcia.or.kr" in url:
            content_div = soup.find('div', class_='view_area')
        else:
            return "", []

        content = ""
        if content_div:
            # 모든 텍스트 추출 (줄바꿈 유지)
            content = content_div.get_text(separator='\n', strip=True)
            # 연속된 빈 줄 제거
            content = re.sub(r'\n\s*\n', '\n', content).strip()

        # 첨부파일 전체 목록 수집(이미 받은 soup 재사용 → 추가 페이지 요청 없음)
        attachments_all = collect_attachments(soup, url, urlparse(url).netloc)

        # 첨부 텍스트 추출: 전체 목록에서 대상 선정(PDF→HWP/HWPX, 최대 ATTACH_EXTRACT_MAX건),
        # 시간예산(over_deadline) 공유. 예산 초과 시 '조용히' 중단 —
        # skipped(마감초과 상세생략) 카운터는 CI 진단 전용이므로 오염 금지.
        for att in _pick_extract_targets(attachments_all):
            if over_deadline():
                break
            att_text = extract_attachment_text(att['URL'], att['이름'])
            time.sleep(ATTACH_SLEEP)  # 첨부 다운로드 politeness 딜레이
            if att_text:
                attach_stats['extracted'] += 1
                content += f"\n\n[첨부: {att['이름']}]\n{att_text}"

        # 저장용 목록: 추출형식(.pdf/.hwp/.hwpx)을 앞에 배치한 뒤 상한 적용
        # (이미지가 5개 이상 선행해도 추출된 문서가 목록에서 잘리지 않도록)
        ext_first = [a for a in attachments_all if _attach_ext(a['이름']) in ('.pdf', '.hwp', '.hwpx')]
        others = [a for a in attachments_all if a not in ext_first]
        attachments = (ext_first + others)[:ATTACH_LIST_MAX]
        attach_stats['listed'] += len(attachments)

        return content.strip(), attachments
    except Exception as e:
        print(f"  [detail] 실패 {url} - {type(e).__name__}: {str(e)[:60]}", flush=True)
        return "", []


def process_mfds(url, soup, source):
    now = now_kst()
    count = 0
    dtime = 0.0
    dmax = 0.0
    skipped = 0
    empty_skipped = 0

    for item in soup.select('ul > li'):
        title_tag = item.select_one('div.center_column > a.title')
        date_tag = item.select_one('div.right_column')
        if not (title_tag and date_tag):
            continue
        title = title_tag.text.strip()
        link = title_tag.get('href')
        date_str = date_tag.text.strip()
        try:
            post_date = datetime.datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            continue
        if not _in_window(post_date, now) or not link:
            continue

        # 빈 제목 행 스킵(상세요청·sleep 전에 차단 → 비용 0). 전용 카운터 사용.
        if not title:
            empty_skipped += 1
            continue

        link = urljoin(url, link)
        # URL 전역 중복 제거(공지 고정행이 일반 dated 행을 복제하는 케이스 제거)
        nkey = _norm_url(link)
        if not nkey or nkey in seen_urls:
            continue
        seen_urls.add(nkey)

        # 상세 내용 크롤링 (식약청 지방청, 공무원지침서, 민원인안내서인 경우)
        detail_content = ""
        attachments = []
        want_detail = any(region in source for region in ['서울', '경인', '부산', '대전', '광주', '대구', '공무원지침서', '민원인안내서'])
        if want_detail:
            if over_deadline():
                skipped += 1  # 시간예산 초과: 상세는 생략하되 목록 정보는 보존
            else:
                t = time.monotonic()
                detail_content, attachments = get_detail_content(link)
                el = time.monotonic() - t
                dtime += el
                dmax = max(dmax, el)
                time.sleep(0.5)  # 서버 부하 방지를 위한 딜레이

        all_posts.append({
            '구분': source,
            '제목': title,
            'URL': link,
            '등록일': date_str,
            '상세내용': detail_content,
            '첨부파일': attachments
        })
        count += 1

    tail = f", 마감초과 상세생략 {skipped}건" if skipped else ""
    if empty_skipped:
        tail += f", 빈제목 {empty_skipped}건"
    print(f"  → {source}: {count}건 (상세 {dtime:.1f}s, max {dmax:.1f}s{tail})", flush=True)


def process_kcia(url, soup, source):
    now = now_kst()
    count = 0
    dtime = 0.0
    dmax = 0.0
    skipped = 0
    empty_skipped = 0

    for item in soup.select('tbody > tr'):
        title_tag = item.select_one('td.left > a.link')
        tds = item.select('td')
        if not (title_tag and tds):
            continue
        title = title_tag.text.strip()
        link = title_tag.get('href')
        date_str = tds[-1].text.strip()
        try:
            post_date = datetime.datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            continue
        if not _in_window(post_date, now) or not link:
            continue

        # 빈 제목 행 스킵(상세요청·sleep 전에 차단). 전용 카운터 사용.
        if not title:
            empty_skipped += 1
            continue

        base_url = url.split('?')[0]
        link = urljoin(base_url, link)
        # URL 전역 중복 제거
        nkey = _norm_url(link)
        if not nkey or nkey in seen_urls:
            continue
        seen_urls.add(nkey)

        # 상세 내용 크롤링
        detail_content = ""
        attachments = []
        if over_deadline():
            skipped += 1
        else:
            t = time.monotonic()
            detail_content, attachments = get_detail_content(link)
            el = time.monotonic() - t
            dtime += el
            dmax = max(dmax, el)
            time.sleep(0.5)  # 서버 부하 방지를 위한 딜레이

        all_posts.append({
            '구분': source,
            '제목': title,
            'URL': link,
            '등록일': date_str,
            '상세내용': detail_content,
            '첨부파일': attachments
        })
        count += 1

    tail = f", 마감초과 상세생략 {skipped}건" if skipped else ""
    if empty_skipped:
        tail += f", 빈제목 {empty_skipped}건"
    print(f"  → {source}: {count}건 (상세 {dtime:.1f}s, max {dmax:.1f}s{tail})", flush=True)


# ── 크롤링 시작 ──
print(f"=== 크롤링 시작 {now_kst().strftime('%Y-%m-%d %H:%M:%S')} KST (상세 시간예산 {DETAIL_DEADLINE_SEC}s) ===", flush=True)
# 진단용: 이 실행이 어떤 IP로 나가는지 기록 (MFDS 차단/throttling 판별에 사용)
try:
    egress = session.get('https://api.ipify.org', timeout=5).text.strip()
    print(f"egress IP: {egress}", flush=True)
except Exception as e:
    print(f"egress IP 확인 실패: {type(e).__name__}", flush=True)

# 식약처 관련 사이트 크롤링
print("\n식약처 관련 사이트 크롤링 시작...", flush=True)
for site in food_drug_urls:
    url = site['url']
    source = site['출처']
    print(f"크롤링 중: {source}", flush=True)
    t = time.monotonic()
    try:
        response = session.get(url, timeout=LIST_TIMEOUT)
        response.raise_for_status()
        print(f"  [list] {source} {response.status_code} {time.monotonic()-t:.1f}s", flush=True)
        soup = BeautifulSoup(response.text, 'html.parser')

        if "kcia.or.kr" in url:
            process_kcia(url, soup, source)
        elif "mfds.go.kr" in url:
            process_mfds(url, soup, source)
    except Exception as e:
        print(f"  [list] {source} 실패 {time.monotonic()-t:.1f}s {type(e).__name__}: {str(e)[:80]}", flush=True)

print(f"\n첨부파일: 목록 {attach_stats['listed']}건 / 텍스트 추출 {attach_stats['extracted']}건", flush=True)

# 데이터프레임 생성 및 열 순서 지정
df = pd.DataFrame(all_posts)
if not df.empty:
    df = df[['구분', '제목', '등록일', 'URL', '상세내용', '첨부파일']]  # 상세내용·첨부파일 열 포함
    # 등록일 기준으로 내림차순 정렬
    df['등록일'] = pd.to_datetime(df['등록일'])  # 문자열을 datetime 형식으로 변환
    df = df.sort_values('등록일', ascending=False)  # 내림차순 정렬
    df['등록일'] = df['등록일'].dt.strftime('%Y-%m-%d')  # 다시 문자열 형식으로 변환
    json_data = df.to_dict(orient='records')
else:
    json_data = []

try:
    new_count = len(json_data)

    # ── 데이터 안전가드 ──
    # 크롤 결과가 비었거나 기존 data.json 대비 50% 미만이면 덮어쓰지 않는다.
    # (MFDS 차단 등으로 일부 소스만 수집된 경우 라이브 페이지가 통째로 비워지는 사고를 방지)
    old_count = 0
    try:
        with open('data.json', 'r', encoding='utf-8') as f:
            old_count = len(json.load(f).get('data', []))
    except Exception:
        old_count = 0

    if new_count == 0 or (old_count > 0 and new_count < old_count * 0.5):
        print(f"⚠️ 안전가드 발동: 신규 {new_count}건 < 기존 {old_count}건의 50% → data.json 보존(미갱신)", flush=True)
        log_time = now_kst().strftime("%Y-%m-%d %H:%M:%S")
        with open('crawl_log.txt', 'a', encoding='utf-8') as log_f:
            log_f.write(f"[{log_time}] 안전가드 발동 | 신규 {new_count}건/기존 {old_count}건 → 미갱신\n")
        print("실행 기록이 'crawl_log.txt'에 저장되었습니다.", flush=True)
    else:
        # data.json 저장 (웹페이지용 고정 파일명) — last_updated는 KST 기준
        data_json = {
            "last_updated": now_kst().strftime("%Y-%m-%d %H:%M:%S"),
            "data": json_data
        }
        json_str = json.dumps(data_json, ensure_ascii=False, indent=2)
        with open('data.json', 'w', encoding='utf-8') as f:
            f.write(json_str)

        print(f"\n크롤링 완료!", flush=True)
        print(f"총 게시글 수: {new_count}", flush=True)
        print(f"data.json 파일이 업데이트되었습니다.", flush=True)

        # 로그 파일에 실행 기록 추가
        log_time = now_kst().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{log_time}] 크롤링 완료 | 게시글 수: {new_count}\n"
        with open('crawl_log.txt', 'a', encoding='utf-8') as log_f:
            log_f.write(log_entry)
        print(f"실행 기록이 'crawl_log.txt'에 저장되었습니다.", flush=True)

    # GitHub Actions 환경에서는 워크플로우가 git push를 처리하므로 스킵
    if os.environ.get('GITHUB_ACTIONS_CRAWL'):
        print("\n✅ GitHub Actions 환경 - git push는 워크플로우에서 처리합니다.", flush=True)
    else:
        # 로컬 실행 시 Git push (data.json을 레포지토리에 반영)
        project_dir = os.path.dirname(os.path.abspath(__file__))
        try:
            def run_git(cmd):
                result = subprocess.run(
                    cmd, cwd=project_dir, capture_output=True, text=True, timeout=30
                )
                return result

            print("\n📤 Git push 시작...", flush=True)
            run_git(['git', 'add', 'data.json', 'crawl_log.txt'])
            commit_msg = f"Update data.json ({now_kst().strftime('%Y-%m-%d %H:%M')})"
            commit_result = run_git(['git', 'commit', '-m', commit_msg])
            if commit_result.returncode == 0:
                push_result = run_git(['git', 'push', '-u', 'origin', 'main'])
                if push_result.returncode == 0:
                    print("✅ data.json이 GitHub에 push되었습니다. Cloudflare Pages 배포가 시작됩니다.", flush=True)
                else:
                    print(f"⚠️ Git push 실패: {push_result.stderr}", flush=True)
            else:
                if 'nothing to commit' in commit_result.stdout:
                    print("ℹ️ data.json에 변경사항 없음 (이전과 동일한 데이터)", flush=True)
                else:
                    print(f"⚠️ Git commit 실패: {commit_result.stderr}", flush=True)
        except Exception as git_err:
            print(f"⚠️ Git 작업 중 오류: {git_err}", flush=True)
            print("수동으로 git push 해주세요.", flush=True)

except Exception as e:
    print(f"데이터 저장 중 오류 발생: {e}", flush=True)
