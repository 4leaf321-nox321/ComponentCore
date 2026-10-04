"""HWAX 포털 연계 — 포털 SSO(jwt-handoff)와 게이트웨이 위임 창구.

포털은 부르지 않는다 — 시험용 RSA 키로 launch 토큰을 서명하고, 공개키 목록(JWKS)을 받는
자리만 바꾼다. 나머지(kid 로 키 고르기 · aud · iss · 1회용 · 사람 찾기 · 세션)는 진짜로 돈다.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.main import _mount_spa
from app.modules.accounts.models import User
from app.modules.auth import sso
from app.modules.auth.models import PersonalAccessToken
from tests.api.conftest import PASSWORD, Signed, make_user

KID = "test-key"
AUD = "compcore"
ISS = "https://portal.test"
SECRET = "gateway-shared-secret"
RECIPE = {
    "nodes": [
        {"id": "s", "op": "sketch", "shapes": [{"type": "rect", "width": 10, "height": 10}]},
        {"id": "b", "op": "extrude", "sketch": "s", "distance": 5},
    ]
}


@pytest.fixture
def portal(monkeypatch: pytest.MonkeyPatch) -> Iterator[rsa.RSAPrivateKey]:
    """포털 SSO 를 켠다 — 서명 키를 돌려준다."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    jwks = {"keys": [{**public, "kid": KID, "use": "sig", "alg": "RS256"}]}
    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", lambda self: jwks)
    monkeypatch.setattr(sso, "_jwk", None)
    settings = get_settings()
    monkeypatch.setattr(settings, "portal_jwks_url", "http://portal.test/jwks.json")
    monkeypatch.setattr(settings, "portal_audience", AUD)
    monkeypatch.setattr(settings, "portal_issuer", ISS)
    monkeypatch.setattr(settings, "portal_jit_create", True)
    yield key


@pytest.fixture
def gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "heax_sso_secret", SECRET)
    monkeypatch.setattr(settings, "heax_sso_allowed_ips", "")
    monkeypatch.setattr(settings, "heax_sso_jit_create", True)


def _launch(key: rsa.RSAPrivateKey, email: str, **over: Any) -> str:
    now = int(time.time())
    claims: dict[str, Any] = {
        "aud": AUD,
        "iss": ISS,
        "iat": now,
        "exp": now + 90,
        "jti": uuid.uuid4().hex,
        "scope": "launch",
        "email": email,
        "name": "홍길동",
    }
    claims.update(over)
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": KID})


def _email() -> str:
    return f"sso-{uuid.uuid4().hex[:8]}@example.local"


def _ask(client: TestClient, email: str, *, client_id: str = "mcp", **headers: str) -> Any:
    return client.post(
        "/api/auth/sso",
        headers={
            "X-Heax-Gateway-Secret": SECRET,
            "X-Heax-User-Email": email,
            "X-Heax-User-Name": quote("홍길동"),
            "X-Heax-Client": client_id,
            **headers,
        },
    )


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── 꺼짐 ──────────────────────────────────────────────────────────────────────


def test_설정이_비면_창구가_없다(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "portal_jwks_url", "")
    monkeypatch.setattr(settings, "heax_sso_secret", "")
    assert client.post("/api/auth/portal-exchange", json={"token": "x"}).status_code == 404
    assert client.post("/api/auth/portal-callback", data={"token": "x"}).status_code == 404
    for path in ("/api/auth/sso", "/api/auth/sso/verify", "/api/auth/sso/revoke"):
        assert client.post(path, headers={"X-Heax-Gateway-Secret": ""}).status_code == 404


# ── 포털 SSO ─────────────────────────────────────────────────────────────────


def test_처음_온_사람은_계정이_생기고_토큰은_한_번만_통한다(
    client: TestClient, db: Session, portal: rsa.RSAPrivateKey
) -> None:
    email = _email()
    token = _launch(portal, email.upper(), login_id="K123")
    first = client.post("/api/auth/portal-exchange", json={"token": token})
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["user"]["email"] == email
    assert body["user"]["display_name"] == "홍길동"
    assert body["user"]["must_change_password"] is False
    assert "compcore_refresh=" in first.headers["set-cookie"]
    assert client.get("/api/auth/me", headers=_bearer(body["access_token"])).status_code == 200
    made = db.scalar(select(User).where(User.email == email))
    assert made is not None and made.sso_login_id == "K123"

    again = client.post("/api/auth/portal-exchange", json={"token": token})
    assert again.status_code == 401
    assert "이미 사용한" in again.json()["error"]["message"]


def test_있는_계정은_이메일_대소문자를_무시해_찾고_LoginId_를_새긴다(
    client: TestClient, db: Session, portal: rsa.RSAPrivateKey
) -> None:
    user = make_user(db, label="Kim", is_system_admin=False)
    answer = client.post(
        "/api/auth/portal-exchange",
        json={"token": _launch(portal, user.email.upper(), login_id="L-77")},
    )
    assert answer.status_code == 200, answer.text
    assert answer.json()["user"]["id"] == str(user.id)
    db.refresh(user)
    assert user.sso_login_id == "L-77"

    # 메일 주소가 바뀌어도 LoginId 로 같은 사람 — 새 주소를 따라간다.
    moved = _email()
    answer = client.post(
        "/api/auth/portal-exchange", json={"token": _launch(portal, moved, login_id="L-77")}
    )
    assert answer.status_code == 200, answer.text
    assert answer.json()["user"]["id"] == str(user.id)
    db.refresh(user)
    assert user.email == moved


@pytest.mark.parametrize(
    ("over", "said"),
    [
        ({"aud": "other-app"}, "aud"),
        ({"iss": "https://evil.test"}, "iss"),
        ({"scope": "api"}, "scope"),
        ({"exp": int(time.time()) - 120, "iat": int(time.time()) - 210}, "만료"),
    ],
)
def test_다른_앱_발급자_용도_만료_토큰은_거절한다(
    client: TestClient, portal: rsa.RSAPrivateKey, over: dict[str, Any], said: str
) -> None:
    answer = client.post(
        "/api/auth/portal-exchange", json={"token": _launch(portal, _email(), **over)}
    )
    assert answer.status_code == 401
    assert said in answer.json()["error"]["message"]


def test_다른_키로_서명한_토큰은_거절한다(
    client: TestClient, portal: rsa.RSAPrivateKey
) -> None:
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    answer = client.post("/api/auth/portal-exchange", json={"token": _launch(other, _email())})
    assert answer.status_code == 401


def test_정지된_계정과_자동_생성_꺼짐은_403(
    client: TestClient,
    db: Session,
    portal: rsa.RSAPrivateKey,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = make_user(db, label="stopped", is_system_admin=False)
    user.status = "suspended"
    db.commit()
    answer = client.post(
        "/api/auth/portal-exchange", json={"token": _launch(portal, user.email)}
    )
    assert answer.status_code == 403

    monkeypatch.setattr(get_settings(), "portal_jit_create", False)
    answer = client.post(
        "/api/auth/portal-exchange", json={"token": _launch(portal, _email())}
    )
    assert answer.status_code == 403
    assert "계정이 없습니다" in answer.json()["error"]["message"]


def test_임시_비밀번호_계정은_포털로_오면_변경_화면에_갇히지_않는다(
    client: TestClient, db: Session, portal: rsa.RSAPrivateKey
) -> None:
    user = make_user(db, label="fresh", is_system_admin=False)
    user.must_change_password = True
    db.commit()
    answer = client.post(
        "/api/auth/portal-exchange", json={"token": _launch(portal, user.email)}
    )
    assert answer.status_code == 200, answer.text
    assert answer.json()["user"]["must_change_password"] is False
    # 임시 비밀번호는 더 통하지 않는다.
    login = client.post("/api/auth/login", json={"email": user.email, "password": PASSWORD})
    assert login.status_code == 401


def test_타일_콜백은_접두어를_붙여_쿠키를_심고_화면으로_보낸다(
    client: TestClient, portal: rsa.RSAPrivateKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "trust_proxy", True)
    prefix = {"X-Forwarded-Prefix": "/compcore"}
    ok = client.post(
        "/api/auth/portal-callback",
        data={"token": _launch(portal, _email())},
        headers=prefix,
        follow_redirects=False,
    )
    assert ok.status_code == 303
    assert ok.headers["location"] == "/compcore/"
    cookie = ok.headers["set-cookie"]
    assert "compcore_refresh=" in cookie and "Path=/compcore/api/auth" in cookie
    assert "HttpOnly" in cookie

    bad = client.post(
        "/api/auth/portal-callback",
        data={"token": "not-a-jwt"},
        headers=prefix,
        follow_redirects=False,
    )
    assert bad.status_code == 303
    assert bad.headers["location"].startswith("/compcore/login?sso_error=")
    assert "set-cookie" not in bad.headers

    # 꾸민 접두어로 남의 사이트로 보내지 못한다.
    odd = client.post(
        "/api/auth/portal-callback",
        data={"token": "x"},
        headers={"X-Forwarded-Prefix": "//evil.test"},
        follow_redirects=False,
    )
    assert odd.headers["location"].startswith("/login?")


# ── 게이트웨이 위임 창구 ──────────────────────────────────────────────────────


def test_위임_창구는_비밀과_이메일을_본다(client: TestClient, gateway: None) -> None:
    assert (
        client.post(
            "/api/auth/sso/verify", headers={"X-Heax-Gateway-Secret": SECRET}
        ).status_code
        == 204
    )
    wrong = _ask(client, _email(), **{"X-Heax-Gateway-Secret": "nope"})
    assert wrong.status_code == 401
    assert _ask(client, "not-an-email").status_code == 401
    missing = client.post("/api/auth/sso", headers={"X-Heax-Gateway-Secret": SECRET})
    assert missing.status_code == 400


def test_허용_목록_밖에서는_403(
    client: TestClient, gateway: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "heax_sso_allowed_ips", "10.0.0.5")
    assert _ask(client, _email()).status_code == 403


def test_위임_토큰은_그_사람의_것이고_client_마다_하나다(
    client: TestClient, db: Session, gateway: None
) -> None:
    email = _email()
    first = _ask(client, email)
    assert first.status_code == 200, first.text
    data = first.json()["data"]
    assert first.json()["success"] is True
    assert data["token_type"] == "bearer" and data["expires_in"] == 2 * 86400
    token = data["access_token"]
    me = client.get("/api/auth/me", headers=_bearer(token)).json()
    assert me["email"] == email and me["display_name"] == "홍길동"

    # 그 사람의 이름으로 만든다 — 사람 세션에서 자기 작업으로 보인다.
    made = client.post(
        "/api/works",
        json={"name": "채팅으로 만듦", "recipe": RECIPE, "source": "ai"},
        headers=_bearer(token),
    )
    assert made.status_code == 201, made.text

    # 같은 client 로 다시 받으면 직전 것은 지운다. 다른 client 는 따로 산다.
    second = _ask(client, email.upper()).json()["data"]["access_token"]
    other = _ask(client, email, client_id="agent").json()["data"]["access_token"]
    assert client.get("/api/works", headers=_bearer(token)).status_code == 401
    assert client.get("/api/works", headers=_bearer(second)).status_code == 200
    names = set(
        db.scalars(
            select(PersonalAccessToken.name)
            .join(User, User.id == PersonalAccessToken.user_id)
            .where(User.email == email)
        )
    )
    assert names == {"HWAX 포털 게이트웨이 (mcp)", "HWAX 포털 게이트웨이 (agent)"}

    revoked = client.post(
        "/api/auth/sso/revoke",
        headers={
            "X-Heax-Gateway-Secret": SECRET,
            "X-Heax-User-Email": email,
            "X-Heax-Client": "mcp",
        },
    )
    assert revoked.status_code == 200 and revoked.json()["revoked"] == 1
    assert client.get("/api/works", headers=_bearer(second)).status_code == 401
    assert client.get("/api/works", headers=_bearer(other)).status_code == 200


def test_정지된_사람에게는_발급하지_않는다_404_가_아니라_403(
    client: TestClient, db: Session, gateway: None
) -> None:
    user = make_user(db, label="gone", is_system_admin=False)
    user.status = "suspended"
    db.commit()
    assert _ask(client, user.email).status_code == 403


def test_위임_토큰으로는_관리자_기능과_계정_설정을_못_쓴다(
    client: TestClient, db: Session, gateway: None, admin: Signed, member: Signed
) -> None:
    token = _ask(client, admin.email).json()["data"]["access_token"]
    headers = _bearer(token)

    denied = client.get("/api/accounts", headers=headers)
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "CCR-AUTH-0104"
    assert client.get("/api/auth/me", headers=headers).json()["is_system_admin"] is False
    # 토큰을 새로 만들어 울타리를 넘지 못한다.
    made = client.post(
        "/api/auth/tokens", json={"name": "x", "scopes": ["read"]}, headers=headers
    )
    assert made.status_code == 403
    assert made.json()["error"]["code"] == "CCR-AUTH-0109"

    # 남의 작업도 관리자 권한으로 열지 못한다 — 사람 세션의 관리자는 연다.
    theirs = client.post(
        "/api/works", json={"name": "남의 것", "recipe": RECIPE}, headers=member.headers
    ).json()["id"]
    assert client.get(f"/api/works/{theirs}", headers=headers).status_code == 403
    assert client.get(f"/api/works/{theirs}", headers=admin.headers).status_code == 200

    # 내려놓은 것은 이 요청뿐이다 — 쓰기 요청이 커밋해도 DB 의 관리자 표시는 그대로.
    assert (
        client.post(
            "/api/works", json={"name": "내 것", "recipe": RECIPE}, headers=headers
        ).status_code
        == 201
    )
    stored = db.scalar(select(User.is_system_admin).where(User.email == admin.email))
    assert stored is True
    assert client.get("/api/accounts", headers=admin.headers).status_code == 200


# ── 화면 · 접두어 ─────────────────────────────────────────────────────────────


def test_화면은_요청마다_접두어와_포털_타일을_심는다(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text(
        '<html><head><script src="./assets/a.js"></script></head></html>', encoding="utf-8"
    )
    settings = get_settings()
    monkeypatch.setattr(settings, "trust_proxy", True)
    monkeypatch.setattr(settings, "portal_jwks_url", "http://portal.test/jwks.json")
    monkeypatch.setattr(settings, "portal_system_id", "compcore")
    app = FastAPI()
    _mount_spa(app, settings.model_copy(update={"frontend_dist": tmp_path}))
    with TestClient(app) as local:
        behind = local.get("/works/abc", headers={"X-Forwarded-Prefix": "/compcore"}).text
        assert '<base href="/compcore/" />' in behind
        assert '<meta name="app-base" content="/compcore" />' in behind
        assert '<meta name="portal-system" content="compcore" />' in behind
        # 루트에 뜬 단독 설치 — 깊은 주소에서도 자산을 루트에서 찾는다.
        alone = local.get("/works/abc").text
        assert '<base href="/" />' in alone and 'content=""' in alone

    monkeypatch.setattr(settings, "portal_jwks_url", "")
    app = FastAPI()
    _mount_spa(app, settings.model_copy(update={"frontend_dist": tmp_path}))
    with TestClient(app) as local:
        assert "portal-system" not in local.get("/").text


def test_health_는_화면_주소를_알려_준다(client: TestClient) -> None:
    assert "public_url" in client.get("/api/health").json()
