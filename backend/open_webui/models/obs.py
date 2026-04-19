import time
import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict
from sqlalchemy import BigInteger, Column, Text, JSON
from sqlalchemy.orm import Session

from open_webui.internal.obs_db import ObsBase, obs_engine, get_obs_db_context

####################
# OBS DB Schema
####################


class ObsItem(ObsBase):
    __tablename__ = "obs_item"

    id = Column(Text, primary_key=True, unique=True)
    kind = Column(Text)  # e.g. announcement | card | profile | custom

    title = Column(Text, nullable=True)
    data = Column(JSON, nullable=True)  # flexible payload for UI

    created_by = Column(Text, nullable=True)  # user id (from primary DB)
    created_at = Column(BigInteger)
    updated_at = Column(BigInteger)


class ObsItemModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    title: Optional[str] = None
    data: Optional[dict] = None
    created_by: Optional[str] = None
    created_at: int
    updated_at: int


class ObsItemCreateForm(BaseModel):
    kind: str
    title: Optional[str] = None
    data: Optional[dict] = None


class ObsItemUpdateForm(BaseModel):
    kind: Optional[str] = None
    title: Optional[str] = None
    data: Optional[dict] = None


class ObsItemsTable:
    def init_tables(self):
        # Ensure table exists on the OBS DB
        ObsBase.metadata.create_all(bind=obs_engine)

    def list_items(
        self,
        kind: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
        db: Optional[Session] = None,
    ) -> list[ObsItemModel]:
        with get_obs_db_context(db) as session:
            q = session.query(ObsItem)
            if kind:
                q = q.filter(ObsItem.kind == kind)
            q = q.order_by(ObsItem.updated_at.desc()).offset(skip).limit(limit)
            return [ObsItemModel.model_validate(x) for x in q.all()]

    def get_item(
        self, item_id: str, db: Optional[Session] = None
    ) -> Optional[ObsItemModel]:
        with get_obs_db_context(db) as session:
            item = session.query(ObsItem).filter(ObsItem.id == item_id).first()
            return ObsItemModel.model_validate(item) if item else None

    def create_item(
        self, user_id: str, form: ObsItemCreateForm, db: Optional[Session] = None
    ) -> ObsItemModel:
        with get_obs_db_context(db) as session:
            now = int(time.time())
            item = ObsItem(
                id=str(uuid.uuid4()),
                kind=form.kind,
                title=form.title,
                data=form.data,
                created_by=user_id,
                created_at=now,
                updated_at=now,
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            return ObsItemModel.model_validate(item)

    def update_item(
        self, item_id: str, form: ObsItemUpdateForm, db: Optional[Session] = None
    ) -> Optional[ObsItemModel]:
        with get_obs_db_context(db) as session:
            item = session.query(ObsItem).filter(ObsItem.id == item_id).first()
            if not item:
                return None

            if form.kind is not None:
                item.kind = form.kind
            if form.title is not None:
                item.title = form.title
            if form.data is not None:
                item.data = form.data

            item.updated_at = int(time.time())
            session.add(item)
            session.commit()
            session.refresh(item)
            return ObsItemModel.model_validate(item)

    def delete_item(self, item_id: str, db: Optional[Session] = None) -> bool:
        with get_obs_db_context(db) as session:
            item = session.query(ObsItem).filter(ObsItem.id == item_id).first()
            if not item:
                return False
            session.delete(item)
            session.commit()
            return True


ObsItems = ObsItemsTable()
