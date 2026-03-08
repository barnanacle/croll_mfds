import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import datetime
import pandas as pd
import re
import json
import time  # 딜레이를 위한 time 모듈

# 공통 헤더
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.61 Safari/537.36'
}

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


def get_detail_content(url):
    """
    게시글의 상세 내용을 크롤링하는 함수
    """
    try:
        response = requests.get(url, headers=headers, timeout=10)
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
            content = content_div.get_text(separator='\n', strip=True)
            content = re.sub(r'\n\s*\n', '\n', content)
            return content.strip()
        return ""
    except Exception as e:
        print(f"상세 내용 크롤링 중 오류 발생: {url} - {str(e)}")
        return ""


def process_mfds(url, soup, source, all_posts):
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
                        detail_content = ""
                        if any(region in source for region in ['서울', '경인', '부산', '대전', '광주', '대구', '공무원지침서', '민원인안내서']):
                            detail_content = get_detail_content(link)
                            time.sleep(0.5)

                        all_posts.append({
                            '구분': source,
                            '제목': title,
                            'URL': link,
                            '등록일': date_str,
                            '상세내용': detail_content
                        })
            except ValueError:
                continue


def process_kcia(url, soup, source, all_posts):
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
                        detail_content = get_detail_content(link)
                        time.sleep(0.5)

                        all_posts.append({
                            '구분': source,
                            '제목': title,
                            'URL': link,
                            '등록일': date_str,
                            '상세내용': detail_content
                        })
            except ValueError:
                continue


def run_crawling():
    all_posts = []

    print("\n식약처 관련 사이트 크롤링 시작...")
    for site in food_drug_urls:
        url = site['url']
        source = site['출처']
        print(f"크롤링 중: {source}")
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            if "kcia.or.kr" in url:
                process_kcia(url, soup, source, all_posts)
            elif "mfds.go.kr" in url:
                process_mfds(url, soup, source, all_posts)
        except Exception as e:
            print(f"Error processing {url}: {e}")

    if not all_posts:
        print("수집된 게시글이 없습니다.")
        return

    # 데이터프레임 생성 및 정렬
    df = pd.DataFrame(all_posts)
    df = df[['구분', '제목', '등록일', 'URL', '상세내용']]
    df['등록일'] = pd.to_datetime(df['등록일'])
    df = df.sort_values('등록일', ascending=False)
    df['등록일'] = df['등록일'].dt.strftime('%Y-%m-%d')

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
    print(f"크롤링 결과가 'data.json' 파일로 저장되었습니다.")


if __name__ == '__main__':
    run_crawling()
