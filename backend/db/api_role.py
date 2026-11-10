"""Create the API's own database account, which can read every table and write none.

The API's sessions are already read-only, but they still log in as the pipeline's
account, which can do anything: a session setting is one line of code away from
being undone. With this account, PostgreSQL refuses a write whatever the session
says.

    $env:NEWSEYE_API_DB_PASSWORD = "..."    # choose one; never store it in the repository
    python -m backend.db.api_role

Run it again to change the password. Then start the API with the same password in
the environment and NEWSEYE_API_DB_USER=newseye_api.
"""
import os

from psycopg2 import sql

from backend.db.connection import DB_CONFIG, get_cursor

ROLE = "newseye_api"
MIN_PASSWORD = 12
GRANTS = ("GRANT CONNECT ON DATABASE {database} TO {role}",
          "GRANT USAGE ON SCHEMA public TO {role}",
          "GRANT SELECT ON ALL TABLES IN SCHEMA public TO {role}",
          # tables created later by the migrations, such as a rebuilt people table
          "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO {role}")


def apply(cur, password):
    """Create or update the account, in the caller's transaction."""
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (ROLE,))
    verb = "ALTER" if cur.fetchone() else "CREATE"
    role = sql.Identifier(ROLE)
    cur.execute(sql.SQL(verb + " ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                               "PASSWORD %s").format(role), (password,))
    for grant in GRANTS:
        cur.execute(sql.SQL(grant).format(database=sql.Identifier(DB_CONFIG["dbname"]),
                                          role=role))


def main():
    password = os.environ.get("NEWSEYE_API_DB_PASSWORD", "")
    if len(password) < MIN_PASSWORD:
        raise SystemExit(f"Set NEWSEYE_API_DB_PASSWORD to at least {MIN_PASSWORD} "
                         "characters first.")
    with get_cursor() as cur:
        apply(cur, password)
    print(f"{ROLE} can now read every table and write none. Start the API with "
          f"NEWSEYE_API_DB_USER={ROLE} and the same password in the environment.")


if __name__ == "__main__":
    main()
