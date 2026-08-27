import json
import os
import threading

from datetime import datetime, timezone


# ============================================================
# ESTADOS DEL BOT
# ============================================================

STARTING = "STARTING"
CONNECTED = "CONNECTED"
READY = "READY"

PROCESSING_SIGNAL = "PROCESSING_SIGNAL"

RECONNECTING_IBKR = "RECONNECTING_IBKR"
RECONNECTING_GMAIL = "RECONNECTING_GMAIL"

PAUSED = "PAUSED"
SAFETY_LOCK = "SAFETY_LOCK"
STOPPING = "STOPPING"


# ============================================================
# ARCHIVO DE ESTADO
# ============================================================

STATUS_FILE = os.path.join(
    "data",
    "bot_status.json"
)


# ============================================================
# ARCHIVO HEARTBEAT
# ============================================================

HEARTBEAT_FILE = os.path.join(
    "data",
    "bot_heartbeat.json"
)


# ============================================================
# ESTADO GLOBAL
# ============================================================

class BotState:

    def __init__(self):

        self._lock = threading.RLock()

        self.status = STARTING

        self.started_at = None
        self.updated_at = None

        # ----------------------------------------------------
        # CONEXIONES
        # ----------------------------------------------------

        self.ibkr_connected = False
        self.gmail_connected = False

        # ----------------------------------------------------
        # SEÑAL ACTUAL
        # ----------------------------------------------------

        self.current_message_id = None

        # ----------------------------------------------------
        # ÚLTIMA SEÑAL
        # ----------------------------------------------------

        self.last_signal_status = None

        # ----------------------------------------------------
        # ÚLTIMO ERROR
        # ----------------------------------------------------

        self.last_error = None

        # ----------------------------------------------------
        # ÚLTIMA ORDEN
        # ----------------------------------------------------

        self.last_order_id = None
        self.last_execution_price = None

        # ----------------------------------------------------
        # POSICIÓN
        # ----------------------------------------------------

        self.position = 0.0

        # ----------------------------------------------------
        # HEARTBEAT
        # ----------------------------------------------------

        self.last_heartbeat = None
        self.last_cycle = None

        # ----------------------------------------------------
        # CREAR ESTADO INICIAL
        # ----------------------------------------------------

        self._save()

    # ========================================================
    # DIRECTORIO
    # ========================================================

    def _ensure_directory(
        self
    ):

        directory = os.path.dirname(
            STATUS_FILE
        )

        if directory:

            os.makedirs(
                directory,
                exist_ok=True
            )

    # ========================================================
    # DIRECTORIO HEARTBEAT
    # ========================================================

    def _ensure_heartbeat_directory(
        self
    ):

        directory = os.path.dirname(
            HEARTBEAT_FILE
        )

        if directory:

            os.makedirs(
                directory,
                exist_ok=True
            )

    # ========================================================
    # SNAPSHOT INTERNO
    # ========================================================

    def _snapshot_locked(
        self
    ):

        return {

            "status":
                self.status,

            "started_at":
                self.started_at,

            "updated_at":
                self.updated_at,

            "ibkr_connected":
                self.ibkr_connected,

            "gmail_connected":
                self.gmail_connected,

            "current_message_id":
                self.current_message_id,

            "last_signal_status":
                self.last_signal_status,

            "last_error":
                self.last_error,

            "last_order_id":
                self.last_order_id,

            "last_execution_price":
                self.last_execution_price,

            "position":
                self.position,

            "last_heartbeat":
                self.last_heartbeat,

            "last_cycle":
                self.last_cycle,
        }

    # ========================================================
    # GUARDAR ESTADO
    # ========================================================

    def _save(
        self
    ):

        with self._lock:

            data = (
                self._snapshot_locked()
            )

            try:

                self._ensure_directory()

                temporary_file = (
                    STATUS_FILE
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
                    STATUS_FILE
                )

            except Exception as error:

                # No dependemos del logger aquí para evitar
                # problemas durante el arranque del programa.

                print(
                    "ERROR guardando "
                    f"{STATUS_FILE}: "
                    f"{type(error).__name__}: "
                    f"{error}"
                )

    # ========================================================
    # HEARTBEAT
    # ========================================================

    def heartbeat(
        self
    ):
        """
        Registra un pulso del proceso principal.

        El heartbeat NO ejecuta órdenes ni modifica
        ninguna lógica de trading.

        Actualiza:
            - last_heartbeat
            - last_cycle

        y persiste el resultado en:
            data/bot_heartbeat.json
        """

        now = (
            datetime.now(
                timezone.utc
            ).isoformat()
        )

        with self._lock:

            self.last_heartbeat = now
            self.last_cycle = now

        # ----------------------------------------------------
        # Guardar también en bot_status.json para que el estado
        # principal tenga constancia del último heartbeat.
        # ----------------------------------------------------

        self._save()

        # ----------------------------------------------------
        # Guardar heartbeat independiente.
        # ----------------------------------------------------

        heartbeat_data = {

            "status":
                "RUNNING",

            "last_heartbeat":
                now,

            "last_cycle":
                now,
        }

        try:

            self._ensure_heartbeat_directory()

            temporary_file = (
                HEARTBEAT_FILE
                + ".tmp"
            )

            with open(
                temporary_file,
                "w",
                encoding="utf-8"
            ) as file:

                json.dump(
                    heartbeat_data,
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
                HEARTBEAT_FILE
            )

        except Exception as error:

            print(
                "ERROR guardando "
                f"{HEARTBEAT_FILE}: "
                f"{type(error).__name__}: "
                f"{error}"
            )

    # ========================================================
    # CAMBIAR ESTADO
    # ========================================================

    def set_status(
        self,
        status,
        error=None
    ):

        with self._lock:

            self.status = (
                status
            )

            self.updated_at = (
                datetime.now()
                .astimezone()
                .isoformat()
            )

            if error is not None:

                self.last_error = (
                    str(error)
                )

        self._save()

    # ========================================================
    # MARCAR INICIO
    # ========================================================

    def mark_started(
        self
    ):

        with self._lock:

            now = (
                datetime.now()
                .astimezone()
                .isoformat()
            )

            self.started_at = now
            self.updated_at = now

            self.status = STARTING

            self.last_error = None

            self.last_heartbeat = None
            self.last_cycle = None

        self._save()

    # ========================================================
    # IBKR
    # ========================================================

    def set_ibkr_connected(
        self,
        connected
    ):

        with self._lock:

            self.ibkr_connected = (
                bool(connected)
            )

            self.updated_at = (
                datetime.now()
                .astimezone()
                .isoformat()
            )

        self._save()

    # ========================================================
    # GMAIL
    # ========================================================

    def set_gmail_connected(
        self,
        connected
    ):

        with self._lock:

            self.gmail_connected = (
                bool(connected)
            )

            self.updated_at = (
                datetime.now()
                .astimezone()
                .isoformat()
            )

        self._save()

    # ========================================================
    # SEÑAL ACTUAL
    # ========================================================

    def set_current_signal(
        self,
        message_id
    ):

        with self._lock:

            self.current_message_id = (
                message_id
            )

            self.updated_at = (
                datetime.now()
                .astimezone()
                .isoformat()
            )

        self._save()

    def clear_current_signal(
        self
    ):

        with self._lock:

            self.current_message_id = None

            self.updated_at = (
                datetime.now()
                .astimezone()
                .isoformat()
            )

        self._save()

    # ========================================================
    # ÚLTIMA SEÑAL
    # ========================================================

    def set_last_signal_status(
        self,
        status
    ):

        with self._lock:

            self.last_signal_status = (
                status
            )

            self.updated_at = (
                datetime.now()
                .astimezone()
                .isoformat()
            )

        self._save()

    # ========================================================
    # ÚLTIMA ORDEN
    # ========================================================

    def set_last_order(
        self,
        order_id,
        price=None
    ):

        with self._lock:

            self.last_order_id = (
                order_id
            )

            self.last_execution_price = (
                price
            )

            self.updated_at = (
                datetime.now()
                .astimezone()
                .isoformat()
            )

        self._save()

    # ========================================================
    # POSICIÓN
    # ========================================================

    def set_position(
        self,
        position
    ):

        with self._lock:

            self.position = (
                float(position)
            )

            self.updated_at = (
                datetime.now()
                .astimezone()
                .isoformat()
            )

        self._save()

    # ========================================================
    # ERROR
    # ========================================================

    def set_error(
        self,
        error
    ):

        with self._lock:

            self.last_error = (
                str(error)
            )

            self.updated_at = (
                datetime.now()
                .astimezone()
                .isoformat()
            )

        self._save()

    # ========================================================
    # LIMPIAR ERROR
    # ========================================================

    def clear_error(
        self
    ):

        with self._lock:

            self.last_error = None

            self.updated_at = (
                datetime.now()
                .astimezone()
                .isoformat()
            )

        self._save()

    # ========================================================
    # SNAPSHOT PÚBLICO
    # ========================================================

    def snapshot(
        self
    ):

        with self._lock:

            return (
                self._snapshot_locked()
            )


# ============================================================
# LEER ESTADO PERSISTENTE
# ============================================================

def load_saved_status():

    try:

        with open(
            STATUS_FILE,
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
                "bot_status.json "
                "no contiene un objeto JSON."
            )

        return data

    except FileNotFoundError:

        return None

    except Exception as error:

        raise RuntimeError(
            "No se pudo leer "
            "bot_status.json: "
            f"{type(error).__name__}: "
            f"{error}"
        ) from error


# ============================================================
# LEER HEARTBEAT PERSISTENTE
# ============================================================

def load_saved_heartbeat():

    try:

        with open(
            HEARTBEAT_FILE,
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
                "bot_heartbeat.json "
                "no contiene un objeto JSON."
            )

        return data

    except FileNotFoundError:

        return None

    except Exception as error:

        raise RuntimeError(
            "No se pudo leer "
            "bot_heartbeat.json: "
            f"{type(error).__name__}: "
            f"{error}"
        ) from error


# ============================================================
# INSTANCIA GLOBAL
# ============================================================

bot_state = BotState()