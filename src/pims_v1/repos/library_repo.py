from sqlalchemy.orm import Session

from pims_v1.models.library import Library


def list_libraries(session: Session) -> list[Library]:
    return list(session.query(Library).order_by(Library.name).all())


def get_or_create_library(
    session: Session,
    name: str,
    kind: str,
    root_path: str,
) -> Library:
    library = session.query(Library).filter(Library.root_path == root_path).one_or_none()
    if library is None:
        library = Library(name=name, kind=kind, root_path=root_path)
        session.add(library)
        session.flush()
        return library

    library.name = name
    library.kind = kind
    session.flush()
    return library
