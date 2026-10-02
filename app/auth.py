"""구글 / 카카오 OAuth 로그인.

전사 기능 자체는 로그인 없이 쓸 수 있고, 히스토리 저장·조회에만 로그인이
필요하다. 각 제공자의 클라이언트 ID/SECRET이 환경변수로 설정되지 않으면
해당 로그인 버튼은 비활성 상태로 안내된다 (README 참고).
"""

from __future__ import annotations

import os

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Request
from starlette.responses import RedirectResponse

from .db import get_session
from .models import User

router = APIRouter(prefix="/auth", tags=["auth"])
oauth = OAuth()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
KAKAO_CLIENT_ID = os.getenv("KAKAO_CLIENT_ID")
KAKAO_CLIENT_SECRET = os.getenv("KAKAO_CLIENT_SECRET")

GOOGLE_ENABLED = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)
KAKAO_ENABLED = bool(KAKAO_CLIENT_ID and KAKAO_CLIENT_SECRET)

if GOOGLE_ENABLED:
    oauth.register(
        name="google",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

if KAKAO_ENABLED:
    oauth.register(
        name="kakao",
        client_id=KAKAO_CLIENT_ID,
        client_secret=KAKAO_CLIENT_SECRET,
        access_token_url="https://kauth.kakao.com/oauth/token",
        authorize_url="https://kauth.kakao.com/oauth/authorize",
        api_base_url="https://kapi.kakao.com/",
        client_kwargs={"scope": "profile_nickname account_email"},
    )


def auth_status() -> dict:
    return {"google": GOOGLE_ENABLED, "kakao": KAKAO_ENABLED}


def current_user(request: Request) -> dict | None:
    return request.session.get("user")


def _upsert_user(provider: str, provider_id: str, email: str | None, display_name: str | None) -> User:
    db = get_session()
    try:
        user = (
            db.query(User)
            .filter_by(provider=provider, provider_id=provider_id)
            .one_or_none()
        )
        if user is None:
            user = User(
                provider=provider,
                provider_id=provider_id,
                email=email,
                display_name=display_name,
            )
            db.add(user)
        else:
            user.email = email or user.email
            user.display_name = display_name or user.display_name
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


@router.get("/google/login")
async def google_login(request: Request):
    redirect_uri = request.url_for("google_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback", name="google_callback")
async def google_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    info = token.get("userinfo") or await oauth.google.userinfo(token=token)
    user = _upsert_user(
        provider="google",
        provider_id=info["sub"],
        email=info.get("email"),
        display_name=info.get("name"),
    )
    request.session["user"] = {
        "id": user.id,
        "provider": "google",
        "email": user.email,
        "display_name": user.display_name,
    }
    return RedirectResponse(url="/")


@router.get("/kakao/login")
async def kakao_login(request: Request):
    redirect_uri = request.url_for("kakao_callback")
    return await oauth.kakao.authorize_redirect(request, redirect_uri)


@router.get("/kakao/callback", name="kakao_callback")
async def kakao_callback(request: Request):
    token = await oauth.kakao.authorize_access_token(request)
    resp = await oauth.kakao.get("v2/user/me", token=token)
    info = resp.json()
    kakao_account = info.get("kakao_account", {})
    profile = kakao_account.get("profile", {})
    user = _upsert_user(
        provider="kakao",
        provider_id=str(info["id"]),
        email=kakao_account.get("email"),
        display_name=profile.get("nickname"),
    )
    request.session["user"] = {
        "id": user.id,
        "provider": "kakao",
        "email": user.email,
        "display_name": user.display_name,
    }
    return RedirectResponse(url="/")


@router.post("/logout")
async def logout(request: Request):
    request.session.pop("user", None)
    return RedirectResponse(url="/", status_code=303)
