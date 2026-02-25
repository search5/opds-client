# CLAUDE.md — OPDS Client Calibre Plugin

이 파일은 Claude Code가 프로젝트 컨텍스트를 복원하거나 플러그인을 처음부터 재현할 수 있도록 작성된 기술 가이드다.

---

## 프로젝트 개요

Calibre GUI에서 OPDS 피드 서버를 탐색하고 책을 라이브러리에 추가하는 플러그인.

- **라이선스**: BSD
- **Calibre 최소 버전**: 5.0
- **Python**: 3.8+ (Calibre 내장)
- **Qt 바인딩**: PyQt5 (Calibre 내장); PyQt6 enum 스타일은 try/except로 병행 지원
- **외부 pip 패키지**: 없음 — Calibre 내장 모듈만 사용

---

## 디렉터리 구조

```
opds-client/
├── Makefile                          # make build → opds_client.zip
├── README.md
├── CLAUDE.md                         # 이 파일
└── calibre_plugin/
    ├── __init__.py                   # InterfaceActionBase 서브클래스 (메타데이터만)
    ├── plugin-import-name-opds_client.txt  # 플러그인 네임스페이스 선언
    ├── config.py                     # JSONConfig 래퍼 (서버 목록 / 마지막 선택 인덱스)
    ├── opds_parser.py                # OPDS XML → dataclass 파싱
    ├── model.py                      # QAbstractTableModel (책 목록 테이블)
    ├── network.py                    # _fetch(), FetchThread, DownloadThread
    ├── server_dialog.py              # ServerDialog (추가/편집), ServerManagerDialog (관리)
    ├── dialog.py                     # OPDSDialog (메인 브라우저 UI)
    ├── main.py                       # OPDSClientAction (InterfaceAction, 진입점)
    ├── image/
    │   └── opds_client_icon.png      # 툴바 아이콘
    └── translations/
        ├── ko.po                     # 한국어 번역 소스
        └── ko.mo                     # 컴파일된 바이너리 (런타임 로드)
```

---

## 모듈 의존성 (단방향)

```
config.py       ← 독립 (JSONConfig만 사용)
opds_parser.py  ← 독립 (feedparser, ET만 사용)
model.py        ← 독립 (Qt만 사용)
network.py      ← 독립 (stdlib urllib, Qt만 사용)
server_dialog.py ← config 사용 (load_servers, save_servers)
       ↓
dialog.py       ← network, config, opds_parser, model, server_dialog 사용
       ↓
main.py         ← dialog 사용 (OPDSClientAction만 포함)
```

순환 import 없음. 각 레이어는 아래 레이어만 참조한다.

---

## Calibre 플러그인 메커니즘

### 등록 방식
- `__init__.py`의 `OPDSClientPlugin(InterfaceActionBase)`가 플러그인 메타데이터를 정의
- `actual_plugin = 'calibre_plugins.opds_client.main:OPDSClientAction'` 으로 실제 GUI 클래스를 지연 로드
- `plugin-import-name-opds_client.txt` 파일이 있어야 Calibre가 `calibre_plugins.opds_client` 네임스페이스로 인식

### 자동 주입 글로벌 (`load_translations`, `get_icons`)
- Calibre가 플러그인 zip 내 각 `.py`를 로드할 때 해당 모듈의 글로벌 네임스페이스에 자동 주입
- 명시적 import 없이 바로 호출 가능
- `load_translations()`: 번역 문자열 `_()` 사용 전 모듈 상단에서 반드시 호출
- `get_icons('image/...')`: `InterfaceAction.genesis()` 안에서만 호출 (컨텍스트 필요)

### 빌드 & 설치
```bash
make build              # calibre_plugin/ 전체를 opds_client.zip으로 압축
make clean              # zip 삭제
calibre-customize -b calibre_plugin   # 개발 중 직접 설치 (zip 없이)
```

---

## 각 모듈 상세

### `__init__.py`
`InterfaceActionBase` 서브클래스. 코드 로직 없음. 메타데이터만:
```python
class OPDSClientPlugin(InterfaceActionBase):
    name                    = 'OPDS Client'
    description             = 'OPDS 서버에서 책을 검색하고 다운로드합니다.'
    supported_platforms     = ['windows', 'osx', 'linux']
    author                  = 'User'
    version                 = (1, 0, 0)
    minimum_calibre_version = (5, 0, 0)
    actual_plugin           = 'calibre_plugins.opds_client.main:OPDSClientAction'

    def is_customizable(self):
        return False
```

---

### `config.py`
Calibre의 `JSONConfig('plugins/opds_client')` → `~/.config/calibre/plugins/opds_client.json`

**저장 스키마**:
```python
{
  "servers": [
    {
      "name": "My Server",       # 표시 이름
      "url": "http://example.com/opds",  # 루트 OPDS URL
      "auth": "basic",           # "basic" | "none"
      "username": "user",        # auth=="basic"일 때만 존재
      "password": "pass"         # 평문 저장 (Calibre 표준 방식)
    }
  ],
  "last_server": 0              # 마지막 선택한 서버 인덱스
}
```

**공개 함수**:
- `load_servers() → list` — 레거시 항목(auth 필드 없음)은 `"basic"`으로 보완
- `save_servers(servers)`
- `get_last_server() → int`
- `set_last_server(index)`

---

### `opds_parser.py`

**파싱 전략**:
1. `calibre.web.feeds.feedparser.parse()` 로 1차 파싱 (불량 XML 복구 내장)
2. feedparser 실패 + entry 없음 → `ValueError` 발생
3. `xml.etree.ElementTree`로 `<publisher><name>` 보완 (`_atom_publishers`) — feedparser가 처리 못하는 Calibre-Web 방식

**피드 타입 판별 (`_detect_feed_type`)** — 우선순위 순:
1. entry 링크에 `http://opds-spec.org/acquisition` rel → `'acquisition'`
2. feed self 링크 type에 `kind=acquisition` / `kind=navigation` → 해당 타입
3. entry 링크 mime이 `application/atom+xml` 계열 → `'navigation'`
4. 기본값 → `'navigation'`

**반환 dataclass**:
```python
@dataclass
class NavEntry:
    title: str
    url: str
    content: str = ''

@dataclass
class BookEntry:
    title: str
    authors: List[str]
    formats: List[dict]   # [{'type': 'epub', 'mime': '...', 'url': '...', 'size': int}]
    summary: str = ''
    cover_url: str = ''
    publisher: str = ''

@dataclass
class NavigationFeed:
    title: str
    entries: List[NavEntry]

@dataclass
class AcquisitionFeed:
    title: str
    entries: List[BookEntry]
    next_url: Optional[str] = None
    total_results: int = 0
```

**지원 다운로드 MIME 타입**: `epub+zip`, `pdf`, `x-mobipocket-ebook`, `mobi8-ebook`, `fb2`, `zip`, `x-cbz`, `x-cbr`

---

### `model.py`

`BookTableModel(QAbstractTableModel)` — 4컬럼 읽기 전용 테이블.

| 인덱스 | 헤더 | 내용 |
|---|---|---|
| 0 | Title | `entry.title` |
| 1 | Author | `', '.join(entry.authors)` |
| 2 | Format | `', '.join(f['type'].upper() for f in entry.formats)` |
| 3 | Size | 전체 formats 합산 → MB/KB/B 포맷 |

- `Qt.UserRole`로 `entry` 객체 자체를 반환 → `dialog.py`에서 행 선택 시 entry 취득
- `set_entries(entries)`: `beginResetModel/endResetModel` 쌍으로 안전 갱신
- `entry(row) → BookEntry`

---

### `network.py`

**상수**:
```python
_FETCH_TIMEOUT = 60      # 초
_FETCH_RETRIES = 3
_FETCH_RETRY_DELAY = 5   # 초 (재시도 사이 대기)
```

**`_fetch(url, server) → bytes`**:
- `auth == "basic"` → `HTTPPasswordMgrWithDefaultRealm` + `HTTPBasicAuthHandler`
- User-Agent: `CalibreOPDSClient/1.0`
- Accept: `application/atom+xml, application/xml, text/xml, */*`
- `URLError` / `TimeoutError` → 재시도; 최종 실패 시 마지막 예외 raise
- 서버가 HTML 반환(`Content-Type`에 `text/html`) → `ValueError` (URL/인증 설정 안내 포함)

**`FetchThread(QThread)`**:
- `finished = pyqtSignal(bytes)` / `error = pyqtSignal(str)`
- `run()` → `_fetch()` 호출, 결과를 시그널로 emit

**`DownloadThread(QThread)`**:
- `finished = pyqtSignal(str)` (저장된 파일 경로) / `error = pyqtSignal(str)`
- `run()` → `_fetch()` → 파일 write → `finished.emit(save_path)`

---

### `server_dialog.py`

**`ServerDialog(QDialog)`** — 단일 서버 추가/편집 폼:
- 필드: 서버명, URL, 인증 방식(None / Basic Auth 라디오버튼), 사용자명, 비밀번호
- 유효성 검사: 서버명 필수, URL이 `http://` 또는 `https://`로 시작해야 함
- Basic Auth가 아닐 때 username/password 필드 `setEnabled(False)`
- `get_server() → dict` 로 입력값 반환

**`ServerManagerDialog(QDialog)`** — 서버 목록 관리:
- 레이아웃: 좌측 `QListWidget` + 우측 버튼 컬럼 (Add / Edit / Delete / Move Up / Move Down / Close)
- `_add()` / `_edit()`: `ServerDialog` 띄워 결과를 받아 `save_servers()` 호출
- `_delete()`: `QMessageBox.question`으로 확인 후 삭제
- `_move_up()` / `_move_down()`: 인덱스 스왑 → `save_servers()` → `list.setCurrentRow()` 복원
- 모든 변경 즉시 `save_servers()` 로 영속화

---

### `dialog.py`

**`OPDSDialog(QDialog)`** — 메인 브라우저 UI.

**레이아웃 (위→아래)**:
```
[Server: combo ▼]  [Manage Servers]
[◄ Back] [↻ Refresh]  Path: Home > ...
┌──────────────────────────────────────┐
│  QStackedWidget                      │
│  index 0: QListWidget (Navigation)   │
│  index 1: QTableView  (Acquisition)  │
└──────────────────────────────────────┘
[Search: input] [Search]  [Download Selected]
         Page: [◄] 1 [►]
```

**상태 변수**:
```python
self._servers          # load_servers() 결과
self._url_stack        # 뒤로가기용 URL 스택 (list)
self._breadcrumb       # 경로 표시용 타이틀 목록 (list)
self._current_url      # 현재 표시 중인 URL
self._next_url         # 다음 페이지 URL (None이면 비활성)
self._prev_urls        # 이전 페이지 URL 목록 (pagination)
self._current_feed     # 마지막 파싱된 피드 객체
self._fetch_thread     # FetchThread 인스턴스
self._download_thread  # DownloadThread 인스턴스
```

**주요 흐름**:
1. 서버 선택 변경 → `_on_server_changed()` → `set_last_server()` → `_load_root()`
2. `_load_root()` → URL/breadcrumb 스택 초기화 → `_fetch_url(server['url'])`
3. `_fetch_url(url)`:
   - 상대 URL이면 `urljoin(current_url, url)` 로 절대화
   - `self.setEnabled(False)` (UI 블로킹)
   - 기존 실행 중인 `_fetch_thread` 있으면 quit/wait
   - 새 `FetchThread` 생성 → `finished` / `error` 시그널 연결 → `start()`
4. `_on_fetch_done(data)` → `parse_feed(data)` → `NavigationFeed`이면 stack[0], `AcquisitionFeed`이면 stack[1]
5. 네비게이션 항목 더블클릭 → URL/breadcrumb 스택에 push → `_fetch_url(entry.url)`
6. 뒤로가기 → URL 스택 pop, breadcrumb pop → `_fetch_url(prev_url)` + `_prev_urls` 초기화
7. 검색 → `server['url'] + ('&' if '?' in url else '?') + 'q=' + quote(query)` 로 fetch

**다운로드 흐름**:
1. 선택된 행에서 `book_model.entry(row)` 취득
2. `entry.formats`가 없으면 안내 메시지
3. formats가 2개 이상이면 `QInputDialog.getItem`으로 형식 선택
4. URL 절대화 → `tempfile.mkstemp(suffix='.ext', prefix=제목_)` 생성
5. `self.setEnabled(False)` → `DownloadThread` 시작
6. 완료 시 `do_add_books([path], entry)` 콜백 호출

**Qt5/Qt6 호환** (try/except 패턴, `dialog.py` 상단):
```python
try:
    _USER_ROLE = Qt.UserRole
    self.book_table.setSelectionBehavior(QAbstractItemView.SelectRows)
    _stretch = QHeaderView.Stretch
    _rtc    = QHeaderView.ResizeToContents
except AttributeError:
    _USER_ROLE = Qt.ItemDataRole.UserRole
    self.book_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    _stretch = QHeaderView.ResizeMode.Stretch
    _rtc    = QHeaderView.ResizeMode.ResizeToContents
```

---

### `main.py`

**`OPDSClientAction(InterfaceAction)`** — Calibre 툴바/메뉴 액션.

```python
name         = 'OPDS Client'
action_spec  = (_('OPDS Client'), None, _('Browse and download books from OPDS servers.'), None)
popup_type   = 0
allowed_in_toolbar = True
allowed_in_menu    = True
```

- `genesis()`: `get_icons('image/opds_client_icon.png')` → 아이콘 설정, `show_dialog` 연결
- `show_dialog()`: `OPDSDialog(self.gui, icon, self._add_books).exec_()`
- `_add_books(paths, entry)`: `OPDSDialog`의 `do_add_books` 콜백
  - `entry` 있음: `Metadata` 생성 → `db.import_book(mi, paths)` → `add_action.refresh_gui()` → 임시 파일 삭제
  - `entry` 없음: `calibre.gui2.add.Adder` 사용 → `_on_added()` 콜백으로 파일 삭제

---

## 국제화 (i18n)

- 모든 사용자 노출 문자열: `_('...')` 래핑 필수
- 각 `.py` 파일 상단에 `load_translations()` 호출 (Calibre가 자동 주입)
- `translations/ko.po` → `msgfmt ko.po -o ko.mo` 로 컴파일
- 새 언어 추가: `ko.po` 복사 → 번역 → `msgfmt` → 재설치

---

## 코딩 규칙

- **PyQt5 import만** 사용 (PyQt6 직접 import 금지; enum 차이는 try/except로 흡수)
- **외부 패키지 import 금지** — Calibre 내장 모듈만 사용
- `_()` 사용 전 `load_translations()` 모듈 상단에 필수
- Qt 시그널/슬롯 연결은 `_build_ui()` 말미에 모아서 작성
- 스레드 완료/오류 핸들러에서 반드시 `self.setEnabled(True)` 복원
- `print()` 디버그 대신 `from calibre.utils.logging import default_log` 사용

---

## 주요 Calibre API

| API | 모듈 | 용도 |
|---|---|---|
| `InterfaceActionBase` | `calibre.customize` | 플러그인 메타데이터 베이스 클래스 |
| `InterfaceAction` | `calibre.gui2.actions` | GUI 툴바 액션 베이스 클래스 |
| `JSONConfig` | `calibre.utils.config` | 설정 영속화 |
| `feedparser_parse` | `calibre.web.feeds.feedparser` | OPDS XML 파싱 (불량 XML 복구 내장) |
| `error_dialog` / `info_dialog` | `calibre.gui2` | 표준 오류/정보 다이얼로그 |
| `Metadata` | `calibre.ebooks.metadata.book.base` | 책 메타데이터 객체 |
| `Adder` | `calibre.gui2.add` | 비동기 책 추가 |
| `load_translations()` | Calibre 자동 주입 | i18n 초기화 (`_()` 활성화) |
| `get_icons('image/...')` | Calibre 자동 주입 | 플러그인 zip 내 이미지 로드 |

---

## 알려진 제약 / 향후 개선 방향

- [ ] 비밀번호 암호화 저장 (현재 평문)
- [ ] 책 목록에 커버 썸네일 표시
- [ ] 이미 라이브러리에 있는 책 필터링
- [ ] tags, series, rating 등 추가 메타데이터 가져오기
- [ ] OPDS 2.0 (JSON 기반) 지원
