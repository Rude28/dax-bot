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
CANCELLED = "CANCELLED"


# ============================================================
# COMANDOS MANUALES
# ============================================================

MANUAL_COMMANDS = {
    "OPEN LONG",
    "CLOSE LONG",
    "OPEN SHORT",
    "CLOSE SHORT",
}


# ============================================================
# GESTOR DE COMANDOS PENDIENTES
# ============================================================

class PendingCommandManager:

    def __init__(
        self,
        ttl_seconds=CONFIRMATION_TTL
    ):

        self.ttl_seconds = int(
            ttl_seconds
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

    def _ensure_directory(
        self
    ):

        directory = os.path.dirname(
            PENDING_FILE
        )

        if directory:

            os.makedirs(
                directory,
                exist_ok=True
            )

    # ========================================================
    # LEER ARCHIVO
    # ========================================================

    def _load_all(
        self
    ):

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
    # GUARDAR ARCHIVO
    # ========================================================

    def _save_all(
        self,
        data
    ):

        self._ensure_directory()

        temporary_file = (
            PENDING_FILE
            + ".tmp"
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

                    command[
                        "expired_at"
                    ] = now

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
            "No se pudo generar un "
            "código de confirmación único."
        )

    # ========================================================
    # VALIDAR COMANDO
    # ========================================================

    @staticmethod
    def is_manual_command(
        command
    ):

        if not command:

            return False

        return (
            command.strip().upper()
            in MANUAL_COMMANDS
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
        """
        Crea una solicitud manual pendiente.

        NO ejecuta ninguna orden.
        """

        command = (
            str(command)
            .strip()
            .upper()
        )

        # ----------------------------------------------------
        # Validación
        # ----------------------------------------------------

        if not self.is_manual_command(
            command
        ):

            raise ValueError(
                f"Comando manual no válido: "
                f"{command}"
            )

        if int(quantity) != 1:

            raise ValueError(
                "El MVP solo permite "
                "1 contrato."
            )

        self.cleanup_expired()

        now = time.time()

        with self._lock:

            data = self._load_all()

            # ------------------------------------------------
            # Evitar múltiples confirmaciones simultáneas
            # de la misma operación.
            # ------------------------------------------------

            for existing_code, existing in (
                data.items()
            ):

                if existing.get(
                    "status"
                ) != PENDING:

                    continue

                if (
                    existing.get(
                        "command"
                    ) == command
                    and existing.get(
                        "sender"
                    ) == sender
                ):

                    raise RuntimeError(
                        "Ya existe una solicitud "
                        "pendiente para esta operación."
                    )

            # ------------------------------------------------
            # Generar código
            # ------------------------------------------------

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
                    str(email_uid),

                "message_id":
                    message_id,

                "sender":
                    sender,

                "subject":
                    subject,

                "quantity":
                    int(quantity),

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

                "expired_at":
                    None,

                "cancelled_at":
                    None,

                "cancel_reason":
                    None,

                "metadata":
                    metadata
                    if metadata
                    else {}
            }

            data[
                code
            ] = pending

            self._save_all(
                data
            )

            return dict(
                pending
            )

    # ========================================================
    # OBTENER SOLICITUD
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
    # CONSUMIR CÓDIGO
    # ========================================================

    def mark_used(
        self,
        code
    ):
        """
        Marca el código como USED.

        Debe llamarse justo antes de ejecutar
        la operación para impedir reutilización.
        """

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

            # ------------------------------------------------
            # Solo PENDING puede pasar a USED.
            # ------------------------------------------------

            if command.get(
                "status"
            ) != PENDING:

                return dict(
                    command
                )

            # ------------------------------------------------
            # Comprobar caducidad nuevamente.
            # ------------------------------------------------

            if time.time() >= float(
                command.get(
                    "expires_at",
                    0
                )
            ):

                command[
                    "status"
                ] = EXPIRED

                command[
                    "expired_at"
                ] = time.time()

                self._save_all(
                    data
                )

                return dict(
                    command
                )

            # ------------------------------------------------
            # Consumir.
            # ------------------------------------------------

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

            if command.get(
                "status"
            ) != PENDING:

                return dict(
                    command
                )

            command[
                "status"
            ] = CANCELLED

            command[
                "cancelled_at"
            ] = time.time()

            command[
                "cancel_reason"
            ] = str(
                reason
            )

            self._save_all(
                data
            )

            return dict(
                command
            )

    # ========================================================
    # TODOS LOS COMANDOS
    # ========================================================

    def all(
        self
    ):

        self.cleanup_expired()

        with self._lock:

            return self._load_all()

    # ========================================================
    # SOLICITUDES PENDIENTES
    # ========================================================

    def get_pending(
        self
    ):

        self.cleanup_expired()

        with self._lock:

            data = self._load_all()

            return {
                code: dict(command)

                for code, command
                in data.items()

                if command.get(
                    "status"
                ) == PENDING
            }

    # ========================================================
    # COMPROBAR EXISTENCIA
    # ========================================================

    def has_pending_for_sender(
        self,
        sender
    ):

        sender = (
            str(sender)
            .strip()
            .lower()
        )

        self.cleanup_expired()

        with self._lock:

            data = self._load_all()

            for command in data.values():

                if command.get(
                    "status"
                ) != PENDING:

                    continue

                existing_sender = (
                    str(
                        command.get(
                            "sender",
                            ""
                        )
                    )
                    .strip()
                    .lower()
                )

                if (
                    existing_sender
                    == sender
                ):

                    return True

            return False


# ============================================================
# INSTANCIA GLOBAL
# ============================================================

pending_commands = (
    PendingCommandManager()
)