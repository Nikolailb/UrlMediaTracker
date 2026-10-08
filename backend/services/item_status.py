"""Item lifecycle rules (REQ-022)."""
from decimal import Decimal, InvalidOperation

from models.item import ItemStatus, TrackedItem


def caught_up(current: str | None, latest: str | None) -> bool:
    if not current or not latest:
        return False
    try:
        current_number, latest_number = Decimal(current), Decimal(latest)
        return current_number.is_finite() and latest_number.is_finite() and current_number >= latest_number
    except InvalidOperation:
        return False


def set_status(item: TrackedItem, status: ItemStatus | str) -> None:
    item.status = ItemStatus(status).value
    item.is_active = item.status == ItemStatus.ONGOING.value


def reconcile_finished(item: TrackedItem) -> None:
    if item.status == ItemStatus.FINISHED.value and not caught_up(item.current_chapter, item.latest_chapter):
        set_status(item, ItemStatus.COMPLETED)
