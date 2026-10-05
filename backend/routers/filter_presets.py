"""Per-library saved filters (REQ-009)."""
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError

from models.filter_preset import FilterPreset
from models.item import ItemCategory
from services.auth import DbDep, IdentityDep, MutationDep

router = APIRouter(prefix="/filter-presets", tags=["filter-presets"])

VISUAL = ["Manhwa", "Manhua", "Manga", "Webtoon", "Pornhwa", "Comic", "Anime"]
BUILTINS = [
    {"id": "images", "name": "Images", "categories": VISUAL, "unread_only": False, "include_inactive": True, "builtin": True},
    {"id": "words", "name": "Words", "categories": ["Novel", "Light Novel"], "unread_only": False, "include_inactive": True, "builtin": True},
    {"id": "unread", "name": "Unread", "categories": [], "unread_only": True, "include_inactive": True, "builtin": True},
]
BUILTIN_NAMES = {preset["name"].casefold() for preset in BUILTINS}


class PresetInput(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    categories: list[ItemCategory] = Field(default_factory=list, max_length=len(ItemCategory))
    unread_only: bool = False
    include_inactive: bool = True

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Enter a preset name.")
        return value

    @field_validator("categories")
    @classmethod
    def unique_categories(cls, value: list[ItemCategory]) -> list[ItemCategory]:
        if len(set(value)) != len(value):
            raise ValueError("A category can appear only once.")
        return value


def _read(row: FilterPreset) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "categories": json.loads(row.categories_json),
        "unread_only": row.unread_only,
        "include_inactive": row.include_inactive,
        "builtin": False,
    }


def _owned(db: DbDep, identity: IdentityDep, preset_id: str) -> FilterPreset:
    row = db.query(FilterPreset).filter(
        FilterPreset.id == preset_id, FilterPreset.user_id == identity.library_user_id
    ).first()
    if not row:
        raise HTTPException(404, "Preset not found.")
    return row


def _apply(row: FilterPreset, data: PresetInput) -> None:
    row.name = data.name
    row.name_key = data.name.casefold()
    row.categories_json = json.dumps([category.value for category in data.categories])
    row.unread_only = data.unread_only
    row.include_inactive = data.include_inactive


def _save(db: DbDep, row: FilterPreset) -> dict:
    try:
        db.add(row)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "A preset with that name already exists.") from None
    db.refresh(row)
    return _read(row)


@router.get("")
def list_presets(db: DbDep, identity: IdentityDep):
    rows = db.query(FilterPreset).filter(FilterPreset.user_id == identity.library_user_id).order_by(FilterPreset.name_key).all()
    return BUILTINS + [_read(row) for row in rows]


@router.post("", status_code=201)
def create_preset(data: PresetInput, db: DbDep, identity: MutationDep):
    if data.name.casefold() in BUILTIN_NAMES:
        raise HTTPException(409, "That name belongs to a built-in preset.")
    if db.query(FilterPreset).filter(FilterPreset.user_id == identity.library_user_id).count() >= 50:
        raise HTTPException(400, "Preset limit reached.")
    row = FilterPreset(user_id=identity.library_user_id)
    _apply(row, data)
    return _save(db, row)


@router.put("/{preset_id}")
def update_preset(preset_id: str, data: PresetInput, db: DbDep, identity: MutationDep):
    row = _owned(db, identity, preset_id)
    if data.name.casefold() in BUILTIN_NAMES:
        raise HTTPException(409, "That name belongs to a built-in preset.")
    _apply(row, data)
    return _save(db, row)


@router.delete("/{preset_id}", status_code=204)
def delete_preset(preset_id: str, db: DbDep, identity: MutationDep):
    row = _owned(db, identity, preset_id)
    db.delete(row)
    db.commit()
