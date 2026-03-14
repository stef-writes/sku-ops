"""Create or update an admin user in the local users table.

This provisions the local profile row so /api/auth/me returns full user data.
In production with Supabase, the user must ALSO exist in Supabase Auth.

IMPORTANT: Pass --id with the Supabase user UUID (from auth.users.id) so the
local row matches the JWT 'sub' claim. Without this, /api/auth/me falls back
to JWT claims (missing company, phone, billing_entity fields).

Find the Supabase user UUID:
    SELECT id FROM auth.users WHERE email = 'admin@example.com';

Supabase side — run this in the Supabase SQL Editor to set the admin role:

    UPDATE auth.users
    SET raw_app_meta_data = jsonb_set(
      COALESCE(raw_app_meta_data, '{}'::jsonb),
      '{role}', '"admin"'
    )
    WHERE email = 'admin@example.com';

Usage:
    PYTHONPATH=backend:. uv run python backend/scripts/create_admin.py \\
        --id <supabase-user-uuid> --email admin@company.com --name "Admin User"

    # Or via bin/dev:
    ./bin/dev create-admin --id <supabase-user-uuid> --email admin@company.com --name "Admin User"
"""

import argparse
import asyncio
import uuid
from datetime import UTC, datetime


async def main(
    user_id_arg: str, email: str, name: str, role: str, org_id: str, password: str = ""
) -> None:
    from shared.infrastructure.db import close_db, get_connection, init_db
    from shared.kernel.constants import DEFAULT_ORG_ID

    resolved_org = org_id or DEFAULT_ORG_ID
    await init_db()

    try:
        conn = get_connection()

        cursor = await conn.execute("SELECT id, role FROM users WHERE email = ?", (email,))
        existing = await cursor.fetchone()

        if existing:
            updates = ["name = ?", "role = ?"]
            params: list = [name, role]
            if user_id_arg and existing["id"] != user_id_arg:
                updates.append("id = ?")
                params.append(user_id_arg)
            params.append(email)
            await conn.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE email = ?",
                tuple(params),
            )
            await conn.commit()
            print(f"Updated existing user {existing['id']}")
            if user_id_arg and existing["id"] != user_id_arg:
                print(f"  id:    {existing['id']} -> {user_id_arg}")
            print(f"  email: {email}")
            print(f"  role:  {existing['role']} -> {role}")
            print(f"  name:  {name}")
        else:
            user_id = user_id_arg or str(uuid.uuid4())
            if not user_id_arg:
                print("WARNING: No --id provided. Generating random UUID.")
                print("         For Supabase auth, pass --id with the Supabase user UUID")
                print("         so /api/auth/me can find this profile row.")
                print()
            now = datetime.now(UTC).isoformat()
            if password:
                import bcrypt

                hashed_pw = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode(
                    "utf-8"
                )
            else:
                hashed_pw = "!supabase-managed"
            await conn.execute(
                "INSERT INTO users "
                "(id, email, password, name, role, company, billing_entity, phone, "
                "is_active, organization_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
                (user_id, email, hashed_pw, name, role, "", "", "", resolved_org, now),
            )
            await conn.commit()
            print(f"Created user {user_id}")
            print(f"  email: {email}")
            print(f"  role:  {role}")
            print(f"  name:  {name}")
            print(f"  org:   {resolved_org}")

        if not password:
            print()
            print("If using Supabase auth, also run in the Supabase SQL Editor:")
            print("  UPDATE auth.users")
            print("  SET raw_app_meta_data = jsonb_set(")
            print("    COALESCE(raw_app_meta_data, '{}'::jsonb),")
            print("    '{role}', '\"admin\"'")
            print("  )")
            print(f"  WHERE email = '{email}';")
    finally:
        await close_db()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create or update an admin user")
    parser.add_argument(
        "--id",
        default="",
        help="Supabase user UUID (from auth.users.id). Strongly recommended for production.",
    )
    parser.add_argument("--email", required=True, help="User email address")
    parser.add_argument("--name", required=True, help="Display name")
    parser.add_argument("--role", default="admin", help="User role (default: admin)")
    parser.add_argument("--org-id", default="", help="Organization ID (default: DEFAULT_ORG_ID)")
    parser.add_argument("--password", default="", help="Password for local auth (bcrypt hashed)")
    args = parser.parse_args()

    asyncio.run(main(args.id, args.email, args.name, args.role, args.org_id, args.password))
