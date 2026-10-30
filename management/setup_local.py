#!/usr/bin/env python3
"""Provision the phase-1 local database without changing Kestra's internal database."""
import argparse
import os
from pathlib import Path
import secrets
import subprocess


def psql(database, statement):
    return subprocess.run(
        ["docker", "exec", "-i", "log-backend-local-postgres-1", "psql", "-X", "-v", "ON_ERROR_STOP=1",
         "-U", "kestra", "-d", database, "-At"], input=statement, text=True, capture_output=True, check=True).stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    args = parser.parse_args()
    args.env_file.parent.mkdir(parents=True, exist_ok=True)
    if not args.env_file.exists():
        values = {"ANALYTICS_READER_PASSWORD": secrets.token_hex(32),
                  "ANALYTICS_IMPORTER_PASSWORD": secrets.token_hex(32),
                  "ANALYTICS_ARCHIVE_DIR": str(args.archive.resolve()),
                  "ANALYTICS_SNAPSHOT_DIR": str(args.snapshot.resolve()),
                  "ANALYTICS_LOCAL_UID": str(os.getuid()), "ANALYTICS_LOCAL_GID": str(os.getgid())}
        if any("\n" in value or "'" in value for value in values.values()):
            raise ValueError("Unsupported environment path")
        with open(args.env_file, "x", opener=lambda p, flags: os.open(p, flags, 0o600)) as file:
            file.write("".join(f"{key}='{value}'\n" for key, value in values.items()))
    args.env_file.chmod(0o600)
    values = dict(line.strip().split("=", 1) for line in args.env_file.read_text().splitlines() if line.strip())
    values = {key: value.strip("'") for key, value in values.items()}
    for role, key in [("analytics_reader", "ANALYTICS_READER_PASSWORD"), ("analytics_importer", "ANALYTICS_IMPORTER_PASSWORD")]:
        password = values[key]
        if len(password) != 64 or any(c not in "0123456789abcdef" for c in password):
            raise ValueError("Invalid generated database credential")
        if psql("postgres", f"SELECT 1 FROM pg_roles WHERE rolname='{role}';") != "1":
            psql("postgres", f"CREATE ROLE {role} LOGIN PASSWORD '{password}';")
    if psql("postgres", "SELECT 1 FROM pg_roles WHERE rolname='analytics_owner';") != "1":
        psql("postgres", "CREATE ROLE analytics_owner NOLOGIN;")
    if psql("postgres", "SELECT 1 FROM pg_database WHERE datname='analytics_management';") != "1":
        psql("postgres", "CREATE DATABASE analytics_management OWNER analytics_owner;")
    psql("analytics_management", "REVOKE ALL ON DATABASE analytics_management FROM PUBLIC;\n"
         "GRANT CONNECT ON DATABASE analytics_management TO analytics_reader, analytics_importer;\n"
         "ALTER ROLE analytics_reader SET default_transaction_read_only=on;\n"
         "SET ROLE analytics_owner;\n" + Path(__file__).with_name("schema.sql").read_text())
    print("Independent database/schema ready; environment file permissions: 0600. No cached records imported yet.")


if __name__ == "__main__":
    main()
