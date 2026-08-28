import os

from logger import (
    log_info,
    log_warning,
    log_error,
)

from bot_state import (
    bot_state,
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

TRADING_MODE = os.getenv(
    "TRADING_MODE",
    "LIVE"
)


# ============================================================
# COMANDOS
# ============================================================

STATUS = "STATUS"
POSITIONS = "POSITIONS"
ACCOUNT = "ACCOUNT"

OPEN_LONG = "OPEN LONG"
CLOSE_LONG = "CLOSE LONG"
OPEN_SHORT = "OPEN SHORT"
CLOSE_SHORT = "CLOSE SHORT"

SUPPORTED_QUERY_COMMANDS = {
    STATUS,
    POSITIONS,
    ACCOUNT,
}

SUPPORTED_MANUAL_COMMANDS = {
    OPEN_LONG,
    CLOSE_LONG,
    OPEN_SHORT,
    CLOSE_SHORT,
}


# ============================================================
# UTILIDADES
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
    # DISPONIBILIDAD IBKR
    # ========================================================

    def _ibkr_ready(self):

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

        if hasattr(
            self.ib_app,
            "isConnected"
        ):

            try:

                return bool(
                    self.ib_app.isConnected()
                )

            except Exception:

                return False

        return True

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

        status = (
            state.get(
                "status",
                "UNKNOWN"
            )
        )

        ibkr_connected = bool(
            state.get(
                "ibkr_connected",
                False
            )
        )

        gmail_connected = bool(
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
                "POSITIONS sin IBKR."
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

            account_id = getattr(
                self.ib_app,
                "account_id",
                None
            )

            lines = []

            lines.append(
                "DAX BOT - POSICIONES"
            )

            lines.append(
                "===================="
            )

            lines.append("")

            if account_id:

                lines.append(
                    f"Cuenta: {account_id}"
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
                "ACCOUNT sin IBKR."
            )

            return (
                "DAX BOT - CUENTA\n"
                "================\n\n"
                "IBKR no está disponible."
            )

        try:

            # ------------------------------------------------
            # Si el executor implementa directamente la capa
            # de cuenta, la utilizamos.
            # ------------------------------------------------

            if hasattr(
                self.ib_app,
                "get_account_snapshot"
            ):

                account_data = (
                    self.ib_app
                    .get_account_snapshot()
                )

            elif hasattr(
                self.ib_app,
                "get_account_summary"
            ) and hasattr(
                self.ib_app,
                "request_account_summary"
            ):

                request_id = (
                    self.ib_app
                    .request_account_summary()
                )

                if request_id is None:

                    return (
                        "DAX BOT - CUENTA\n"
                        "================\n\n"
                        "No se pudo iniciar la consulta."
                    )

                account_data = (
                    self.ib_app
                    .get_account_summary(
                        request_id
                    )
                )

            else:

                account_data = None

            if not account_data:

                account_id = getattr(
                    self.ib_app,
                    "account_id",
                    None
                )

                accounts = getattr(
                    self.ib_app,
                    "accounts",
                    []
                )

                lines = [
                    "DAX BOT - CUENTA",
                    "================",
                    "",
                ]

                if account_id:

                    lines.append(
                        f"Cuenta: {account_id}"
                    )

                elif accounts:

                    lines.append(
                        f"Cuentas: {accounts}"
                    )

                else:

                    lines.append(
                        "Cuenta: N/D"
                    )

                lines.append("")

                lines.append(
                    "El executor LIVE actual "
                    "no tiene todavía una capa "
                    "AccountSummary implementada."
                )

                return "\n".join(
                    lines
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

            lines = [
                "DAX BOT - CUENTA",
                "================",
                "",
                f"Divisa: {currency}",
                "",
                f"Net Liquidation: "
                f"{format_number(net_liquidation)}",
                f"Cash: "
                f"{format_number(total_cash)}",
                f"Available Funds: "
                f"{format_number(available_funds)}",
                f"Buying Power: "
                f"{format_number(buying_power)}",
            ]

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
    # OPERACIÓN MANUAL
    # ========================================================

    def execute_manual(
        self,
        command
    ):

        command = (
            str(command)
            .strip()
            .upper()
        )

        log_info(
            f"Ejecutando comando manual | "
            f"Command={command}"
        )

        if command not in (
            SUPPORTED_MANUAL_COMMANDS
        ):

            return {
                "success": False,
                "command": command,
                "subject":
                    "DAX BOT - Control rechazado",
                "body": (
                    "COMANDO NO SOPORTADO.\n\n"
                    f"Comando: {command}"
                )
            }

        if self.ib_app is None:

            return {
                "success": False,
                "command": command,
                "subject":
                    "DAX BOT - Operación manual",
                "body": (
                    "OPERACIÓN NO REALIZADA.\n\n"
                    "IBKR no está disponible."
                )
            }

        if not self._ibkr_ready():

            return {
                "success": False,
                "command": command,
                "subject":
                    "DAX BOT - Operación manual",
                "body": (
                    "OPERACIÓN NO REALIZADA.\n\n"
                    "IBKR no está preparado para operar."
                )
            }

        # ----------------------------------------------------
        # Obtener posición antes de actuar.
        # ----------------------------------------------------

        try:

            position = (
                self.ib_app.get_position()
            )

        except Exception as error:

            return {
                "success": False,
                "command": command,
                "subject":
                    "DAX BOT - Operación manual",
                "body": (
                    "OPERACIÓN NO REALIZADA.\n\n"
                    "No se pudo consultar la posición.\n"
                    f"Error: {error}"
                )
            }

        # ----------------------------------------------------
        # Decidir operación.
        # ----------------------------------------------------

        if command == OPEN_LONG:

            if position != 0:

                return self._manual_blocked(
                    command,
                    position,
                    "Ya existe una posición abierta."
                )

            method_name = "open_long"

        elif command == CLOSE_LONG:

            if position <= 0:

                return self._manual_blocked(
                    command,
                    position,
                    "No existe un largo que cerrar."
                )

            method_name = "close_position"

        elif command == OPEN_SHORT:

            if position != 0:

                return self._manual_blocked(
                    command,
                    position,
                    "Ya existe una posición abierta."
                )

            method_name = "open_short"

        else:

            if position >= 0:

                return self._manual_blocked(
                    command,
                    position,
                    "No existe un corto que cerrar."
                )

            method_name = "close_position"

        # ----------------------------------------------------
        # El LiveExecutor mantiene actualmente una barrera
        # de seguridad: la llamada devolverá BLOCKED mientras
        # VALIDATION_ONLY esté activo.
        # ----------------------------------------------------

        method = getattr(
            self.ib_app,
            method_name,
            None
        )

        if method is None:

            return {
                "success": False,
                "command": command,
                "subject":
                    "DAX BOT - Operación manual",
                "body": (
                    "OPERACIÓN NO REALIZADA.\n\n"
                    f"El executor no implementa "
                    f"{method_name}()."
                )
            }

        try:

            result = (
                method()
            )

        except Exception as error:

            log_error(
                f"Error ejecutando comando manual | "
                f"Command={command} | "
                f"{type(error).__name__}: {error}"
            )

            return {
                "success": False,
                "command": command,
                "subject":
                    "DAX BOT - Operación manual",
                "body": (
                    "OPERACIÓN NO REALIZADA.\n\n"
                    f"Error: {error}"
                )
            }

        if not isinstance(
            result,
            dict
        ):

            return {
                "success": False,
                "command": command,
                "subject":
                    "DAX BOT - Operación manual",
                "body": (
                    "OPERACIÓN NO REALIZADA.\n\n"
                    "El executor devolvió un resultado "
                    "no válido."
                )
            }

        success = bool(
            result.get(
                "success",
                False
            )
        )

        final_position = result.get(
            "position",
            position
        )

        status = result.get(
            "status",
            "UNKNOWN"
        )

        order_id = result.get(
            "order_id"
        )

        price = result.get(
            "price"
        )

        error = result.get(
            "error"
        )

        if success:

            subject = (
                "DAX BOT - Operación manual realizada"
            )

            body = (
                "OPERACIÓN MANUAL REALIZADA\n\n"
                f"Solicitud: {command}\n"
                f"Estado: {status}\n"
                f"Order ID: {order_id or 'N/A'}\n"
                f"Cantidad: "
                f"{result.get('filled', 0)}\n"
                f"Precio: "
                f"{format_number(price)}\n"
                f"Posición final: "
                f"{final_position}\n"
            )

        else:

            subject = (
                "DAX BOT - Operación manual no realizada"
            )

            body = (
                "OPERACIÓN MANUAL NO REALIZADA\n\n"
                f"Solicitud: {command}\n"
                f"Estado: {status}\n"
                f"Posición: {final_position}\n"
                f"Error: {error or 'N/A'}\n"
            )

        return {
            "success":
                success,

            "command":
                command,

            "subject":
                subject,

            "body":
                body,

            "result":
                result
        }

    # ========================================================
    # BLOQUEO MANUAL
    # ========================================================

    @staticmethod
    def _manual_blocked(
        command,
        position,
        reason
    ):

        log_warning(
            f"Operacion manual bloqueada | "
            f"Command={command} | "
            f"Position={position} | "
            f"Reason={reason}"
        )

        return {
            "success":
                False,

            "command":
                command,

            "subject":
                "DAX BOT - Operación manual bloqueada",

            "body": (
                "OPERACIÓN MANUAL BLOQUEADA\n\n"
                f"Solicitud: {command}\n"
                f"Posición actual: {position}\n"
                f"Motivo: {reason}\n\n"
                "No se ha enviado ninguna orden."
            )
        }

    # ========================================================
    # EJECUTAR CUALQUIER COMANDO
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

        if command == STATUS:

            result = {
                "success": True,
                "command": STATUS,
                "subject":
                    "DAX BOT - Estado",
                "body":
                    self.get_status()
            }

        elif command == POSITIONS:

            result = {
                "success": True,
                "command": POSITIONS,
                "subject":
                    "DAX BOT - Posiciones",
                "body":
                    self.get_positions()
            }

        elif command == ACCOUNT:

            result = {
                "success": True,
                "command": ACCOUNT,
                "subject":
                    "DAX BOT - Cuenta",
                "body":
                    self.get_account()
            }

        elif command in (
            SUPPORTED_MANUAL_COMMANDS
        ):

            result = self.execute_manual(
                command
            )

        else:

            log_warning(
                f"Comando de control no soportado | "
                f"Command={command}"
            )

            result = {
                "success": False,
                "command": command,
                "subject":
                    "DAX BOT - Comando rechazado",
                "body": (
                    "Comando no soportado.\n\n"
                    f"Comando: {command}"
                )
            }

        log_info(
            f"Resultado comando control | "
            f"Command={command} | "
            f"Success={result.get('success')}"
        )

        return result


# ============================================================
# PRUEBA LOCAL SIN OPERAR
# ============================================================

def main():

    print(
        "========================================"
    )

    print(
        "     CONTROL EXECUTOR - LIVE"
    )

    print(
        "========================================"
    )

    print(
        "Comandos de consulta:"
    )

    for command in sorted(
        SUPPORTED_QUERY_COMMANDS
    ):

        print(
            f"  - {command}"
        )

    print()

    print(
        "Comandos manuales:"
    )

    for command in sorted(
        SUPPORTED_MANUAL_COMMANDS
    ):

        print(
            f"  - {command}"
        )

    print()

    print(
        "El LiveExecutor mantiene las órdenes"
    )

    print(
        "bloqueadas mientras VALIDATION_ONLY=True."
    )


if __name__ == "__main__":

    main()
