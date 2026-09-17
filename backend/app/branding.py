"""이 제품이 무엇인가.

AutoJigGenerator 는 **하나의 독립 플랫폼**이다. StandardPlatform 의 인스턴스(확장 모듈)가
아니라, 그 틀에서 로그인 · 설정 · 오류 규약 같은 제반 구조만 가져와 세운 저장소다.
그래서 여기 이름은 기본값이 아니라 **이 제품의 이름**이다 — 다만 설치마다 화면에 다른
이름을 붙일 수 있게 `.env` 의 `APP_NAME` 이 덮을 수 있다(app/config.py).

## 오류 코드 접두사

`AJG-<MODULE>-<NNNN>`. 코드 곳곳의 `errors.code()` 가 조립하는 문자열이라 빌드에 박힌다 —
로그 검색이 한 값으로 걸려야 한다.
"""

from __future__ import annotations

#: 화면 제목 · API 문서 제목 · 기동 로그.
DEFAULT_APP_NAME = "AutoJigGenerator"

#: 기계가 읽는 이름 — **DB 이름 · 리프레시 쿠키 이름이 여기서 나온다.**
#: 소문자 · 숫자 한 덩어리, 32자 이내. 같은 서버의 다른 플랫폼과 겹치면 쿠키가 서로를 덮어
#: **번갈아 로그아웃**되고, 그 원인은 코드 어디에도 없다.
DEFAULT_APP_SLUG = "autojig"

#: 한 줄 설명 — 로그인 화면과 사이드바.
DEFAULT_APP_TAGLINE = "제품 STEP 에서 지그를 자동으로"

#: 오류 코드 접두사. **한 저장소에 하나뿐이어야 한다.**
ERROR_PREFIX = "AJG"
