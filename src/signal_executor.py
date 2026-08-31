from signal_state import (
    SignalState,
)

from logger import (
    log_info,
    log_warning,
    log_error,
)


# ============================================================
# ACCIONES
# ============================================================

OPEN_LONG = "ABRIR_LARGO"
CLOSE_LONG = "CERRAR_LARGO"
OPEN_SHORT = "ABRIR_CORTO"
CLOSE_SHORT = "CERRAR_CORTO"


# ============================================================
# EJECUTOR
# ============================================================

class SignalExecutor:
    """
    Motor de señales compartido por PAPER y LIVE.

    La diferencia entre entornos está en ib_app:
        PaperExecutor
        LiveExecutor

    El motor mantiene la misma lógica de estado, PROCESSING,
    operaciones secuenciales y validación de posición.
    """

    def __init__(
        self,
        ib_app,
        state_manager: SignalState
    ):

        self.ib_app = ib_app
        self.state_manager = (
            state_manager
        )

    # ========================================================
    # CANTIDAD DE CONTRATOS
    # ========================================================

    def _get_order_quantity(self):

        quantity = getattr(
            self.ib_app,
            "order_quantity",
            1
        )

        try:
            quantity = int(quantity)
        except (
            TypeError,
            ValueError
        ):
            quantity = 1

        if quantity < 1:
            raise ValueError(
                "La cantidad de contratos debe ser >= 1."
            )

        return quantity

    # ========================================================
    # CAPACIDAD DEL EXECUTOR
    # ========================================================

    def _executor_ready(self):

        if self.ib_app is None:
            return False

        if hasattr(
            self.ib_app,
            "is_trading_connection_ready"
        ):
            try:
                return bool(
                    self.ib_app.is_trading_connection_ready()
                )
            except Exception:
                return False

        return True

    # ========================================================
    # EJECUTAR
    # ========================================================

    def execute(
        self,
        signal
    ):

        if not isinstance(
            signal,
            dict
        ):

            return self._error_result(
                signal,
                "La señal no es un diccionario."
            )

        actions = signal.get(
            "actions",
            []
        )

        if not actions:

            return self._error_result(
                signal,
                "La señal no contiene acciones."
            )

        print()
        print(
            "========================================"
        )

        print(
            "         EJECUTANDO SEÑAL"
        )

        print(
            "========================================"
        )

        print(
            f"Message-ID: "
            f"{signal.get('message_id')}"
        )

        print(
            f"UID: "
            f"{signal.get('email_uid')}"
        )

        print(
            f"Acciones: {actions}"
        )

        print(
            "========================================"
        )

        # ----------------------------------------------------
        # Verificar que el executor está preparado.
        # ----------------------------------------------------

        if not self._executor_ready():

            return self._error_result(
                signal,
                "El executor IBKR no está preparado."
            )

        # ----------------------------------------------------
        # Calcular posición inicial y final esperada.
        # ----------------------------------------------------

        initial_position = (
            self.ib_app.get_position()
        )

        expected_final_position = (
            self._calculate_final_position(
                initial_position,
                actions
            )
        )

        # ----------------------------------------------------
        # Guardar metadatos de PROCESSING.
        # ----------------------------------------------------

        self.state_manager.set_status(
            signal[
                "message_id"
            ],
            "PROCESSING",

            email_uid=signal[
                "email_uid"
            ],

            sender=signal[
                "sender"
            ],

            subject=signal[
                "subject"
            ],

            date=signal[
                "date"
            ],

            actions=actions,

            valid=True,

            position_initial=(
                initial_position
            ),

            expected_final_position=(
                expected_final_position
            ),

            operations=[]
        )

        # ----------------------------------------------------
        # UNA ACCIÓN
        # ----------------------------------------------------

        if len(actions) == 1:

            return self._execute_single_action(
                signal,
                actions[0],
                operation_index=0
            )

        # ----------------------------------------------------
        # LARGO → CORTO
        # ----------------------------------------------------

        if actions == [
            CLOSE_LONG,
            OPEN_SHORT
        ]:

            return self._switch_long_to_short(
                signal
            )

        # ----------------------------------------------------
        # CORTO → LARGO
        # ----------------------------------------------------

        if actions == [
            CLOSE_SHORT,
            OPEN_LONG
        ]:

            return self._switch_short_to_long(
                signal
            )

        return self._error_result(
            signal,
            (
                "Combinación de acciones "
                f"no soportada: {actions}"
            )
        )

    # ========================================================
    # POSICIÓN FINAL ESPERADA
    # ========================================================

    def _calculate_final_position(
        self,
        initial_position,
        actions
    ):
        """Calcula la posición final usando la cantidad del executor."""

        position = float(
            initial_position
        )

        quantity = self._get_order_quantity()

        for action in actions:

            if action == OPEN_LONG:
                position += quantity

            elif action == CLOSE_LONG:
                position -= quantity

            elif action == OPEN_SHORT:
                position -= quantity

            elif action == CLOSE_SHORT:
                position += quantity

        return position

    # ========================================================
    # PREPARAR ORDEN
    # ========================================================

    def _prepare_operation(
        self,
        signal,
        operation_index,
        signal_action
    ):
        """
        Guarda el Order ID que IBKR está a punto de utilizar
        ANTES de enviar la orden.
        """

        current_position = (
            self.ib_app.get_position()
        )

        quantity = self._get_order_quantity()

        # ----------------------------------------------------
        # Traducir acción de señal a acción IBKR.
        # ----------------------------------------------------

        if signal_action == OPEN_LONG:

            ib_action = "BUY"
            expected_position = (
                current_position + quantity
            )

        elif signal_action == CLOSE_LONG:

            ib_action = "SELL"
            expected_position = (
                current_position - quantity
            )

        elif signal_action == OPEN_SHORT:

            ib_action = "SELL"
            expected_position = (
                current_position - quantity
            )

        elif signal_action == CLOSE_SHORT:

            ib_action = "BUY"
            expected_position = (
                current_position + quantity
            )

        else:

            raise RuntimeError(
                f"Acción desconocida: "
                f"{signal_action}"
            )

        # ----------------------------------------------------
        # El executor LIVE/PAPER utilizará este Order ID.
        # ----------------------------------------------------

        order_id = (
            self.ib_app.next_order_id
        )

        if order_id is None:

            raise RuntimeError(
                "IBKR no tiene un Order ID disponible."
            )

        # ----------------------------------------------------
        # Guardar ANTES de placeOrder().
        # ----------------------------------------------------

        self.state_manager.set_processing_order(
            signal[
                "message_id"
            ],
            operation_index,
            signal_action,
            ib_action,
            order_id,
            current_position,
            expected_position
        )

        return (
            current_position,
            expected_position,
            ib_action,
            order_id
        )

    # ========================================================
    # GUARDAR RESULTADO OPERACIÓN
    # ========================================================

    def _save_operation_result(
        self,
        signal,
        operation_index,
        signal_action,
        result
    ):

        result[
            "signal_action"
        ] = signal_action

        self.state_manager.set_operation_result(
            signal[
                "message_id"
            ],
            operation_index,
            result
        )

        return result

    # ========================================================
    # ACCIÓN INDIVIDUAL
    # ========================================================

    def _execute_single_action(
        self,
        signal,
        action,
        operation_index
    ):

        current_position = (
            self.ib_app.get_position()
        )

        # ----------------------------------------------------
        # Compatibilidad posición/señal.
        # ----------------------------------------------------

        if action == OPEN_LONG:

            if current_position != 0:

                result = self._blocked_result(
                    signal,
                    action,
                    (
                        "No se puede abrir un largo "
                        "con posición actual "
                        f"{current_position}."
                    ),
                    current_position
                )

                return result

            runner = self.ib_app.open_long

        elif action == CLOSE_LONG:

            if current_position <= 0:

                return self._blocked_result(
                    signal,
                    action,
                    (
                        "No existe un largo que cerrar."
                    ),
                    current_position
                )

            runner = self.ib_app.close_position

        elif action == OPEN_SHORT:

            if current_position != 0:

                return self._blocked_result(
                    signal,
                    action,
                    (
                        "No se puede abrir un corto "
                        "con posición actual "
                        f"{current_position}."
                    ),
                    current_position
                )

            runner = self.ib_app.open_short

        elif action == CLOSE_SHORT:

            if current_position >= 0:

                return self._blocked_result(
                    signal,
                    action,
                    (
                        "No existe un corto que cerrar."
                    ),
                    current_position
                )

            runner = self.ib_app.close_position

        else:

            return self._error_result(
                signal,
                f"Acción desconocida: {action}"
            )

        # ----------------------------------------------------
        # Preparar estado ANTES de la orden.
        # ----------------------------------------------------

        try:

            self._prepare_operation(
                signal,
                operation_index,
                action
            )

        except Exception as error:

            return self._error_result(
                signal,
                str(error)
            )

        # ----------------------------------------------------
        # Ejecutar.
        # ----------------------------------------------------

        result = runner()

        return self._save_operation_result(
            signal,
            operation_index,
            action,
            result
        )

    # ========================================================
    # LARGO → CORTO
    # ========================================================

    def _switch_long_to_short(
        self,
        signal
    ):

        initial_position = (
            self.ib_app.get_position()
        )

        quantity = self._get_order_quantity()

        if initial_position != quantity:

            return self._blocked_result(
                signal,
                "CERRAR_LARGO + ABRIR_CORTO",
                (
                    "La transición requiere "
                    "un largo de 1 contrato."
                ),
                initial_position
            )

        operations = []

        # ----------------------------------------------------
        # OPERACIÓN 1
        # ----------------------------------------------------

        try:

            self._prepare_operation(
                signal,
                0,
                CLOSE_LONG
            )

        except Exception as error:

            return self._error_result(
                signal,
                str(error)
            )

        close_result = self.ib_app.close_position()

        close_result = (
            self._save_operation_result(
                signal,
                0,
                CLOSE_LONG,
                close_result
            )
        )

        operations.append(
            close_result
        )

        if not close_result.get(
            "success",
            False
        ):

            return self._build_sequence_result(
                signal,
                False,
                operations,
                self.ib_app.get_position(),
                "No se pudo cerrar el largo."
            )

        if self.ib_app.get_position() != 0:

            return self._build_sequence_result(
                signal,
                False,
                operations,
                self.ib_app.get_position(),
                "La posición después del cierre "
                "no es 0."
            )

        # ----------------------------------------------------
        # OPERACIÓN 2
        # ----------------------------------------------------

        try:

            self._prepare_operation(
                signal,
                1,
                OPEN_SHORT
            )

        except Exception as error:

            return self._error_result(
                signal,
                str(error)
            )

        open_result = self.ib_app.open_short()

        open_result = (
            self._save_operation_result(
                signal,
                1,
                OPEN_SHORT,
                open_result
            )
        )

        operations.append(
            open_result
        )

        final_position = (
            self.ib_app.get_position()
        )

        if not open_result.get(
            "success",
            False
        ):

            return self._build_sequence_result(
                signal,
                False,
                operations,
                final_position,
                (
                    "El largo se cerró, "
                    "pero el corto no se pudo abrir."
                )
            )

        if final_position != -quantity:

            return self._build_sequence_result(
                signal,
                False,
                operations,
                final_position,
                "La posición final no es -1."
            )

        return self._build_sequence_result(
            signal,
            True,
            operations,
            final_position,
            None
        )

    # ========================================================
    # CORTO → LARGO
    # ========================================================

    def _switch_short_to_long(
        self,
        signal
    ):

        initial_position = (
            self.ib_app.get_position()
        )

        quantity = self._get_order_quantity()

        if initial_position != -quantity:

            return self._blocked_result(
                signal,
                "CERRAR_CORTO + ABRIR_LARGO",
                (
                    "La transición requiere "
                    "un corto de 1 contrato."
                ),
                initial_position
            )

        operations = []

        # ----------------------------------------------------
        # OPERACIÓN 1
        # ----------------------------------------------------

        try:

            self._prepare_operation(
                signal,
                0,
                CLOSE_SHORT
            )

        except Exception as error:

            return self._error_result(
                signal,
                str(error)
            )

        close_result = self.ib_app.close_position()

        close_result = (
            self._save_operation_result(
                signal,
                0,
                CLOSE_SHORT,
                close_result
            )
        )

        operations.append(
            close_result
        )

        if not close_result.get(
            "success",
            False
        ):

            return self._build_sequence_result(
                signal,
                False,
                operations,
                self.ib_app.get_position(),
                "No se pudo cerrar el corto."
            )

        if self.ib_app.get_position() != 0:

            return self._build_sequence_result(
                signal,
                False,
                operations,
                self.ib_app.get_position(),
                "La posición después del cierre "
                "no es 0."
            )

        # ----------------------------------------------------
        # OPERACIÓN 2
        # ----------------------------------------------------

        try:

            self._prepare_operation(
                signal,
                1,
                OPEN_LONG
            )

        except Exception as error:

            return self._error_result(
                signal,
                str(error)
            )

        open_result = self.ib_app.open_long()

        open_result = (
            self._save_operation_result(
                signal,
                1,
                OPEN_LONG,
                open_result
            )
        )

        operations.append(
            open_result
        )

        final_position = (
            self.ib_app.get_position()
        )

        if not open_result.get(
            "success",
            False
        ):

            return self._build_sequence_result(
                signal,
                False,
                operations,
                final_position,
                (
                    "El corto se cerró, "
                    "pero el largo no se pudo abrir."
                )
            )

        if final_position != quantity:

            return self._build_sequence_result(
                signal,
                False,
                operations,
                final_position,
                "La posición final no es +1."
            )

        return self._build_sequence_result(
            signal,
            True,
            operations,
            final_position,
            None
        )

    # ========================================================
    # RESULTADO SECUENCIA
    # ========================================================

    def _build_sequence_result(
        self,
        signal,
        success,
        operations,
        final_position,
        error
    ):

        return {
            "success": success,
            "type": "sequence",

            "message_id": signal.get(
                "message_id"
            ),

            "email_uid": signal.get(
                "email_uid"
            ),

            "sender": signal.get(
                "sender"
            ),

            "date": signal.get(
                "date"
            ),

            "subject": signal.get(
                "subject"
            ),

            "actions": signal.get(
                "actions",
                []
            ),

            "status": (
                "FILLED"
                if success
                else "ERROR"
            ),

            "filled": sum(
                operation.get(
                    "filled",
                    0.0
                )
                for operation in operations
            ),

            "price": self._get_last_price(
                operations
            ),

            "position": final_position,

            "error": error,

            "operations": operations
        }

    # ========================================================
    # RESULTADO INDIVIDUAL
    # ========================================================

    def _build_single_result(
        self,
        signal,
        action,
        result
    ):

        result[
            "message_id"
        ] = signal.get(
            "message_id"
        )

        result[
            "email_uid"
        ] = signal.get(
            "email_uid"
        )

        result[
            "sender"
        ] = signal.get(
            "sender"
        )

        result[
            "date"
        ] = signal.get(
            "date"
        )

        result[
            "subject"
        ] = signal.get(
            "subject"
        )

        result[
            "actions"
        ] = signal.get(
            "actions",
            []
        )

        result[
            "type"
        ] = "single"

        result[
            "action"
        ] = action

        return result

    # ========================================================
    # RESULTADO BLOQUEADO
    # ========================================================

    def _blocked_result(
        self,
        signal,
        action,
        error,
        position
    ):

        print()
        print(
            f">>> SEÑAL BLOQUEADA: "
            f"{error} <<<"
        )

        return {
            "success": False,
            "type": "blocked",

            "message_id": signal.get(
                "message_id"
            ) if signal else None,

            "email_uid": signal.get(
                "email_uid"
            ) if signal else None,

            "sender": signal.get(
                "sender"
            ) if signal else None,

            "date": signal.get(
                "date"
            ) if signal else None,

            "subject": signal.get(
                "subject"
            ) if signal else None,

            "actions": signal.get(
                "actions",
                []
            ) if signal else [],

            "action": action,

            "status": "BLOCKED",

            "filled": 0.0,

            "price": 0.0,

            "position": position,

            "order_id": None,

            "error": error,

            "operations": []
        }

    # ========================================================
    # ERROR
    # ========================================================

    def _error_result(
        self,
        signal,
        error
    ):

        print()
        print(
            f">>> ERROR DE SEÑAL: "
            f"{error} <<<"
        )

        return {
            "success": False,
            "type": "error",

            "message_id": (
                signal.get(
                    "message_id"
                )
                if signal
                else None
            ),

            "email_uid": (
                signal.get(
                    "email_uid"
                )
                if signal
                else None
            ),

            "sender": (
                signal.get(
                    "sender"
                )
                if signal
                else None
            ),

            "date": (
                signal.get(
                    "date"
                )
                if signal
                else None
            ),

            "subject": (
                signal.get(
                    "subject"
                )
                if signal
                else None
            ),

            "actions": (
                signal.get(
                    "actions",
                    []
                )
                if signal
                else []
            ),

            "status": "ERROR",

            "filled": 0.0,

            "price": 0.0,

            "position": (
                self.ib_app.get_position()
                if self.ib_app
                else None
            ),

            "order_id": None,

            "error": error,

            "operations": []
        }

    # ========================================================
    # ÚLTIMO PRECIO
    # ========================================================

    @staticmethod
    def _get_last_price(
        operations
    ):

        for operation in reversed(
            operations
        ):

            price = operation.get(
                "price"
            )

            if price not in (
                None,
                0,
                0.0
            ):

                return price

        return 0.0