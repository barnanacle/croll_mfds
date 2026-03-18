import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import datetime
import pandas as pd
import re
import json

import time  # 딜레이를 위한 time 모듈 추가
import subprocess
import os

# 공통 헤더
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.61 Safari/537.36'
}

# 재시도 로직이 포함된 세션 생성
session = requests.Session()
retry_strategy = Retry(
    total=3,                    # 최대 3회 재시도
    backoff_factor=2,           # 2초, 4초, 8초 간격으로 재시도
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

def get_detail_content(url):
    """
    게시글의 상세 내용을 크롤링하는 함수
    """
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 식약청 지방청의 경우
        if "mfds.go.kr" in url:
            content_div = soup.find('div', class_='bv_cont')
        # 대한화장품협회의 경우
        elif "kcia.or.kr" in url:
            content_div = soup.find('div', class_='view_area')
        else:
            return ""
            
        if content_div:
            # 모든 텍스트 추출 (줄바꿈 유지)
            content = content_div.get_text(separator='\n', strip=True)
            # 연속된 빈 줄 제거
            content = re.sub(r'\n\s*\n', '\n', content)
            return content.strip()
        return ""
    except Exception as e:
        print(f"상세 내용 크롤링 중 오류 발생: {url} - {str(e)}")
        return ""

def process_mfds(url, soup, source):
    now = datetime.datetime.now()
    current_month = now.month
    last_month = (now - datetime.timedelta(days=30)).month

    for item in soup.select('ul > li'):
        title_tag = item.select_one('div.center_column > a.title')
        date_tag = item.select_one('div.right_column')
        if title_tag and date_tag:
            title = title_tag.text.strip()
            link = title_tag.get('href')
            date_str = date_tag.text.strip()
            try:
                post_date = datetime.datetime.strptime(date_str, '%Y-%m-%d')
                if post_date.month in [current_month, last_month]:
                    if link:
                        link = urljoin(url, link)
                        # 상세 내용 크롤링 (식약청 지방청, 공무원지침서, 민원인안내서인 경우)
                        detail_content = ""
                        if any(region in source for region in ['서울', '경인', '부산', '대전', '광주', '대구', '공무원지침서', '민원인안내서']):
                            detail_content = get_detail_content(link)
                            time.sleep(0.5)  # 서버 부하 방지를 위한 딜레이
                        
                        all_posts.append({
                            '구분': source,
                            '제목': title,
                            'URL': link,
                            '등록일': date_str,
                            '상세내용': detail_content
                        })
            except ValueError:
                continue

def process_kcia(url, soup, source):
    now = datetime.datetime.now()
    current_month = now.month
    last_month = (now - datetime.timedelta(days=30)).month

    for item in soup.select('tbody > tr'):
        title_tag = item.select_one('td.left > a.link')
        date_tag = item.select('td')[-1]
        if title_tag and date_tag:
            title = title_tag.text.strip()
            link = title_tag.get('href')
            date_str = date_tag.text.strip()
            try:
                post_date = datetime.datetime.strptime(date_str, '%Y-%m-%d')
                if post_date.month in [current_month, last_month]:
                    if link:
                        base_url = url.split('?')[0]
                        link = urljoin(base_url, link)
                        # 상세 내용 크롤링
                        detail_content = get_detail_content(link)
                        time.sleep(0.5)  # 서버 부하 방지를 위한 딜레이
                        
                        all_posts.append({
                            '구분': source,
                            '제목': title,
                            'URL': link,
                            '등록일': date_str,
                            '상세내용': detail_content
                        })
            except ValueError:
                continue

# 식약처 관련 사이트 크롤링
print("\n식약처 관련 사이트 크롤링 시작...")
for site in food_drug_urls:
    url = site['url']
    source = site['출처']
    print(f"크롤링 중: {source}")
    try:
        response = session.get(url, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        if "kcia.or.kr" in url:
            process_kcia(url, soup, source)
        elif "mfds.go.kr" in url:
            process_mfds(url, soup, source)
    except Exception as e:
        print(f"Error processing {url}: {e}")

# 데이터프레임 생성 및 열 순서 지정
df = pd.DataFrame(all_posts)
df = df[['구분', '제목', '등록일', 'URL', '상세내용']]  # 상세내용 열 추가

# 등록일 기준으로 내림차순 정렬
df['등록일'] = pd.to_datetime(df['등록일'])  # 문자열을 datetime 형식으로 변환
df = df.sort_values('등록일', ascending=False)  # 내림차순 정렬
df['등록일'] = df['등록일'].dt.strftime('%Y-%m-%d')  # 다시 문자열 형식으로 변환

try:
    # data.json 저장 (웹페이지용 고정 파일명)
    json_data = df.to_dict(orient='records')
    data_json = {
        "last_updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data": json_data
    }
    json_str = json.dumps(data_json, ensure_ascii=False, indent=2)
    with open('data.json', 'w', encoding='utf-8') as f:
        f.write(json_str)

    print(f"\n크롤링 완료!")
    print(f"총 게시글 수: {len(all_posts)}")
    print(f"data.json 파일이 업데이트되었습니다.")

    # 로그 파일에 실행 기록 추가
    log_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{log_time}] 크롤링 완료 | 게시글 수: {len(all_posts)}\n"
    with open('crawl_log.txt', 'a', encoding='utf-8') as log_f:
        log_f.write(log_entry)
    print(f"실행 기록이 'crawl_log.txt'에 저장되었습니다.")

    # GitHub Actions 환경에서는 워크플로우가 git push를 처리하므로 스킵
    if os.environ.get('GITHUB_ACTIONS_CRAWL'):
        print("\n✅ GitHub Actions 환경 - git push는 워크플로우에서 처리합니다.")
    else:
        # 로컬 실행 시 Git push (data.json을 레포지토리에 반영)
        project_dir = os.path.dirname(os.path.abspath(__file__))
        try:
            def run_git(cmd):
                result = subprocess.run(
                    cmd, cwd=project_dir, capture_output=True, text=True, timeout=30
                )
                return result

            print("\n📤 Git push 시작...")
            run_git(['git', 'add', 'data.json'])
            commit_msg = f"Update data.json ({datetime.datetime.now().strftime('%Y-%m-%d %H:%M')})"
            commit_result = run_git(['git', 'commit', '-m', commit_msg])
            if commit_result.returncode == 0:
                push_result = run_git(['git', 'push', '-u', 'origin', 'main'])
                if push_result.returncode == 0:
                    print("✅ data.json이 GitHub에 push되었습니다. Cloudflare Pages 배포가 시작됩니다.")
                else:
                    print(f"⚠️ Git push 실패: {push_result.stderr}")
            else:
                if 'nothing to commit' in commit_result.stdout:
                    print("ℹ️ data.json에 변경사항 없음 (이전과 동일한 데이터)")
                else:
                    print(f"⚠️ Git commit 실패: {commit_result.stderr}")
        except Exception as git_err:
            print(f"⚠️ Git 작업 중 오류: {git_err}")
            print("수동으로 git push 해주세요.")

except Exception as e:
    print(f"데이터 저장 중 오류 발생: {e}")