"""Productized multi-user API."""
from __future__ import annotations

from urllib.parse import unquote

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import JSONResponse

from training.product.accounts import ProductAuthService, set_session_cookie
from training.product.repository import ProductRepository
from training.product.uploads import ProductFitUploadService


router = APIRouter()


@router.post("/auth/register")
def register(payload: dict = Body(...)):
    auth = ProductAuthService()
    user = auth.register(
        email=payload.get("email", ""),
        password=payload.get("password", ""),
        display_name=payload.get("display_name", ""),
    )
    token = auth.create_session(user["id"])
    response = JSONResponse({"success": True, "user": user})
    set_session_cookie(response, token)
    return response


@router.post("/auth/login")
def login(payload: dict = Body(...)):
    user, token = ProductAuthService().login(payload.get("email", ""), payload.get("password", ""))
    response = JSONResponse({"success": True, "user": user})
    set_session_cookie(response, token)
    return response


@router.post("/auth/logout")
def logout(request: Request):
    response = JSONResponse({"success": True})
    ProductAuthService().logout(request, response)
    return response


@router.get("/me")
def me(request: Request):
    user = ProductAuthService().require_user(request)
    return {"user": user, "profile": ProductRepository().get_profile(user["id"])}


@router.get("/onboarding")
def get_onboarding(request: Request):
    user = ProductAuthService().require_user(request)
    return {"profile": ProductRepository().get_profile(user["id"])}


@router.post("/onboarding")
def save_onboarding(request: Request, payload: dict = Body(...)):
    user = ProductAuthService().require_user(request)
    if payload.get("accepted_terms") is not True:
        raise HTTPException(status_code=400, detail="Privacy and training disclaimer must be accepted")
    profile = ProductRepository().save_profile(user["id"], payload)
    refreshed = ProductAuthService().get_user_by_id(user["id"])
    return {"success": True, "user": refreshed, "profile": profile}


@router.post("/fit/upload")
async def upload_fit(request: Request):
    user = ProductAuthService().require_user(request)
    filename = unquote(request.headers.get("x-filename") or "upload.fit")
    content = await request.body()
    result = ProductFitUploadService().upload_fit(user["id"], filename, content)
    return {"success": True, **result}


@router.get("/today/simple")
def simple_today(request: Request):
    user = ProductAuthService().require_user(request)
    return ProductRepository().build_simple_today(user)


@router.get("/privacy/export")
def export_privacy_data(request: Request):
    user = ProductAuthService().require_user(request)
    return {"success": True, "data": ProductRepository().export_user_data(user)}


@router.delete("/privacy/account")
def delete_account(request: Request, payload: dict = Body(default={})):
    user = ProductAuthService().require_user(request)
    if payload.get("confirmation") != "DELETE_MY_DATA":
        raise HTTPException(status_code=400, detail="confirmation must be DELETE_MY_DATA")
    counts = ProductRepository().delete_user_data(user["id"])
    response = JSONResponse({"success": True, "deleted": counts})
    ProductAuthService().logout(request, response)
    return response


@router.post("/notifications/subscribe")
def subscribe_notifications(request: Request, payload: dict = Body(...)):
    user = ProductAuthService().require_user(request)
    endpoint = payload.get("endpoint")
    if not endpoint:
        raise HTTPException(status_code=400, detail="endpoint is required")
    keys = payload.get("keys") or {}
    subscription = ProductRepository().upsert_notification_subscription(
        user_id=user["id"],
        endpoint=endpoint,
        p256dh=keys.get("p256dh") or payload.get("p256dh") or "",
        auth=keys.get("auth") or payload.get("auth") or "",
        user_agent=request.headers.get("user-agent", ""),
    )
    return {"success": True, "subscription": subscription}


@router.post("/notifications/test")
def test_notification(request: Request):
    user = ProductAuthService().require_user(request)
    notification = ProductRepository().queue_notification(
        user_id=user["id"],
        title="训练提醒已开启",
        body="之后系统可以在训练前、跑后和晚间复盘时提醒你。",
        url="/product/today",
    )
    return {"success": True, "notification": notification}


@router.get("/admin/users")
def admin_users(request: Request):
    ProductAuthService().require_admin(request)
    return {"items": ProductRepository().list_users()}
