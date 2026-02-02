#!/usr/bin/env python3
"""Cria ou atualiza um usuário no Firebase Authentication com email + senha."""

from __future__ import annotations

import argparse
import os
import sys

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials as firebase_credentials

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cria/atualiza um usuário na autenticação Firebase.",
    )
    parser.add_argument(
        "-e",
        "--email",
        required=True,
        help="Email do usuário que será criado/atualizado.",
    )
    parser.add_argument(
        "-p",
        "--password",
        required=True,
        help="Senha (mínimo 6 caracteres) para utilizar na tela de login.",
    )
    parser.add_argument(
        "-n",
        "--display-name",
        help="Nome de exibição (opcional).",
    )
    parser.add_argument(
        "-s",
        "--service-account-json",
        default=os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON"),
        help="Caminho para o JSON da service account. Padrão: $FIREBASE_SERVICE_ACCOUNT_JSON.",
    )
    parser.add_argument(
        "--project-id",
        default=os.environ.get("FIREBASE_PROJECT_ID"),
        help="ID do projeto Firebase (opcional, usa $FIREBASE_PROJECT_ID).",
    )
    return parser.parse_args()


def _ensure_password(password: str) -> None:
    if len(password) < 6:
        raise SystemExit("O Firebase exige senha com pelo menos 6 caracteres.")


def _init_firebase(service_account_path: str | None, project_id: str | None) -> firebase_admin.App:
    if firebase_admin._apps:
        return firebase_admin.get_app()

    if not service_account_path:
        raise SystemExit(
            "Não foi informado o caminho para a service account. "
            "Defina FIREBASE_SERVICE_ACCOUNT_JSON ou use --service-account-json."
        )

    service_account_path = os.path.expanduser(service_account_path)

    if not os.path.isfile(service_account_path):
        raise SystemExit(f"Service account não encontrada em {service_account_path!r}.")

    cred = firebase_credentials.Certificate(service_account_path)
    options = {}
    if project_id:
        options["projectId"] = project_id
    return firebase_admin.initialize_app(cred, options or None)


def _upsert_user(email: str, password: str, display_name: str | None) -> firebase_auth.UserRecord:
    try:
        existing = firebase_auth.get_user_by_email(email)
        updates: dict[str, str | None] = {"password": password}
        if display_name:
            updates["display_name"] = display_name
        firebase_auth.update_user(existing.uid, **updates)
        print(f"Usuário já existia, senha atualizada (UID={existing.uid}).")
        return existing
    except firebase_auth.UserNotFoundError:
        user = firebase_auth.create_user(
            email=email,
            password=password,
            display_name=display_name or None,
        )
        print(f"Usuário criado com sucesso (UID={user.uid}).")
        return user


def _try_load_dotenv() -> None:
    if load_dotenv:
        load_dotenv()  # carrega .env/.ENV padrão


def main() -> None:
    _try_load_dotenv()
    args = _parse_args()
    _ensure_password(args.password)
    _init_firebase(args.service_account_json, args.project_id)
    _upsert_user(args.email, args.password, args.display_name)


if __name__ == "__main__":
    main()
