"""Auth & account management endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas import (
    ChildCreate,
    DeleteChildRequest,
    GetDetailsRequest,
    UserCreate,
    UserLogin,
    UserDetails,
)
from app.services.auth_service import AuthService

router = APIRouter(tags=["auth"])


@router.post("/register/")
async def register_user(user: UserCreate):
    svc = AuthService()
    return svc.register(user.email, user.name, user.password)


@router.post("/login")
async def login_user(user: UserLogin):
    svc = AuthService()
    return svc.login(user.email, user.password)


@router.post("/save-user-data/")
async def save_user_data(user_data: UserCreate):
    svc = AuthService()
    return svc.save_user_data(user_data.idToken, user_data.name, user_data.email)


@router.post("/user-details/")
async def get_user_details(user_details: UserDetails):
    svc = AuthService()
    return svc.get_user_details(
        user_details.idToken, user_details.email, user_details.name, user_details.age
    )


@router.post("/add_child/")
async def add_child(child: ChildCreate):
    svc = AuthService()
    return svc.add_child(child.idToken, child.name, child.age, child.grade)


@router.post("/get_children/")
async def get_children(request: GetDetailsRequest):
    svc = AuthService()
    return svc.get_children(request.idToken)


@router.post("/get_all_child_details/")
async def get_all_child_details(request: GetDetailsRequest):
    svc = AuthService()
    return svc.get_all_child_details(request.idToken)


@router.delete("/delete_child/")
async def delete_child(request: DeleteChildRequest):
    svc = AuthService()
    return svc.delete_child(request.idToken, request.child_id)
