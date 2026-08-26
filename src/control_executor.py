import os

from logger import (
    log_info,
    log_warning,
    log_error,
)

from bot_state import (
    bot_state,
    READY,
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

TRADING_MODE = os.getenv(
    "TRADING_MODE",
    "PAPER"
)


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

            if hasattr(
                self.ib_app,
                "isConnected"
            ):

                if not self.ib_app.isConnected():

                    log_warning(
                        "Consulta ACCOUNT bloqueada: "
                        "IBKR desconectado."
                    )

                    return (
                        "DAX BOT - CUENTA\n"
                        "================\n\n"
                        "IBKR está desconectado."
                    )

            request_id = (
                self.ib_app.request_account_summary()
            )

            if request_id is None:

                log_error(
                    "IBKR no devolvió Request ID "
                    "para ACCOUNT SUMMARY."
                )

                return (
                    "DAX BOT - CUENTA\n"
                    "================\n\n"
                    "No se pudo iniciar la consulta "
                    "de cuenta."
                )

            log_info(
                f"Consulta ACCOUNT iniciada | "
                f"RequestID={request_id}"
            )

            account_data = (
                self.ib_app.get_account_summary(
                    request_id
                )
            )

            if not account_data:

                log_warning(
                    f"ACCOUNT SUMMARY sin datos | "
                    f"RequestID={request_id}"
                )

                return (
                    "DAX BOT - CUENTA\n"
                    "================\n\n"
                    "IBKR no devolvió datos de cuenta."
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
                    "Currency"
                )
            )

            if not currency:

                raw_summary = getattr(
                    self.ib_app,
                    "account_summary",
                    {}
                )

                for tag in (
                    "NetLiquidation",
                    "TotalCashValue",
                    "AvailableFunds",
                    "BuyingPower",
                ):

                    raw_data = (
                        raw_summary.get(
                            tag
                        )
                    )

                    if isinstance(
                        raw_data,
                        dict
                    ):

                        currency = (
                            raw_data.get(
                                "currency"
                            )
                        )

                        if currency:

                            break

            if not currency:

                currency = "EUR"

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

            lines.append("")

            lines.append(
                "Datos consultados directamente "
                "desde IBKR."
            )

            log_info(
                f"ACCOUNT SUMMARY completado | "
                f"RequestID={request_id} | "
                f"Currency={currency} | "
                f"NetLiquidation={net_liquidation} | "
                f"Cash={total_cash} | "
                f"AvailableFunds={available_funds} | "
                f"BuyingPower={buying_power}"
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
    # EJECUCIÓN MANUAL DIRECTA
    # ========================================================

    def execute_manual_command(
        self,
        control_email
    ):
        """
        Valida una orden manual y devuelve una señal
        compatible con SignalExecutor.

        IMPORTANTE:
        Este método NO envía directamente la orden a IBKR.

        Devuelve la señal para que bot_auto.py la pase al
        mismo SignalExecutor utilizado por las señales
        automáticas.
        """

        command = (
            str(
                control_email.get(
                    "command",
                    ""
                )
            )
            .strip()
            .upper()
        )

        if command not in MANUAL_COMMANDS:

            return {
                "success": False,
                "command": command,
                "error": (
                    "Comando manual no soportado."
                ),
                "body": (
                    "Operación no soportada."
                )
            }

        # ----------------------------------------------------
        # IBKR disponible
        # ----------------------------------------------------

        if self.ib_app is None:

            return {
                "success": False,
                "command": command,
                "error": (
                    "IBKR no está disponible."
                ),
                "body": (
                    "No se ha enviado ninguna orden."
                )
            }

        # ----------------------------------------------------
        # Estado del bot
        # ----------------------------------------------------

        state = (
            bot_state.snapshot()
        )

        current_status = state.get(
            "status"
        )

        if current_status != READY:

            log_warning(
                f"Orden manual bloqueada | "
                f"Command={command} | "
                f"BotStatus={current_status}"
            )

            return {
                "success": False,
                "command": command,
                "error": (
                    "El bot no está en estado READY."
                ),
                "body": (
                    f"Estado actual del bot: "
                    f"{current_status}\n\n"
                    "No se ha enviado ninguna orden."
                )
            }

        # ----------------------------------------------------
        # Estado de conexión IBKR
        # ----------------------------------------------------

        if not state.get(
            "ibkr_connected",
            False
        ):

            log_warning(
                f"Orden manual bloqueada | "
                f"Command={command} | "
                f"Motivo=IBKR desconectado"
            )

            return {
                "success": False,
                "command": command,
                "error": (
                    "IBKR no está conectado."
                ),
                "body": (
                    "IBKR está desconectado.\n\n"
                    "No se ha enviado ninguna orden."
                )
            }

        # ----------------------------------------------------
        # Comprobar conexión real de IBKR si está disponible
        # ----------------------------------------------------

        try:

            if hasattr(
                self.ib_app,
                "isConnected"
            ):

                if not self.ib_app.isConnected():

                    log_warning(
                        f"Orden manual bloqueada | "
                        f"Command={command} | "
                        f"Motivo=Socket IBKR desconectado"
                    )

                    return {
                        "success": False,
                        "command": command,
                        "error": (
                            "La conexión real con IBKR "
                            "no está disponible."
                        ),
                        "body": (
                            "IBKR está desconectado.\n\n"
                            "No se ha enviado ninguna orden."
                        )
                    }

        except Exception as error:

            log_error(
                f"Error comprobando conexión IBKR | "
                f"{type(error).__name__}: {error}"
            )

            return {
                "success": False,
                "command": command,
                "error": str(error),
                "body": (
                    "No se pudo verificar la conexión "
                    "con IBKR.\n\n"
                    "No se ha enviado ninguna orden."
                )
            }

        # ----------------------------------------------------
        # Obtener posición REAL
        # ----------------------------------------------------

        try:

            position = float(
                self.ib_app.get_position()
            )

        except Exception as error:

            log_error(
                f"No se pudo obtener posición para "
                f"operación manual | "
                f"Command={command} | "
                f"{type(error).__name__}: {error}"
            )

            return {
                "success": False,
                "command": command,
                "error": (
                    "No se pudo verificar la posición."
                ),
                "body": (
                    "No se pudo verificar la posición "
                    "actual.\n\n"
                    "No se ha enviado ninguna orden."
                )
            }

        # ====================================================
        # VALIDACIÓN DE CADA OPERACIÓN
        # ====================================================

        if command == "OPEN LONG":

            if position != 0:

                return self._manual_blocked(
                    command,
                    position,
                    (
                        "Ya existe una posición abierta."
                    )
                )

            action = "ABRIR_LARGO"
            expected_position = 1.0

        elif command == "CLOSE LONG":

            if position != 1:

                return self._manual_blocked(
                    command,
                    position,
                    (
                        "No existe un largo de "
                        "1 contrato."
                    )
                )

            action = "CERRAR_LARGO"
            expected_position = 0.0

        elif command == "OPEN SHORT":

            if position != 0:

                return self._manual_blocked(
                    command,
                    position,
                    (
                        "Ya existe una posición abierta."
                    )
                )

            action = "ABRIR_CORTO"
            expected_position = -1.0

        else:
            # CLOSE SHORT

            if position != -1:

                return self._manual_blocked(
                    command,
                    position,
                    (
                        "No existe un corto de "
                        "1 contrato."
                    )
                )

            action = "CERRAR_CORTO"
            expected_position = 0.0

        # ====================================================
        # CREAR SEÑAL COMPATIBLE CON SIGNAL EXECUTOR
        # ====================================================

        message_id = (
            "MANUAL:"
            + str(
                control_email.get(
                    "message_id",
                    ""
                )
            )
        )

        signal = {

            "message_id":
                message_id,

            "email_uid":
                control_email.get(
                    "email_uid"
                ),

            "sender":
                control_email.get(
                    "sender"
                ),

            "date":
                control_email.get(
                    "date"
                ),

            "subject":
                control_email.get(
                    "subject"
                ),

            "actions": [
                action
            ],

            "manual":
                True,

            "manual_command":
                command,

            "position_initial":
                position,

            "expected_final_position":
                expected_position,
        }

        log_info(
            f"Orden manual validada | "
            f"Command={command} | "
            f"Action={action} | "
            f"Position={position} | "
            f"Expected={expected_position} | "
            f"Message-ID={message_id}"
        )

        return {
            "success": True,
            "command": command,
            "action": action,
            "signal": signal,
            "position": position,
            "expected_position": expected_position,
            "body": (
                f"Orden manual validada: "
                f"{command}\n\n"
                f"Posición actual: "
                f"{format_number(position)}\n"
                f"Posición esperada: "
                f"{format_number(expected_position)}\n\n"
                "Se enviará al SignalExecutor."
            )
        }

    # ========================================================
    # BLOQUEO DE OPERACIÓN MANUAL
    # ========================================================

    @staticmethod
    def _manual_blocked(
        command,
        position,
        reason
    ):

        log_warning(
            f"Operación manual bloqueada | "
            f"Command={command} | "
            f"Position={position} | "
            f"Reason={reason}"
        )

        return {
            "success": False,
            "command": command,
            "position": position,
            "error": reason,
            "body": (
                f"Operación: {command}\n\n"
                f"Posición actual: "
                f"{format_number(position)}\n\n"
                f"Motivo: {reason}\n\n"
                "No se ha enviado ninguna orden."
            )
        }

    # ========================================================
    # COMANDOS DE CONSULTA
    # ========================================================

    def execute(
        self,
        command
    ):

        command = (
            str(command)
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

        if command in MANUAL_COMMANDS:

            return self.execute_manual_command(
                {
                    "command": command
                }
            )

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