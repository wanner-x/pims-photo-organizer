from sqlalchemy.orm import Session

from pims_v1.models.library import Library


def list_libraries(session: Session) -> list[Library]:
    return list(session.query(Library).order_by(Library.name).all())
