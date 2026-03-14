"""sql.js-powered HTML-app export for btk."""
from pathlib import Path
from typing import Dict, List, Optional

from btk.models import Bookmark


def export_html_app(
    bookmarks: List[Bookmark],
    path: Path,
    views: Optional[dict] = None,
    embed: bool = True,
    include_dbs: Optional[Dict[str, List[Bookmark]]] = None,
) -> None:
    from btk.html_app.builder import build_export_db
    from btk.html_app.template import assemble_embedded, assemble_directory

    db_bytes = build_export_db(bookmarks, include_dbs=include_dbs)

    if embed:
        html = assemble_embedded(db_bytes, views=views)
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
    else:
        assemble_directory(db_bytes, Path(path), views=views)
