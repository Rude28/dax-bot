import os
import time

from logger import (
    log_info,
    log_warning,
    log_error,
)

from bot_state import (
    bot_state,
    READY,
)

from pending_commands import (
    pending_commands,
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

TRADING_MODE = os.getenv(
    "TRADING_MODE",
    "PAPER"
)


# ============================================================
# FORMATEAR NÚMEROS
# ============================================================

def format_number(
    value,
    decimals=2
):

    if value is None:
        return "N/A"

    try:

        return (
            f"{float(value):.{decimals}f}"
        )

    except (
        TypeError,
        ValueError
    ):

        return str(value)


# ============================================================
# DIRECCIÓN DE POSICIÓN
# ============================================================

def get_position_direction(
    position
):

    try:

        position = float(
            position
        )

    except (
        TypeError,
        ValueError
    ):

        return "DESCONOCIDA"

    if position > 0:

        return "LARGO"

    if position < 0:

        return "CORTO"

    return "SIN POSICIÓN"


# ============================================================
# CONTROL EXECUTOR
# ============================================================

class ControlExecutor:

    def __init__(
        self,
        ib_app=None
    ):

        self.ib_app = ib_app

    # ========================================================
    # STATUS
    # ========================================================

    def get_status(
        self
    ):

        state = (
            bot_state.snapshot()
        )

        position = (
            state.get(
                "position",
                0.0
            )
        )

        direction = (
            get_position_direction(
                position
            )
        )

        status = state.get(
            "status",
            "UNKNOWN"
        )

        ibkr_connected = (
            state.get(
                "ibkr_connected",
                False
            )
        )

        gmail_connected = (
            state.get(
                "gmail_connected",
                False
            )
        )

        started_at = (
            state.get(
                "started_at"
            )
        )

        updated_at = (
            state.get(
                "updated_at"
            )
        )

        current_message_id = (
            state.get(
                "current_message_id"
            )
        )

        last_signal_status = (
            state.get(
                "last_signal_status"
            )
        )

        last_order_id = (
            state.get(
                "last_order_id"
            )
        )

        last_execution_price = (
            state.get(
                "last_execution_price"
            )
        )

        last_error = (
            state.get(
                "last_error"
            )
        )

        lines = []

        lines.append(
            "DAX BOT - ESTADO"
        )

        lines.append(
            "================"
        )

        lines.append("")

        lines.append(
            f"Estado: {status}"
        )

        lines.append(
            f"Modo: {TRADING_MODE}"
        )

        lines.append("")

        lines.append(
            "CONEXIONES"
        )

        lines.append(
            "----------------"
        )

        lines.append(
            "IBKR: "
            + (
                "CONECTADO"
                if ibkr_connected
                else "DESCONECTADO"
            )
        )

        lines.append(
            "Gmail: "
            + (
                "CONECTADO"
                if gmail_connected
                else "DESCONECTADO"
            )
        )

        lines.append("")

        lines.append(
            "POSICIÓN"
        )

        lines.append(
            "----------------"
        )

        lines.append(
            f"FDXM: "
            f"{format_number(position)}"
        )

        lines.append(
            f"Dirección: {direction}"
        )

        lines.append("")

        lines.append(
            "ÚLTIMA ACTIVIDAD"
        )

        lines.append(
            "----------------"
        )

        lines.append(
            f"Última señal: "
            f"{last_signal_status or 'N/A'}"
        )

        lines.append(
            f"Último Order ID: "
            f"{last_order_id or 'N/A'}"
        )

        lines.append(
            f"Último precio: "
            f"{format_number(last_execution_price)}"
        )

        lines.append(
            f"Señal actual: "
            f"{current_message_id or 'Ninguna'}"
        )

        lines.append("")

        lines.append(
            f"Iniciado: "
            f"{started_at or 'N/A'}"
        )

        lines.append(
            f"Actualizado: "
            f"{updated_at or 'N/A'}"
        )

        lines.append("")

        lines.append(
            "ÚLTIMO ERROR"
        )

        lines.append(
            "----------------"
        )

        lines.append(
            last_error or "Ninguno"
        )

        return "\n".join(
            lines
        )

    # ========================================================
    # POSITIONS
    # ========================================================

    def get_positions(
        self
    ):

        if self.ib_app is None:

            log_warning(
                "Consulta POSITIONS sin IBKR disponible."
            )

            return (
                "DAX BOT - POSICIONES\n"
                "====================\n\n"
                "IBKR no está disponible."
            )

        try:

            position = (
                self.ib_app.get_position()
            )

            direction = (
                get_position_direction(
                    position
                )
            )

            avg_cost = getattr(
                self.ib_app,
                "position_avg_cost",
                0.0
            )

            lines = []

            lines.append(
                "DAX BOT - POSICIONES"
            )

            lines.append(
                "===================="
            )

            lines.append("")

            lines.append(
                "FDXM"
            )

            lines.append(
                f"Cantidad: "
                f"{format_number(position)}"
            )

            lines.append(
                f"Dirección: "
                f"{direction}"
            )

            lines.append(
                f"Precio medio: "
                f"{format_number(avg_cost)}"
            )

            return "\n".join(
                lines
            )

        except Exception as error:

            log_error(
                f"Error consultando posiciones | "
                f"{type(error).__name__}: {error}"
            )

            return (
                "DAX BOT - POSICIONES\n"
                "====================\n\n"
                "ERROR consultando IBKR:\n"
                f"{error}"
            )

    # ========================================================
    # ACCOUNT
    # ========================================================

    def get_account(
        self
    ):

        if self.ib_app is None:

            log_warning(
                "Consulta ACCOUNT sin IBKR disponible."
            )

            return (
                "DAX BOT - CUENTA\n"
                "================\n\n"
                "IBKR no está disponible."
            )

        try:

            request_id = (
                self.ib_app.request_account_summary()
            )

            if request_id is None:

                return (
                    "DAX BOT - CUENTA\n"
                    "================\n\n"
                    "No se pudo iniciar la consulta "
                    "de cuenta."
                )

            account_data = (
                self.ib_app.get_account_summary(
                    request_id
                )
            )

            if not account_data:

                return (
                    "DAX BOT - CUENTA\n"
                    "================\n\n"
                    "No se recibieron datos de IBKR."
                )

            net_liquidation = (
                account_data.get(
                    "NetLiquidation"
                )
            )

            total_cash = (
                account_data.get(
                    "TotalCashValue"
                )
            )

            available_funds = (
                account_data.get(
                    "AvailableFunds"
                )
            )

            buying_power = (
                account_data.get(
                    "BuyingPower"
                )
            )

            currency = (
                account_data.get(
                    "Currency",
                    "EUR"
                )
            )

            lines = []

            lines.append(
                "DAX BOT - CUENTA"
            )

            lines.append(
                "================"
            )

            lines.append("")

            lines.append(
                f"Divisa: {currency}"
            )

            lines.append("")

            lines.append(
                f"Net Liquidation: "
                f"{format_number(net_liquidation)}"
            )

            lines.append(
                f"Cash: "
                f"{format_number(total_cash)}"
            )

            lines.append(
                f"Available Funds: "
                f"{format_number(available_funds)}"
            )

            lines.append(
                f"Buying Power: "
                f"{format_number(buying_power)}"
            )

            return "\n".join(
                lines
            )

        except Exception as error:

            log_error(
                f"Error consultando cuenta IBKR | "
                f"{type(error).__name__}: {error}"
            )

            return (
                "DAX BOT - CUENTA\n"
                "================\n\n"
                "ERROR consultando IBKR:\n"
                f"{error}"
            )

    # ========================================================
    # PREPARAR OPERACIÓN MANUAL
    # ========================================================

    def prepare_manual_command(
        self,
        control_email
    ):
        """
        Recibe una petición manual y crea una solicitud
        pendiente de confirmación.

        IMPORTANTE:

        No envía ninguna orden.
        """

        command = (
            control_email.get(
                "command"
            )
        )

        if self.ib_app is None:

            return self._manual_rejected(
                command,
                "IBKR no está disponible."
            )

        # ----------------------------------------------------
        # Estado global
        # ----------------------------------------------------

        state = (
            bot_state.snapshot()
        )

        if state.get(
            "status"
        ) != READY:

            return self._manual_rejected(
                command,
                (
                    "El bot no está en estado READY. "
                    f"Estado actual: "
                    f"{state.get('status')}"
                )
            )

        if not state.get(
            "ibkr_connected",
            False
        ):

            return self._manual_rejected(
                command,
                "IBKR no está conectado."
            )

        # ----------------------------------------------------
        # POSICIÓN ACTUAL
        # ----------------------------------------------------

        try:

            position = float(
                self.ib_app.get_position()
            )

        except Exception as error:

            log_error(
                f"No se pudo obtener posición para "
                f"operación manual | {error}"
            )

            return self._manual_rejected(
                command,
                "No se pudo verificar la posición."
            )

        # ----------------------------------------------------
        # VALIDAR OPERACIÓN
        # ----------------------------------------------------

        if command == "OPEN LONG":

            if position != 0:

                return self._manual_rejected(
                    command,
                    (
                        "Ya existe una posición abierta."
                    )
                )

            expected_position = (
                position + 1
            )

        elif command == "CLOSE LONG":

            if position != 1:

                return self._manual_rejected(
                    command,
                    (
                        "No existe una posición "
                        "larga de 1 contrato."
                    )
                )

            expected_position = (
                position - 1
            )

        elif command == "OPEN SHORT":

            if position != 0:

                return self._manual_rejected(
                    command,
                    (
                        "Ya existe una posición abierta."
                    )
                )

            expected_position = (
                position - 1
            )

        elif command == "CLOSE SHORT":

            if position != -1:

                return self._manual_rejected(
                    command,
                    (
                        "No existe una posición "
                        "corta de 1 contrato."
                    )
                )

            expected_position = (
                position + 1
            )

        else:

            return self._manual_rejected(
                command,
                "Operación no soportada."
            )

        # ----------------------------------------------------
        # CREAR SOLICITUD PENDIENTE
        # ----------------------------------------------------

        try:

            pending = (
                pending_commands.create(
                    command=command,

                    email_uid=control_email.get(
                        "email_uid"
                    ),

                    message_id=control_email.get(
                        "message_id"
                    ),

                    sender=control_email.get(
                        "sender"
                    ),

                    subject=control_email.get(
                        "subject"
                    ),

                    position_at_request=position,

                    expected_position=(
                        expected_position
                    ),

                    quantity=1,

                    metadata={
                        "trading_mode":
                            TRADING_MODE
                    }
                )
            )

        except Exception as error:

            log_error(
                f"No se pudo crear confirmación manual | "
                f"Command={command} | "
                f"{type(error).__name__}: {error}"
            )

            return self._manual_rejected(
                command,
                "No se pudo crear la confirmación."
            )

        code = pending[
            "code"
        ]

        log_info(
            f"Confirmación manual creada | "
            f"Command={command} | "
            f"Code={code} | "
            f"Position={position} | "
            f"Expected={expected_position}"
        )

        body = (
            "DAX BOT - CONFIRMACIÓN NECESARIA\n"
            "================================\n\n"

            f"Solicitud: {command}\n"
            "Contrato: FDXM\n"
            "Cantidad: 1\n"

            f"Posición actual: "
            f"{format_number(position)}\n"

            f"Posición esperada: "
            f"{format_number(expected_position)}\n\n"

            "LA ORDEN NO SE HA ENVIADO.\n\n"

            "Para confirmar, responde con:\n\n"

            f"DAXCONTROL CONFIRM {code}\n\n"

            "El código es de un solo uso.\n"
            "Caduca en 60 segundos.\n\n"

            "Antes de ejecutar se volverán a comprobar "
            "el estado del bot, la conexión con IBKR "
            "y la posición."
        )

        return {
            "success": True,
            "pending": True,
            "command": command,
            "code": code,
            "subject": (
                "DAX BOT - Confirmación necesaria"
            ),
            "body": body,
            "pending_command": pending,
        }

    # ========================================================
    # CONFIRMAR OPERACIÓN MANUAL
    # ========================================================

    def confirm_manual_command(
        self,
        control_email
    ):
        """
        Valida el código y devuelve la operación preparada.

        IMPORTANTE:

        Aquí todavía NO se envía la orden a IBKR.

        bot_auto.py será responsable de ejecutar la acción
        mediante SignalExecutor/PaperExecutor.
        """

        code = (
            str(
                control_email.get(
                    "code",
                    ""
                )
            )
            .strip()
        )

        if not code:

            return self._confirmation_rejected(
                "No se recibió ningún código."
            )

        pending = (
            pending_commands.get(
                code
            )
        )

        if pending is None:

            return self._confirmation_rejected(
                "Código inexistente."
            )

        # ----------------------------------------------------
        # Estado del código
        # ----------------------------------------------------

        if pending.get(
            "status"
        ) != "PENDING":

            return self._confirmation_rejected(
                "El código ya fue utilizado "
                "o está caducado."
            )

        # ----------------------------------------------------
        # Caducidad
        # ----------------------------------------------------

        expires_at = float(
            pending.get(
                "expires_at",
                0
            )
        )

        if time.time() >= expires_at:

            pending_commands.cancel(
                code,
                "Código caducado."
            )

            return self._confirmation_rejected(
                "El código ha caducado."
            )

        # ----------------------------------------------------
        # Remitente
        # ----------------------------------------------------

        original_sender = (
            pending.get(
                "sender"
            )
        )

        current_sender = (
            control_email.get(
                "sender"
            )
        )

        if (
            not original_sender
            or not current_sender
            or original_sender.strip().lower()
            != current_sender.strip().lower()
        ):

            return self._confirmation_rejected(
                (
                    "El remitente no coincide "
                    "con la solicitud original."
                )
            )

        # ----------------------------------------------------
        # IBKR
        # ----------------------------------------------------

        if self.ib_app is None:

            return self._confirmation_rejected(
                "IBKR no está disponible."
            )

        # ----------------------------------------------------
        # Estado global
        # ----------------------------------------------------

        state = (
            bot_state.snapshot()
        )

        if state.get(
            "status"
        ) != READY:

            return self._confirmation_rejected(
                (
                    "El bot no está en READY. "
                    f"Estado actual: "
                    f"{state.get('status')}"
                )
            )

        if not state.get(
            "ibkr_connected",
            False
        ):

            return self._confirmation_rejected(
                "IBKR no está conectado."
            )

        # ----------------------------------------------------
        # Comprobar posición de nuevo
        # ----------------------------------------------------

        try:

            current_position = float(
                self.ib_app.get_position()
            )

        except Exception as error:

            log_error(
                f"No se pudo verificar posición "
                f"durante confirmación | {error}"
            )

            return self._confirmation_rejected(
                "No se pudo verificar la posición."
            )

        original_position = float(
            pending.get(
                "position_at_request"
            )
        )

        expected_position = float(
            pending.get(
                "expected_position"
            )
        )

        if current_position != (
            original_position
        ):

            pending_commands.cancel(
                code,
                "La posición cambió desde la solicitud."
            )

            return self._confirmation_rejected(
                (
                    "La posición ha cambiado desde "
                    "la solicitud original.\n\n"
                    f"Posición original: "
                    f"{format_number(original_position)}\n"
                    f"Posición actual: "
                    f"{format_number(current_position)}\n\n"
                    "No se ha enviado ninguna orden."
                )
            )

        # ----------------------------------------------------
        # Validar coherencia comando / posición
        # ----------------------------------------------------

        command = pending.get(
            "command"
        )

        if command == "OPEN LONG":

            valid = (
                current_position == 0
                and expected_position == 1
            )

        elif command == "CLOSE LONG":

            valid = (
                current_position == 1
                and expected_position == 0
            )

        elif command == "OPEN SHORT":

            valid = (
                current_position == 0
                and expected_position == -1
            )

        elif command == "CLOSE SHORT":

            valid = (
                current_position == -1
                and expected_position == 0
            )

        else:

            valid = False

        if not valid:

            pending_commands.cancel(
                code,
                "La operación ya no es coherente con la posición."
            )

            return self._confirmation_rejected(
                (
                    "La solicitud ya no coincide "
                    "con la posición actual."
                )
            )

        # ----------------------------------------------------
        # Consumir código ANTES de devolver la orden
        #
        # Así un mismo código no puede utilizarse dos veces.
        # ----------------------------------------------------

        used = (
            pending_commands.mark_used(
                code
            )
        )

        if used is None:

            return self._confirmation_rejected(
                "El código ya no está disponible."
            )

        if used.get(
            "status"
        ) != "USED":

            return self._confirmation_rejected(
                "No se pudo bloquear el código."
            )

        log_info(
            f"Confirmación manual aceptada | "
            f"Command={command} | "
            f"Code={code} | "
            f"Position={current_position}"
        )

        return {
            "success": True,

            "confirmed": True,

            "command": command,

            "subject": (
                "DAX BOT - Confirmación aceptada"
            ),

            "body": (
                f"Confirmación aceptada para: "
                f"{command}\n\n"
                "La operación ha sido validada "
                "y puede pasar al ejecutor."
            ),

            "pending": pending,

            "position": current_position,

            "expected_position": (
                expected_position
            ),

            "code": code,
        }

    # ========================================================
    # EJECUTAR COMANDO DE CONSULTA
    # ========================================================

    def execute(
        self,
        command
    ):

        command = (
            command
            .strip()
            .upper()
        )

        log_info(
            f"Ejecutando comando de control | "
            f"Command={command}"
        )

        if command == "STATUS":

            return {
                "success": True,
                "command": command,
                "subject": (
                    "DAX BOT - Estado"
                ),
                "body": self.get_status()
            }

        if command == "POSITIONS":

            return {
                "success": True,
                "command": command,
                "subject": (
                    "DAX BOT - Posiciones"
                ),
                "body": self.get_positions()
            }

        if command == "ACCOUNT":

            return {
                "success": True,
                "command": command,
                "subject": (
                    "DAX BOT - Cuenta"
                ),
                "body": self.get_account()
            }

        # ----------------------------------------------------
        # Las operaciones manuales no se ejecutan mediante
        # execute(). Primero requieren confirmación.
        # ----------------------------------------------------

        if command in (
            "OPEN LONG",
            "CLOSE LONG",
            "OPEN SHORT",
            "CLOSE SHORT",
        ):

            return {
                "success": False,
                "command": command,
                "requires_confirmation": True,
                "subject": (
                    "DAX BOT - Confirmación necesaria"
                ),
                "body": (
                    "Esta operación necesita "
                    "confirmación de dos pasos."
                )
            }

        log_warning(
            f"Comando de control no soportado | "
            f"Command={command}"
        )

        return {
            "success": False,
            "command": command,
            "subject": (
                "DAX BOT - Comando rechazado"
            ),
            "body": (
                "Comando no soportado."
            )
        }

    # ========================================================
    # RECHAZO DE OPERACIÓN MANUAL
    # ========================================================

    @staticmethod
    def _manual_rejected(
        command,
        reason
    ):

        log_warning(
            f"Operación manual rechazada | "
            f"Command={command} | "
            f"Reason={reason}"
        )

        return {
            "success": False,
            "command": command,
            "subject": (
                "DAX BOT - Operación rechazada"
            ),
            "body": (
                f"Operación: {command}\n\n"
                f"Motivo: {reason}\n\n"
                "No se ha enviado ninguna orden."
            )
        }

    # ========================================================
    # RECHAZO DE CONFIRMACIÓN
    # ========================================================

    @staticmethod
    def _confirmation_rejected(
        reason
    ):

        log_warning(
            f"Confirmación manual rechazada | "
            f"Reason={reason}"
        )

        return {
            "success": False,
            "confirmed": False,
            "subject": (
                "DAX BOT - Confirmación rechazada"
            ),
            "body": (
                "CONFIRMACIÓN RECHAZADA\n\n"
                f"Motivo: {reason}\n\n"
                "No se ha enviado ninguna orden."
            )
        }