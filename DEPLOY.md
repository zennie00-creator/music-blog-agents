# 배포 & 사용 가이드 (처음부터 순서대로)

휴대폰·아이패드·PC 어디서나 쓸 수 있게 이 앱을 인터넷에 올리는 방법입니다.
**터미널 없이 웹 브라우저만으로** 할 수 있습니다.

전체 순서:
1. Streamlit Cloud에 앱 배포 (먼저 데모 모드로 동작 확인)
2. Whoop 개발자 앱 등록 (실제 운동 데이터 연동)
3. 매일 사용하는 법 (네이버 블로그에 올리기)

---

## 준비물

- **GitHub 계정** (이 코드가 이미 올라가 있음)
- **Anthropic API 키** — https://console.anthropic.com → API Keys 에서 발급. `sk-ant-...` 형태.
- (나중에) **Whoop 계정**

---

## 1단계 — Streamlit Cloud에 배포하기

> 먼저 Whoop 없이 "데모 데이터"로 앱을 띄워서 잘 되는지 확인합니다.

1. **share.streamlit.io** 접속 → **Continue with GitHub** 로 로그인
   (GitHub 권한 요청이 뜨면 승인)
2. 오른쪽 위 **Create app**(또는 New app) 클릭 → **Deploy a public app from GitHub** 선택
3. 아래 3개를 채웁니다:
   - **Repository**: `zennie00-creator/music-blog-agents`
   - **Branch**: `claude/whoop-api-workout-logging-vgolrj`
     (나중에 이 브랜치를 main에 합치면 `main`으로 바꾸면 됩니다)
   - **Main file path**: `app.py`
4. **Advanced settings** 클릭 → **Secrets** 칸에 아래를 붙여넣기:
   ```toml
   ANTHROPIC_API_KEY = "여기에-발급받은-키-붙여넣기"
   ```
5. **Deploy** 클릭 → 1~2분 기다리면 앱이 뜹니다.
6. 주소가 생깁니다: 예) `https://music-blog-agents-xxxx.streamlit.app`
   **이 주소를 메모해두세요.** (2단계 Whoop 설정에 필요)

✅ 이제 그 주소로 접속 → **🏃 오늘 운동** → **오늘 운동 불러오기** 를 누르면
Whoop 없이도 샘플 데이터로 운동 일지가 만들어지는 걸 볼 수 있습니다.

---

## 2단계 — Whoop 개발자 앱 등록 (실제 데이터 연동)

1. **developer.whoop.com** 접속 → Whoop 계정으로 로그인
2. **Create Application**(앱 만들기) 클릭
3. 다음을 입력합니다:
   - **Name**: 아무 이름 (예: `내 운동일지`)
   - **Redirect URIs**: 1단계에서 메모한 앱 주소를 **그대로** 입력
     예) `https://music-blog-agents-xxxx.streamlit.app`
     ⚠️ 오타·슬래시 하나까지 정확히 일치해야 합니다.
   - **Scopes**: `read:workout`, `read:recovery`, `read:profile`, `offline` 체크
4. 저장하면 **Client ID** 와 **Client Secret** 이 나옵니다. 복사해두세요.
5. 다시 **Streamlit Cloud** → 내 앱 → 오른쪽 아래 **⋮ (Manage app)** → **Settings** → **Secrets**
   에 아래 3줄을 추가합니다 (기존 ANTHROPIC 줄은 그대로 두고):
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   WHOOP_CLIENT_ID = "여기에-Client-ID"
   WHOOP_CLIENT_SECRET = "여기에-Client-Secret"
   WHOOP_REDIRECT_URI = "https://music-blog-agents-xxxx.streamlit.app"
   ```
   > `WHOOP_REDIRECT_URI` 는 3번에서 등록한 Redirect URI 와 **완전히 똑같아야** 합니다.
6. 저장하면 앱이 자동으로 재시작됩니다.

✅ 이제 앱 → **🏃 오늘 운동** 화면에 **🔗 Whoop 계정 연결하기** 버튼이 보입니다.
누르면 Whoop 로그인 → 승인 → 앱으로 자동 복귀하며 "✅ Whoop 계정 연결됨" 이 뜹니다.
한 번 연결하면 토큰이 저장되어 다음부터는 다시 로그인할 필요가 없습니다.

---

## 3단계 — 매일 사용하는 법

1. 앱 접속 (휴대폰이면 주소를 홈 화면에 추가해두면 앱처럼 열립니다)
2. **🏃 오늘 운동** 선택
3. **오늘 운동 불러오기** → 오늘 한 운동을 (여러 개면 전부) 선택
4. 종목명·거리가 이상하면 수정 (트레드밀이면 거리 직접 입력), **기분·몸 상태** 적기
5. **분석하고 초안 만들기** → 코치 분석 + 운동 일지 초안 확인
6. 마음에 안 들면 **수정 요청**에 한 줄 적고 다시 생성
7. **완성 & 저장** → **📋 네이버에 붙여넣기 (추천)** 탭 → 복사 아이콘 클릭
8. **네이버 블로그 → 글쓰기** 화면에 그대로 붙여넣기 → 사진 추가 → 발행
   > 네이버 새 에디터는 HTML 직접 붙여넣기를 지원하지 않아, 깔끔한 텍스트로 붙입니다.
   > 통계 표까지 살리려면 **🟢 HTML (고급)** 탭 안내를 참고하세요.

> 음악 감상 글도 같은 앱에서 **🎼 음악 감상** 모드로 똑같이 쓸 수 있습니다.

---

## (선택) Notion 자동 발행 설정

네이버와 달리 Notion은 API로 글을 **자동 생성**할 수 있어, 복사·붙여넣기 없이
**버튼 한 번으로 발행**됩니다. (제목 + 통계 콜아웃 + 소제목·본문까지 자동)

1. **Integration 만들기**: https://www.notion.so/my-integrations → **New integration**
   → 이름 입력(예: `운동일지 봇`) → 만들면 **Internal Integration Secret**(토큰) 복사
   (`secret_...` 또는 `ntn_...` 형태)
2. **글을 쌓을 위치 정하기**: Notion에서 페이지 하나(예: 기존 **운동일지** 페이지)를 열거나
   새로 만듭니다. 데이터베이스여도 됩니다. (앱이 페이지/DB를 자동 감지합니다)
3. **그 위치를 Integration에 공유**: 해당 페이지 오른쪽 위 **···** → **Connections(연결)**
   → 1번에서 만든 Integration 선택. (이걸 안 하면 권한이 없어 발행이 실패합니다)
4. **부모 ID 복사**: 그 페이지를 브라우저로 열었을 때 주소 끝의 32자리 문자열이 ID입니다.
   예) `notion.so/운동일지-**2b3c...ffff**` → 굵은 부분.
   (Notion 앱에서는 ··· → **Copy link** 로 주소를 얻어 끝부분을 쓰면 됩니다)
5. **Streamlit Secrets에 추가**:
   ```toml
   NOTION_TOKEN = "secret_... 또는 ntn_..."
   NOTION_PARENT_ID = "복사한 32자리 ID"
   ```
6. Save → 앱 재시작 후, 운동 일지 완성 화면 아래 **📝 Notion에 올리기** 버튼이 활성화됩니다.
   누르면 Notion에 글이 생기고 **🔗 Notion에서 열기** 링크가 나옵니다.

### 📓 개발 일지 모드 (선택)

개발 일지를 별도 Notion 페이지에 올리려면:

1. Notion에 "개발일지" 페이지를 만들고 **같은 Integration을 Connections로 연결**
   (Integration은 재사용 — 새로 만들 필요 없음)
2. 그 페이지 링크의 32자리 ID를 Secrets에 추가:
   ```toml
   NOTION_DEVLOG_PARENT_ID = "개발일지 페이지의 32자리 ID"
   ```
3. 앱 첫 화면 → **📓 개발 일지** 모드에서 메모 작성/불러오기 → 스크린샷 첨부 → 발행

> 이 값을 생략하면 개발 일지도 NOTION_PARENT_ID(운동일지) 페이지로 올라갑니다.

### (선택) 시계열 코치 로그를 다른 페이지에 쌓기

운동 일지를 완성할 때마다 그날의 (요약·코치 분석·내 답장)이 "운동 코치 로그"
페이지에 JSON으로 쌓여, 다음 일지 분석 때 코치가 지난 대화를 이어갑니다.
기본은 NOTION_PARENT_ID 아래에 자동 생성되며, 따로 두고 싶으면:

```toml
NOTION_COACHLOG_PARENT_ID = "코치 로그를 쌓을 페이지의 32자리 ID"
```

> 생략하면 NOTION_PARENT_ID 페이지에 "운동 코치 로그" 페이지가 자동으로 만들어집니다.

---

## 팁 & 참고

- **사이드바 프로필**: 운동 모드에서 "운동 목표 / 톤" 을 저장해두면 일지가 더 내 스타일로 나옵니다.
- **API 키는 절대 코드에 넣지 말 것** — 반드시 Streamlit **Secrets** 에만 넣습니다.
- **네이버 자동 발행은 불가**: 네이버는 글쓰기 공식 API가 없어, 마지막 "붙여넣기"만 수동입니다. (계정 안전을 위해 자동 로그인 매크로는 권장하지 않습니다.)
- 무료 Streamlit Cloud는 한동안 접속이 없으면 잠자기 상태가 됩니다. 다시 접속하면 몇 초 뒤 깨어납니다.
