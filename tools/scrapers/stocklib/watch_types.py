"""
What a variety watch is FOR (2026-10-26).

A watch attaches to one variety, and the variety is the same whether you are
after the tree or a stick of its wood: "Apple - Gala" and "Scion Wood Apple -
Gala" are both apple-gala. Benedict: "scion wood always will attach to a
variety, but it's a different type of watch to just watching that variety".
So a watch is (email, variety_slug, watch_type), and each type sees only its
own listings: a $9.75 Gala scion stick must never tell a Gala tree watcher the
tree is back, and the reverse.

One module because the server, the alert sender and the watch notice all read
and write these rows, and two of them already carried a copy of the schema.
"""
import sqlite3
import urllib.parse

TREE = "tree"
SCION = "scion"
WATCH_TYPES = (TREE, SCION)

SCION_PAGE = "/scion-wood.html"


def scion_anchor(variety_slug: str) -> str:
    """Row id on /scion-wood.html for a variety's scion listings."""
    return f"scion-{variety_slug}"


def watch_label(title: str, watch_type: str) -> str:
    """How a watch reads anywhere a person sees it: "Apple Gala (scion wood)"."""
    return f"{title} (scion wood)" if watch_type == SCION else title


def watch_page_url(site_url: str, variety_slug: str, watch_type: str) -> str:
    """Where a watch's links go. A scion variety may have no tree page at all
    ("Scion Wood Wampee - Guy Sam" with no Guy Sam tree listed), so scion
    watches always land on their row of the scion page."""
    q = urllib.parse.quote(variety_slug)
    if watch_type == SCION:
        return f"{site_url}{SCION_PAGE}#{scion_anchor(q)}"
    return f"{site_url}/variety/{q}.html"


def ensure_watch_type_schema(con: sqlite3.Connection) -> None:
    """Give `watches` and `sends` a watch_type column, every existing row a
    tree watch.

    The uniqueness rule has to move with it ("one watch per person per
    variety" becomes "per variety and type", or a tree watcher could never add
    the scion watch), and SQLite cannot alter a UNIQUE constraint in place, so
    each table is rebuilt once inside a transaction: create the new shape,
    copy every row across with watch_type 'tree', swap the names. Ids are
    copied too, so nothing that remembers a row id is broken. Idempotent: a
    table that already has the column is left alone.

    `sends` gets the same treatment because its UNIQUE(email, variety_slug,
    sent_at) would otherwise silently drop the record of a scion alert sent
    the same day as a tree alert, and that record is the 30-day cooldown.
    """
    def cols(table):
        return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}

    def exists(table):
        return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                           (table,)).fetchone() is not None

    if exists("watches") and "watch_type" not in cols("watches"):
        _atomically(con, [
            """
                CREATE TABLE watches_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    variety_slug TEXT NOT NULL,
                    species_slug TEXT NOT NULL,
                    variety_title TEXT NOT NULL,
                    added_at TEXT NOT NULL,
                    watch_type TEXT NOT NULL DEFAULT 'tree',
                    UNIQUE(email, variety_slug, watch_type)
                )""",
            """
                INSERT INTO watches_new (id, email, variety_slug, species_slug,
                                         variety_title, added_at, watch_type)
                SELECT id, email, variety_slug, species_slug, variety_title,
                       added_at, 'tree' FROM watches""",
            "DROP TABLE watches",
            "ALTER TABLE watches_new RENAME TO watches",
        ])

    if exists("sends") and "watch_type" not in cols("sends"):
        alert_type = "alert_type" if "alert_type" in cols("sends") else "'restock'"
        _atomically(con, [
            """
                CREATE TABLE sends_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    variety_slug TEXT NOT NULL,
                    sent_at TEXT NOT NULL,
                    alert_type TEXT NOT NULL DEFAULT 'restock',
                    watch_type TEXT NOT NULL DEFAULT 'tree',
                    UNIQUE(email, variety_slug, sent_at, watch_type)
                )""",
            f"""
                INSERT INTO sends_new (id, email, variety_slug, sent_at, alert_type, watch_type)
                SELECT id, email, variety_slug, sent_at, {alert_type}, 'tree' FROM sends""",
            "DROP TABLE sends",
            "ALTER TABLE sends_new RENAME TO sends",
        ])


def _atomically(con: sqlite3.Connection, statements: list[str]) -> None:
    """Run DDL + DML as one transaction. The sqlite3 module does not open a
    transaction for CREATE/DROP on its own, so without this a failure between
    DROP and RENAME would leave no watches table at all."""
    if con.in_transaction:
        con.commit()
    con.execute("BEGIN")
    try:
        for statement in statements:
            con.execute(statement)
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise
