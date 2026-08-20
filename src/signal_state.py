import json
import os
import threading
from datetime import datetime, timezone


# ============================================================
# CONFIGURACIÓN
# ============================================================

DATA_DIR = "data"

STATE_FILE = os.path.join(
    DATA_DIR,
    "processed_signals.json"
)


# ============================================================
# ESTADOS
# ============================================================

NEW = "NEW"
PROCESSING = "PROCESSING"
SUCCESS = "SUCCESS"
FAILED = "FAILED"
PARTIAL = "PARTIAL"
REJECTED = "REJECTED"


# ============================================================
# ERROR CRÍTICO
# ============================================================

class SignalStateError(Exception):
    """
    Error crítico del almacenamiento de estados.

    Ante este error el bot NO debe operar.
    """
    pass


# ============================================================
# UTILIDAD FECHA
# ============================================================

def now_iso():

    return (
        datetime.now(
            timezone.utc
        ).isoformat()
    )


# ============================================================
# SIGNAL STATE
# ============================================================

class SignalState:

    def __init__(self):

        self._lock = (
            threading.Lock()
        )

        self._ensure_storage()

    # ========================================================
    # ASEGURAR ALMACENAMIENTO
    # ========================================================

    def _ensure_storage(self):

        os.makedirs(
            DATA_DIR,
            exist_ok=True
        )

        if not os.path.exists(
            STATE_FILE
        ):

            self._save_states({})

            return

        self._validate_storage()

    # ========================================================
    # VALIDAR JSON
    # ========================================================

    def _validate_storage(self):

        try:

            with open(
                STATE_FILE,
                "r",
                encoding="utf-8"
            ) as file:

                data = json.load(
                    file
                )

        except FileNotFoundError:

            self._save_states({})

            return

        except json.JSONDecodeError as error:

            raise SignalStateError(
                "CRÍTICO: "
                "processed_signals.json está corrupto: "
                f"{error}"
            ) from error

        except OSError as error:

            raise SignalStateError(
                "CRÍTICO: no se puede leer "
                "processed_signals.json: "
                f"{error}"
            ) from error

        if not isinstance(
            data,
            dict
        ):

            raise SignalStateError(
                "CRÍTICO: "
                "processed_signals.json tiene "
                "un formato inválido."
            )

    # ========================================================
    # CARGAR
    # ========================================================

    def _load_states(self):

        try:

            with open(
                STATE_FILE,
                "r",
                encoding="utf-8"
            ) as file:

                data = json.load(
                    file
                )

        except FileNotFoundError as error:

            raise SignalStateError(
                "CRÍTICO: "
                "processed_signals.json ha desaparecido."
            ) from error

        except json.JSONDecodeError as error:

            raise SignalStateError(
                "CRÍTICO: "
                "processed_signals.json está corrupto: "
                f"{error}"
            ) from error

        except OSError as error:

            raise SignalStateError(
                "CRÍTICO: "
                "no se puede leer "
                "processed_signals.json: "
                f"{error}"
            ) from error

        if not isinstance(
            data,
            dict
        ):

            raise SignalStateError(
                "CRÍTICO: "
                "formato inválido en "
                "processed_signals.json."
            )

        return data

    # ========================================================
    # GUARDAR
    # ========================================================

    def _save_states(
        self,
        states
    ):

        if not isinstance(
            states,
            dict
        ):

            raise SignalStateError(
                "El estado debe ser un diccionario."
            )

        temp_file = (
            STATE_FILE + ".tmp"
        )

        try:

            with open(
                temp_file,
                "w",
                encoding="utf-8"
            ) as file:

                json.dump(
                    states,
                    file,
                    indent=4,
                    ensure_ascii=False
                )

                file.flush()

                os.fsync(
                    file.fileno()
                )

            os.replace(
                temp_file,
                STATE_FILE
            )

        except OSError as error:

            try:

                if os.path.exists(
                    temp_file
                ):

                    os.remove(
                        temp_file
                    )

            except OSError:

                pass

            raise SignalStateError(
                "CRÍTICO: "
                "no se pudo guardar "
                "processed_signals.json: "
                f"{error}"
            ) from error

    # ========================================================
    # OBTENER ESTADO
    # ========================================================

    def get_status(
        self,
        message_id
    ):

        with self._lock:

            states = (
                self._load_states()
            )

            entry = states.get(
                message_id
            )

            if not entry:

                return None

            return entry.get(
                "status"
            )

    # ========================================================
    # OBTENER REGISTRO
    # ========================================================

    def get(
        self,
        message_id
    ):

        with self._lock:

            states = (
                self._load_states()
            )

            return states.get(
                message_id
            )

    # ========================================================
    # GUARDAR ESTADO
    # ========================================================

    def set_status(
        self,
        message_id,
        status,
        **data
    ):

        if not message_id:

            raise SignalStateError(
                "No se puede guardar "
                "una señal sin Message-ID."
            )

        allowed_statuses = (
            NEW,
            PROCESSING,
            SUCCESS,
            FAILED,
            PARTIAL,
            REJECTED
        )

        if status not in (
            allowed_statuses
        ):

            raise SignalStateError(
                f"Estado no válido: {status}"
            )

        with self._lock:

            states = (
                self._load_states()
            )

            existing = states.get(
                message_id,
                {}
            )

            entry = {
                **existing,
                **data,
                "status": status,
                "updated_at": now_iso()
            }

            states[
                message_id
            ] = entry

            self._save_states(
                states
            )

    # ========================================================
    # PREPARAR OPERACIÓN
    # ========================================================

    def set_processing_order(
        self,
        message_id,
        operation_index,
        signal_action,
        ib_action,
        order_id,
        position_before,
        expected_position
    ):
        """
        Guarda el Order ID ANTES de enviar la orden.

        Esto es fundamental para poder reconciliar una señal
        si Python se cae justo después de placeOrder().
        """

        with self._lock:

            states = (
                self._load_states()
            )

            entry = states.get(
                message_id
            )

            if not entry:

                raise SignalStateError(
                    "No existe la señal "
                    f"{message_id}."
                )

            if entry.get(
                "status"
            ) != PROCESSING:

                raise SignalStateError(
                    "Solo se puede registrar una "
                    "orden mientras la señal está "
                    "en PROCESSING."
                )

            operations = entry.get(
                "operations",
                []
            )

            while len(
                operations
            ) <= operation_index:

                operations.append({})

            operations[
                operation_index
            ] = {
                "operation_index":
                    operation_index,

                "signal_action":
                    signal_action,

                "action":
                    ib_action,

                "order_id":
                    order_id,

                "position_before":
                    position_before,

                "expected_position":
                    expected_position,

                "status":
                    "PENDING",

                "planned_at":
                    now_iso()
            }

            entry[
                "operations"
            ] = operations

            entry[
                "updated_at"
            ] = now_iso()

            states[
                message_id
            ] = entry

            self._save_states(
                states
            )

    # ========================================================
    # GUARDAR RESULTADO DE OPERACIÓN
    # ========================================================

    def set_operation_result(
        self,
        message_id,
        operation_index,
        result
    ):
        """
        Guarda el resultado real de una operación individual.
        """

        with self._lock:

            states = (
                self._load_states()
            )

            entry = states.get(
                message_id
            )

            if not entry:

                raise SignalStateError(
                    "No existe la señal "
                    f"{message_id}."
                )

            operations = entry.get(
                "operations",
                []
            )

            while len(
                operations
            ) <= operation_index:

                operations.append({})

            existing_operation = (
                operations[
                    operation_index
                ]
            )

            operations[
                operation_index
            ] = {
                **existing_operation,
                "status": result.get(
                    "status",
                    "UNKNOWN"
                ),
                "result": result,
                "updated_at": now_iso()
            }

            entry[
                "operations"
            ] = operations

            entry[
                "updated_at"
            ] = now_iso()

            states[
                message_id
            ] = entry

            self._save_states(
                states
            )

    # ========================================================
    # SEÑALES EN PROCESSING
    # ========================================================

    def get_processing_signals(self):

        with self._lock:

            states = (
                self._load_states()
            )

            return {
                message_id: data
                for (
                    message_id,
                    data
                ) in states.items()
                if data.get(
                    "status"
                ) == PROCESSING
            }

    # ========================================================
    # COMPROBAR PROCESADA
    # ========================================================

    def is_processed(
        self,
        message_id
    ):

        status = (
            self.get_status(
                message_id
            )
        )

        return status in (
            SUCCESS,
            FAILED,
            PARTIAL,
            REJECTED
        )

    # ========================================================
    # COMPROBAR PROCESSING
    # ========================================================

    def is_processing(
        self,
        message_id
    ):

        return (
            self.get_status(
                message_id
            )
            == PROCESSING
        )

    # ========================================================
    # TODOS LOS ESTADOS
    # ========================================================

    def all_states(self):

        with self._lock:

            return (
                self._load_states()
            )

    # ========================================================
    # BORRAR
    # ========================================================

    def delete(
        self,
        message_id
    ):

        with self._lock:

            states = (
                self._load_states()
            )

            if message_id not in states:

                return

            del states[
                message_id
            ]

            self._save_states(
                states
            )


# ============================================================
# TEST
# ============================================================

def main():

    print(
        "========================================"
    )

    print(
        "       SIGNAL STATE - TEST"
    )

    print(
        "========================================"
    )

    state = SignalState()

    test_id = (
        "TEST-MESSAGE-ID"
    )

    state.set_status(
        test_id,
        PROCESSING,
        email_uid="TEST-001",
        subject="TEST",
        actions=[
            "ABRIR_LARGO"
        ],
        position_initial=0.0,
        expected_final_position=1.0
    )

    state.set_processing_order(
        test_id,
        operation_index=0,
        signal_action="ABRIR_LARGO",
        ib_action="BUY",
        order_id=999,
        position_before=0.0,
        expected_position=1.0
    )

    print()
    print(
        state.get(
            test_id
        )
    )

    state.set_operation_result(
        test_id,
        0,
        {
            "success": True,
            "status": "Filled",
            "filled": 1.0,
            "price": 26480.0,
            "position": 1.0,
            "order_id": 999
        }
    )

    print()
    print(
        "Tras resultado:"
    )

    print(
        state.get(
            test_id
        )
    )

    state.delete(
        test_id
    )

    print()
    print(
        "Prueba eliminada."
    )


# ============================================================
# INICIO
# ============================================================

if __name__ == "__main__":

    main()