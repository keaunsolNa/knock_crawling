# 🎬 knock_crawling

> **KNOCK** - 영화, 공연예술 개봉일 알림 서비스의 백엔드 크롤링 서비스

[![Heroku](https://img.shields.io/badge/Deploy-Heroku-430098?logo=heroku&logoColor=white)](https://heroku.com)
[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)](https://www.python.org/)
[![Elasticsearch](https://img.shields.io/badge/Elasticsearch-7.x-orange?logo=elasticsearch)](https://www.elastic.co/elasticsearch/)

---

## 🔍 소개

`knock_crawling`은 [KNOCK](https://github.com/keaunsolNa/knock_project) 서비스의 핵심 데이터 수집을 담당하는 **Python 기반의 콘텐츠 크롤러**입니다.  
국내 주요 영화/공연 API 및 웹사이트를 주기적으로 크롤링하여, Elasticsearch에 최신 개봉 정보를 업데이트합니다.

이 서비스는 Heroku에 배포되어 있으며,  
**KNOCK 유저가 구독한 콘텐츠의 개봉 알림 푸시 기반이 되는 데이터**를 제공합니다.

---

## 🛠️ 기술 스택

| 영역        | 스택 / 라이브러리 |
|-------------|------------------|
| 언어        | Python 3.10+ |
| 웹 크롤링   | `Selenium`, `BeautifulSoup`, `requests` |
| 데이터 저장 | `Elasticsearch (Bonsai)` |
| 스케줄러    | `APScheduler` |
| 배포        | Heroku (worker dyno) |

---

## 📦 주요 크롤링 대상

| 카테고리 | 출처 |
|----------|------|
| 🎬 영화 | CGV, MEGABOX, LOTTE CINEMA, KOFIC |
| 🎭 공연 | KOPIS (공연예술통합전산망) |

크롤링 데이터는 Elasticsearch 인덱스로 저장되며,  
KNOCK 프론트엔드 및 백엔드에서 해당 정보를 검색/활용합니다.

---

## 🔁 크롤링 스케줄

- **Heroku Scheduler** 또는 **APScheduler**를 통해 주기적 실행
- 실행 시 전체 콘텐츠를 크롤링하고, 기존 데이터와 비교하여 Elasticsearch에 `upsert`, `delete`, `merge` 처리 수행

---

## 🚀 연동 구조

graph TD
    A[KNOCK 사용자] --> B[프론트엔드 - Next.js]
    B --> C[백엔드 API - Spring Boot]
    C --> D[Elasticsearch (Bonsai)]
    F[knock_crawling (Python)]
    F --> D

## 🗂️ 디렉터리 구조

```plaintext
knock_crawling/
├── crawling/
│   ├── services/         # CGV, MEGABOX, LOTTE, KOPIS 등 각 크롤러
│   ├── base/             # 공통 크롤링 로직 및 WebDriver 설정
│   └── utils/            # 데이터 병합, 시간 변환 등 유틸
├── infra/
│   ├── elasticsearch_config.py
│   ├── es_utils.py
├── scheduler/            # APScheduler 기반 실행 스크립트
├── requirements.txt
└── Procfile              # Heroku worker용 프로세스 설정
```

---

## 🧪 실행 방법 (로컬)

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. `.env` 파일 생성

```dotenv
BONSAI_URL=

KOPIS_API_URL=http://kopis.or.kr/openApi/restful/pblprfr
KOPIS_API_URL_SUB=http://kopis.or.kr/openApi/restful/pblprfr
KOPIS_API_KEY=

KOFIC_API_URL=http://www.kobis.or.kr/kobisopenapi/webservice/rest/movie/searchMovieList.json
KOFIC_API_URL_SUB=https://www.kobis.or.kr/kobisopenapi/webservice/rest/movie/searchMovieInfo.json
KOFIC_API_KEY=

MEGABOX_API_URL=https://www.megabox.co.kr/movie/comingsoon
MEGABOX_API_URL_SUB=https://www.megabox.co.kr/movie-detail?rpstMovieNo=

CGV_API_URL=https://m.cgv.co.kr/WebAPP/MovieV4/movieList.aspx?mtype=now&iPage=1
CGV_API_URL_SUB=https://www.cgv.co.kr/movies/detail-view/?midx=

LOTTE_API_URL=https://www.lottecinema.co.kr/NLCHS/Movie/List?flag=5
LOTTE_API_URL_SUB=https://www.lottecinema.co.kr/NLCMW/Movie/MovieDetailView?movie=

DISCORD_WEBHOOK_URL=

CRON_MINUTE=
```

### 3. 실행

```bash
python scheduler/main.py
```

---

## ☁️ 배포 정보

- **플랫폼**: Heroku (Python Worker Dyno)
- **스토리지**: Elasticsearch (Bonsai Addon)
- **자동 실행**: APScheduler (내부) + Heroku Scheduler (외부 Trigger)

---

## 🧑‍💻 개발자

| 이름   | 역할             | GitHub |
|--------|------------------|--------|
| 나큰솔 | 백엔드, 크롤러 개발 | [@keaunsolNa](https://github.com/keaunsolNa) |

---

## 🔗 관련 서비스

- 🛎️ [KNOCK 메인 레포지토리](https://github.com/keaunsolNa/Knock)
- 📄 [KNOCK 소개 페이지 (Notion)](https://www.notion.so/1d0eb6c84ddd80da9dece7e09ec68c77)

---

## 📄 라이선스

```
MIT License

Copyright (c) 2025 keaunsolNa

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
