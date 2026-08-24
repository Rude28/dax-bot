import json
import os
import secrets
import threading
import time


# ============================================================
# CONFIGURACIÓN
# ============================================================

PENDING_FILE = os.path.join(
    "data",
    "pending_commands.json"
)

CONFIRMATION_TTL = 60


# ============================================================
# ESTADOS
# ============================================================

PENDING = "PENDING"
USED = "USED"
EXPIRED = "EXPIRED"


# ============================================================
# GESTOR DE CONFIRMACIONES
# ============================================================

class PendingCommandManager:

    def __init__(
        self,
        ttl_seconds=CONFIRMATION_TTL
    ):

        self.ttl_seconds = (
            int(ttl_seconds)
        )

        self._lock = (
            threading.RLock()
        )

        self._ensure_directory()

        if not os.path.exists(
            PENDING_FILE
        ):

            self._save_all({})

    # ========================================================
    # DIRECTORIO
    # ========================================================

    def _ensure_directory(self):

        directory = os.path.dirname(
            PENDING_FILE
        )

        if directory:

            os.makedirs(
                directory,
                exist_ok=True
            )

    # ========================================================
    # LEER
    # ========================================================

    def _load_all(self):

        try:

            with open(
                PENDING_FILE,
                "r",
                encoding="utf-8"
            ) as file:

                data = json.load(
                    file
                )

            if not isinstance(
                data,
                dict
            ):

                raise ValueError(
                    "pending_commands.json "
                    "no contiene un objeto JSON."
                )

            return data

        except FileNotFoundError:

            return {}

    # ========================================================
    # GUARDAR
    # ========================================================

    def _save_all(
        self,
        data
    ):

        self._ensure_directory()

        temporary_file = (
            PENDING_FILE + ".tmp"
        )

        with open(
            temporary_file,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=4
            )

            file.flush()

            os.fsync(
                file.fileno()
            )

        os.replace(
            temporary_file,
            PENDING_FILE
        )

    # ========================================================
    # LIMPIAR EXPIRADOS
    # ========================================================

    def cleanup_expired(
        self
    ):

        now = time.time()

        with self._lock:

            data = self._load_all()

            changed = False

            for code, command in data.items():

                if command.get(
                    "status"
                ) != PENDING:

                    continue

                expires_at = float(
                    command.get(
                        "expires_at",
                        0
                    )
                )

                if now >= expires_at:

                    command[
                        "status"
                    ] = EXPIRED

                    changed = True

            if changed:

                self._save_all(
                    data
                )

    # ========================================================
    # GENERAR CÓDIGO
    # ========================================================

    def _generate_code(
        self,
        data
    ):

        for _ in range(100):

            code = str(
                secrets.randbelow(
                    900000
                ) + 100000
            )

            if code not in data:

                return code

        raise RuntimeError(
            "No se pudo generar un código "
            "de confirmación único."
        )

    # ========================================================
    # CREAR SOLICITUD
    # ========================================================

    def create(
        self,
        command,
        email_uid,
        message_id,
        sender,
        subject,
        position_at_request,
        expected_position,
        quantity=1,
        metadata=None
    ):

        self.cleanup_expired()

        now = time.time()

        with self._lock:

            data = self._load_all()

            code = self._generate_code(
                data
            )

            pending = {

                "code":
                    code,

                "status":
                    PENDING,

                "command":
                    command,

                "email_uid":
                    email_uid,

                "message_id":
                    message_id,

                "sender":
                    sender,

                "subject":
                    subject,

                "quantity":
                    quantity,

                "position_at_request":
                    float(
                        position_at_request
                    ),

                "expected_position":
                    float(
                        expected_position
                    ),

                "created_at":
                    now,

                "expires_at":
                    now
                    + self.ttl_seconds,

                "used_at":
                    None,

                "metadata":
                    metadata
                    if metadata
                    else {}
            }

            data[code] = pending

            self._save_all(
                data
            )

            return dict(
                pending
            )

    # ========================================================
    # BUSCAR
    # ========================================================

    def get(
        self,
        code
    ):

        self.cleanup_expired()

        code = str(
            code
        ).strip()

        with self._lock:

            data = self._load_all()

            command = data.get(
                code
            )

            if command is None:

                return None

            return dict(
                command
            )

    # ========================================================
    # CONFIRMAR
    # ========================================================

    def mark_used(
        self,
        code
    ):

        code = str(
            code
        ).strip()

        with self._lock:

            data = self._load_all()

            command = data.get(
                code
            )

            if command is None:

                return None

            if command.get(
                "status"
            ) != PENDING:

                return dict(
                    command
                )

            command[
                "status"
            ] = USED

            command[
                "used_at"
            ] = time.time()

            self._save_all(
                data
            )

            return dict(
                command
            )

    # ========================================================
    # CANCELAR
    # ========================================================

    def cancel(
        self,
        code,
        reason
    ):

        code = str(
            code
        ).strip()

        with self._lock:

            data = self._load_all()

            command = data.get(
                code
            )

            if command is None:

                return None

            command[
                "status"
            ] = EXPIRED

            command[
                "cancel_reason"
            ] = reason

            self._save_all(
                data
            )

            return dict(
                command
            )

    # ========================================================
    # SNAPSHOT
    # ========================================================

    def all(
        self
    ):

        self.cleanup_expired()

        with self._lock:

            return self._load_all()


# ============================================================
# INSTANCIA GLOBAL
# ============================================================

pending_commands = (
    PendingCommandManager()
)