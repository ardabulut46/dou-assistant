import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from open_webui.constants import ERROR_MESSAGES
from open_webui.internal.db import get_session
from open_webui.internal.obs_db import get_obs_session
from open_webui.models.obs import (
    ObsItems,
    ObsItemModel,
    ObsItemCreateForm,
    ObsItemUpdateForm,
)
from open_webui.utils.access_control import has_permission
from open_webui.utils.auth import get_verified_user

log = logging.getLogger(__name__)

router = APIRouter()


def _require_obs_write(request: Request, user, db: Session):
    # Admin always allowed; others need obs.write permission via groups/default config.
    if user.role == "admin":
        return
    if not has_permission(user.id, "obs.write", request.app.state.config.USER_PERMISSIONS, db=db):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.UNAUTHORIZED,
        )


@router.get("/items", response_model=list[ObsItemModel])
async def list_obs_items(
    request: Request,
    kind: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
    obs_db: Session = Depends(get_obs_session),
):
    # Students can read, but allow disabling feature if desired
    if user.role != "admin" and not has_permission(
        user.id, "features.obs", request.app.state.config.USER_PERMISSIONS, db=db
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.UNAUTHORIZED,
        )

    ObsItems.init_tables()
    return ObsItems.list_items(kind=kind, skip=skip, limit=limit, db=obs_db)


@router.get("/items/{item_id}", response_model=ObsItemModel)
async def get_obs_item(
    request: Request,
    item_id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
    obs_db: Session = Depends(get_obs_session),
):
    if user.role != "admin" and not has_permission(
        user.id, "features.obs", request.app.state.config.USER_PERMISSIONS, db=db
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.UNAUTHORIZED,
        )

    ObsItems.init_tables()
    item = ObsItems.get_item(item_id, db=obs_db)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return item


@router.post("/items", response_model=ObsItemModel)
async def create_obs_item(
    request: Request,
    form_data: ObsItemCreateForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
    obs_db: Session = Depends(get_obs_session),
):
    _require_obs_write(request, user, db)
    ObsItems.init_tables()
    return ObsItems.create_item(user.id, form_data, db=obs_db)


@router.put("/items/{item_id}", response_model=ObsItemModel)
async def update_obs_item(
    request: Request,
    item_id: str,
    form_data: ObsItemUpdateForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
    obs_db: Session = Depends(get_obs_session),
):
    _require_obs_write(request, user, db)
    ObsItems.init_tables()
    item = ObsItems.update_item(item_id, form_data, db=obs_db)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return item


@router.delete("/items/{item_id}")
async def delete_obs_item(
    request: Request,
    item_id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
    obs_db: Session = Depends(get_obs_session),
):
    _require_obs_write(request, user, db)
    ObsItems.init_tables()
    ok = ObsItems.delete_item(item_id, db=obs_db)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return {"status": True}

