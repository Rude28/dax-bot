import os
import threading
import time

from dotenv import load_dotenv

from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order


# ============================================================
# CONFIGURACION LIVE
# ============================================================

load_dotenv()

HOST = os.getenv(
    "IB_HOST",
    "127.0.0.1"
)

# IB Gateway LIVE
PORT = int(
    os.getenv(
        "IB_LIVE_PORT",
        "4001"
    )
)

# Separado del PaperExecutor
CLIENT_ID = int(
    os.getenv(
        "IB_LIVE_CLIENT_ID",
        "5"
    )
)

# FDXM SEP26
CON_ID = int(
    os.getenv(
        "FDXM_CON_ID",
        "655095900"
    )
)

EXCHANGE = os.getenv(
    "FDXM_EXCHANGE",
    "EUREX"
)

SYMBOL = os.getenv(
    "FDXM_SYMBOL",
    "FDXM"
)

CURRENCY = os.getenv(
    "FDXM_CURRENCY",
    "EUR"
)

QUANTITY = int(
    os.getenv(
        "FDXM_QUANTITY",
        "1"
    )
)

if QUANTITY < 1:
    raise ValueError(
        "FDXM_QUANTITY debe ser un entero >= 1."
    )

ORDER_TIMEOUT = float(
    os.getenv(
        "IB_ORDER_TIMEOUT",
        "30"
    )
)

POSITION_TIMEOUT = float(
    os.getenv(
        "IB_POSITION_TIMEOUT",
        "5"
    )
)

# ============================================================
# BARRERA LIVE
# ============================================================
#
# MUY IMPORTANTE:
#
# Esta variable permite activar posteriormente el envio de
# ordenes LIVE, pero por seguridad el valor por defecto es
# FALSE.
#
# Mientras sea FALSE:
#     send_order() NO llama a placeOrder()
#
# Esto permite construir y probar toda la arquitectura LIVE
# sin riesgo de enviar una orden accidental.
# ============================================================

LIVE_TRADING_ENABLED = (
    os.getenv(
        "LIVE_TRADING_ENABLED",
        "false"
    )
    .strip()
    .lower()
    in (
        "1",
        "true",
        "yes",
        "on"
    )
)

# Bloqueo adicional de esta fase de desarrollo.
# Aunque el .env dijera true, mientras sea True no se permite
# una orden real.
VALIDATION_ONLY = True


# ============================================================
# LIVE EXECUTOR
# ============================================================

class LiveExecutor(EWrapper, EClient):

    def __init__(self):

        EClient.__init__(
            self,
            self
        )

        # ----------------------------------------------------
        # CONEXION
        # ----------------------------------------------------

        self.next_order_id = None

        self.connection_ready = (
            threading.Event()
        )

        self.connection_lost = (
            threading.Event()
        )

        self.api_thread = None

        # ----------------------------------------------------
        # CUENTA
        # ----------------------------------------------------

        self.accounts = []
        self.account_id = None

        # ----------------------------------------------------
        # POSICION
        # ----------------------------------------------------

        self.current_position = 0.0
        self.position_avg_cost = 0.0

        self.positions_ready = (
            threading.Event()
        )

        self.position_update_event = (
            threading.Event()
        )

        # ----------------------------------------------------
        # ORDENES
        # ----------------------------------------------------

        self.order_event = (
            threading.Event()
        )

        self.current_order_id = None

        self.order_status = None
        self.order_filled = 0.0
        self.order_remaining = 0.0
        self.order_avg_fill_price = 0.0

        # ----------------------------------------------------
        # ERRORES
        # ----------------------------------------------------

        self.error_message = None
        self.error_code = None

        # ----------------------------------------------------
        # RECONCILIACION
        # ----------------------------------------------------

        self.reconciliation_event = (
            threading.Event()
        )

        self.reconciliation_orders = {}

        # ----------------------------------------------------
        # IDENTIFICACION
        # ----------------------------------------------------

        self.environment = "LIVE"

        # Cantidad de contratos configurada para LIVE.
        self.order_quantity = QUANTITY

        # ----------------------------------------------------
        # LOCK
        # ----------------------------------------------------

        self._order_lock = (
            threading.Lock()
        )

    # ========================================================
    # CONEXION
    # ========================================================

    def nextValidId(
        self,
        orderId
    ):

        self.next_order_id = (
            int(orderId)
        )

        self.connection_ready.set()

        print()
        print(
            "========================================"
        )
        print(
            "CONEXION IBKR LIVE CORRECTA"
        )
        print(
            f"Next Order ID: {orderId}"
        )
        print(
            f"Puerto: {PORT}"
        )
        print(
            "========================================"
        )

        # Solicitar posiciones una vez que tenemos
        # identificador de orden valido.

        self.current_position = 0.0
        self.position_avg_cost = 0.0

        self.positions_ready.clear()

        print(
            "Solicitando posiciones LIVE..."
        )

        try:

            self.reqPositions()

        except Exception as error:

            self.error_message = str(
                error
            )

            print(
                "ERROR solicitando posiciones LIVE:"
            )

            print(
                f"{type(error).__name__}: "
                f"{error}"
            )

    # ========================================================
    # CUENTA
    # ========================================================

    def managedAccounts(
        self,
        accountsList
    ):

        self.accounts = [
            item.strip()
            for item in (
                accountsList or ""
            ).split(",")
            if item.strip()
        ]

        if self.accounts:

            self.account_id = (
                self.accounts[0]
            )

        print()
        print(
            "CUENTA IBKR LIVE"
        )

        print(
            f"Cuentas disponibles: "
            f"{self.accounts}"
        )

    # ========================================================
    # ERRORES
    # ========================================================

    def error(
        self,
        reqId,
        errorTime,
        errorCode,
        errorString,
        advancedOrderRejectJson=""
    ):

        if errorCode in (
            2104,
            2106,
            2107,
            2157,
            2158
        ):

            print(
                f"IBKR LIVE INFO | "
                f"code={errorCode} | "
                f"{errorString}"
            )

            # 2104/2106/2158 son mensajes normales.
            # 2157 puede aparecer durante una recuperacion
            # temporal de la granja de datos.
            return

        print(
            f"IBKR LIVE ERROR | "
            f"reqId={reqId} | "
            f"code={errorCode} | "
            f"message={errorString}"
        )

        self.error_message = (
            errorString
        )

        self.error_code = (
            errorCode
        )

        # Si el error pertenece a la orden actual,
        # despertamos send_order().

        if (
            self.current_order_id is not None
            and reqId == self.current_order_id
        ):

            self.order_status = "ERROR"
            self.order_event.set()

        # Detectar errores de conexion conocidos.

        if errorCode in (
            502,
            1100,
            1101,
            1102,
            1300
        ):

            self.connection_lost.set()

    # ========================================================
    # CONEXION PERDIDA
    # ========================================================

    def connectionClosed(
        self
    ):

        self.connection_lost.set()

        print()
        print(
            "IBKR LIVE: conexion cerrada."
        )

    # ========================================================
    # POSICIONES
    # ========================================================

    def position(
        self,
        account,
        contract,
        position,
        avgCost
    ):

        if int(
            getattr(
                contract,
                "conId",
                0
            )
        ) != CON_ID:

            return

        self.current_position = (
            float(position)
        )

        self.position_avg_cost = (
            float(avgCost)
        )

        print()
        print(
            "----------------------------------------"
        )
        print(
            "ACTUALIZACION DE POSICION LIVE"
        )
        print(
            f"Cuenta:        {account}"
        )
        print(
            f"Contrato:      {contract.conId}"
        )
        print(
            f"FDXM:          {self.current_position}"
        )
        print(
            f"Precio medio:  {self.position_avg_cost}"
        )
        print(
            "----------------------------------------"
        )

        self.position_update_event.set()

    def positionEnd(
        self
    ):

        print()
        print(
            "Posiciones LIVE recibidas."
        )

        self.positions_ready.set()

    # ========================================================
    # POSICION
    # ========================================================

    def get_position(
        self
    ):

        return (
            self.current_position
        )

    # ========================================================
    # CONTRATO
    # ========================================================

    def create_contract(
        self
    ):

        contract = Contract()

        contract.conId = CON_ID
        contract.exchange = EXCHANGE
        contract.secType = "FUT"
        contract.currency = CURRENCY

        return contract

    # ========================================================
    # VALIDAR CONTRATO
    # ========================================================

    def validate_contract(
        self
    ):

        contract = (
            self.create_contract()
        )

        valid = (
            int(
                getattr(
                    contract,
                    "conId",
                    0
                )
            ) == CON_ID
            and contract.exchange == EXCHANGE
            and contract.secType == "FUT"
            and contract.currency == CURRENCY
        )

        return {
            "valid": valid,
            "con_id": contract.conId,
            "symbol": SYMBOL,
            "exchange": contract.exchange,
            "sec_type": contract.secType,
            "currency": contract.currency
        }

    # ========================================================
    # ESTADO DE PREPARACION
    # ========================================================

    def readiness_snapshot(
        self
    ):

        try:

            connected = bool(
                self.isConnected()
            )

        except Exception:

            connected = False

        return {
            "environment":
                self.environment,

            "connected":
                connected,

            "connection_ready":
                self.connection_ready.is_set(),

            "positions_ready":
                self.positions_ready.is_set(),

            "account_id":
                self.account_id,

            "accounts":
                list(self.accounts),

            "position":
                self.current_position,

            "avg_cost":
                self.position_avg_cost,

            "next_order_id":
                self.next_order_id,

            "contract":
                self.validate_contract(),

            "live_trading_enabled":
                LIVE_TRADING_ENABLED,

            "validation_only":
                VALIDATION_ONLY
        }

    def is_trading_connection_ready(
        self
    ):

        snapshot = (
            self.readiness_snapshot()
        )

        return bool(
            snapshot["connected"]
            and snapshot["connection_ready"]
            and snapshot["positions_ready"]
            and snapshot["contract"]["valid"]
        )

    # ========================================================
    # ESPERAR POSICION
    # ========================================================

    def wait_for_position(
        self,
        expected_position,
        timeout=POSITION_TIMEOUT
    ):

        if (
            self.current_position
            == expected_position
        ):

            return True

        self.position_update_event.clear()

        if not self.position_update_event.wait(
            timeout=timeout
        ):

            return (
                self.current_position
                == expected_position
            )

        return (
            self.current_position
            == expected_position
        )

    # ========================================================
    # CREAR ORDEN MARKET
    # ========================================================

    def create_market_order(
        self,
        action
    ):

        order = Order()

        order.action = action
        order.orderType = "MKT"
        order.totalQuantity = QUANTITY
        order.tif = "DAY"
        order.transmit = True

        return order

    # ========================================================
    # NORMALIZAR ACCION
    # ========================================================

    @staticmethod
    def _normalize_ib_action(
        action
    ):

        action = str(
            action
        ).strip().upper()

        if action not in (
            "BUY",
            "SELL"
        ):

            raise ValueError(
                f"Accion IBKR no valida: "
                f"{action}"
            )

        return action

    # ========================================================
    # ENVIAR ORDEN
    # ========================================================

    def send_order(
        self,
        action
    ):

        action = (
            self._normalize_ib_action(
                action
            )
        )

        # ----------------------------------------------------
        # BARRERA ABSOLUTA
        # ----------------------------------------------------

        if (
            VALIDATION_ONLY
            or not LIVE_TRADING_ENABLED
        ):

            print()
            print(
                "========================================"
            )
            print(
                "ORDEN LIVE BLOQUEADA"
            )
            print(
                f"Accion solicitada: {action}"
            )
            print(
                f"LIVE_TRADING_ENABLED: "
                f"{LIVE_TRADING_ENABLED}"
            )
            print(
                f"VALIDATION_ONLY: "
                f"{VALIDATION_ONLY}"
            )
            print(
                "NO se llama a placeOrder()."
            )
            print(
                "========================================"
            )

            return {
                "success": False,
                "action": action,
                "status": "BLOCKED",
                "filled": 0.0,
                "price": 0.0,
                "position": self.current_position,
                "error": (
                    "Envio de ordenes LIVE "
                    "deshabilitado en esta fase."
                )
            }

        # ----------------------------------------------------
        # SOLO UNA ORDEN A LA VEZ
        # ----------------------------------------------------

        with self._order_lock:

            # ------------------------------------------------
            # Conexion
            # ------------------------------------------------

            if not self.is_trading_connection_ready():

                return {
                    "success": False,
                    "action": action,
                    "status": "ERROR",
                    "filled": 0.0,
                    "price": 0.0,
                    "position": self.current_position,
                    "error": (
                        "IBKR LIVE no esta preparado."
                    )
                }

            # ------------------------------------------------
            # Capturar posición ANTES de enviar la orden.
            #
            # La posición puede actualizarse asíncronamente
            # después del Filled. Por eso expected_position
            # debe calcularse desde esta fotografía inicial,
            # nunca desde current_position después del Fill.
            # ------------------------------------------------

            initial_position = float(
                self.current_position
            )

            # ------------------------------------------------
            # Order ID
            # ------------------------------------------------

            if (
                self.next_order_id
                is None
            ):

                return {
                    "success": False,
                    "action": action,
                    "status": "ERROR",
                    "filled": 0.0,
                    "price": 0.0,
                    "position": self.current_position,
                    "error": (
                        "No existe Order ID."
                    )
                }

            # ------------------------------------------------
            # Contrato
            # ------------------------------------------------

            contract_info = (
                self.validate_contract()
            )

            if not contract_info["valid"]:

                return {
                    "success": False,
                    "action": action,
                    "status": "ERROR",
                    "filled": 0.0,
                    "price": 0.0,
                    "position": self.current_position,
                    "error": (
                        "El contrato FDXM LIVE "
                        "no supera la validacion."
                    )
                }

            contract = (
                self.create_contract()
            )

            order = (
                self.create_market_order(
                    action
                )
            )

            order_id = (
                self.next_order_id
            )

            self.current_order_id = (
                order_id
            )

            # ------------------------------------------------
            # Reset completo
            # ------------------------------------------------

            self.order_event.clear()

            self.order_status = None
            self.order_filled = 0.0
            self.order_remaining = float(
                QUANTITY
            )
            self.order_avg_fill_price = 0.0

            self.error_message = None
            self.error_code = None

            # ------------------------------------------------
            # Mostrar operacion
            # ------------------------------------------------

            print()
            print(
                "========================================"
            )
            print(
                "ENVIANDO ORDEN LIVE"
            )
            print(
                f"Posición inicial: {initial_position}"
            )
            print(
                f"Accion:     {action}"
            )
            print(
                f"Cantidad:   {QUANTITY}"
            )
            print(
                "Tipo:       MKT"
            )
            print(
                f"Order ID:   {order_id}"
            )
            print(
                "========================================"
            )

            # ------------------------------------------------
            # ESTE ES EL UNICO PUNTO DONDE SE ENVIA LA ORDEN
            # ------------------------------------------------

            self.placeOrder(
                order_id,
                contract,
                order
            )

            # El siguiente Order ID es propiedad del
            # cliente despues de aceptar la orden.

            self.next_order_id += 1

            # ------------------------------------------------
            # Esperar resultado
            # ------------------------------------------------

            finished = (
                self.order_event.wait(
                    timeout=ORDER_TIMEOUT
                )
            )

            # ------------------------------------------------
            # TIMEOUT
            # ------------------------------------------------

            if not finished:

                print()
                print(
                    "TIMEOUT: no se confirmo "
                    "la ejecucion LIVE."
                )

                return {
                    "success": False,
                    "action": action,
                    "status": "TIMEOUT",
                    "filled": self.order_filled,
                    "price": self.order_avg_fill_price,
                    "position": self.current_position,
                    "error": (
                        f"No se recibio confirmacion "
                        f"en {ORDER_TIMEOUT} segundos."
                    ),
                    "order_id": order_id
                }

            # ------------------------------------------------
            # ERROR
            # ------------------------------------------------

            if self.order_status == "ERROR":

                return {
                    "success": False,
                    "action": action,
                    "status": "ERROR",
                    "filled": self.order_filled,
                    "price": self.order_avg_fill_price,
                    "position": self.current_position,
                    "error":
                        self.error_message,
                    "error_code":
                        self.error_code,
                    "order_id":
                        order_id
                }

            # ------------------------------------------------
            # FILLED
            # ------------------------------------------------

            if self.order_status == "Filled":

                expected_position = (
                    initial_position
                    + self.order_filled
                    if action == "BUY"
                    else
                    initial_position
                    - self.order_filled
                )

                position_ok = (
                    self.wait_for_position(
                        expected_position,
                        timeout=POSITION_TIMEOUT
                    )
                )

                final_position = (
                    self.current_position
                )

                if not position_ok:

                    return {
                        "success": False,
                        "action": action,
                        "status": "POSITION_MISMATCH",
                        "filled":
                            self.order_filled,
                        "price":
                            self.order_avg_fill_price,
                        "position":
                            final_position,
                        "expected_position":
                            expected_position,
                        "error": (
                            "La orden aparece Filled, "
                            "pero la posicion LIVE "
                            "no coincide con la esperada."
                        ),
                        "order_id":
                            order_id
                    }

                if (
                    self.order_filled
                    != QUANTITY
                ):

                    return {
                        "success": False,
                        "action": action,
                        "status": "PARTIAL",
                        "filled":
                            self.order_filled,
                        "price":
                            self.order_avg_fill_price,
                        "position":
                            final_position,
                        "expected_position":
                            expected_position,
                        "error": (
                            "La orden no se ejecuto "
                            "completamente."
                        ),
                        "order_id":
                            order_id
                    }

                return {
                    "success": True,
                    "action": action,
                    "status": "Filled",
                    "filled":
                        self.order_filled,
                    "price":
                        self.order_avg_fill_price,
                    "position":
                        final_position,
                    "expected_position":
                        expected_position,
                    "order_id":
                        order_id
                }

            # ------------------------------------------------
            # OTROS ESTADOS
            # ------------------------------------------------

            return {
                "success": False,
                "action": action,
                "status":
                    self.order_status,
                "filled":
                    self.order_filled,
                "price":
                    self.order_avg_fill_price,
                "position":
                    self.current_position,
                "error": (
                    f"Estado final: "
                    f"{self.order_status}"
                ),
                "order_id":
                    order_id
            }

    # ========================================================
    # ORDER STATUS
    # ========================================================

    def orderStatus(
        self,
        orderId,
        status,
        filled,
        remaining,
        avgFillPrice,
        permId,
        parentId,
        lastFillPrice,
        clientId,
        whyHeld,
        mktCapPrice
    ):

        if (
            self.current_order_id
            is None
        ):

            return

        if (
            int(orderId)
            != int(self.current_order_id)
        ):

            return

        self.order_status = (
            status
        )

        self.order_filled = (
            float(filled)
        )

        self.order_remaining = (
            float(remaining)
        )

        self.order_avg_fill_price = (
            float(avgFillPrice)
        )

        print(
            f"Orden {orderId} | "
            f"Estado: {status} | "
            f"Ejecutado: {filled} | "
            f"Restante: {remaining}"
        )

        if status in (
            "Filled",
            "Cancelled",
            "ApiCancelled",
            "Inactive"
        ):

            self.order_event.set()

    # ========================================================
    # OPEN LONG
    # ========================================================

    def open_long(
        self
    ):

        position = (
            self.get_position()
        )

        print()
        print(
            f"Posicion actual: "
            f"{position} contratos"
        )

        if position != 0:

            return {
                "success": False,
                "action": "ABRIR_LARGO",
                "status": "BLOCKED",
                "filled": 0.0,
                "price": 0.0,
                "position":
                    position,
                "error": (
                    "Ya existe una posicion abierta."
                )
            }

        result = self.send_order(
            "BUY"
        )

        if result["success"]:

            result["signal_action"] = (
                "ABRIR_LARGO"
            )

        return result

    # ========================================================
    # OPEN SHORT
    # ========================================================

    def open_short(
        self
    ):

        position = (
            self.get_position()
        )

        print()
        print(
            f"Posicion actual: "
            f"{position} contratos"
        )

        if position != 0:

            return {
                "success": False,
                "action": "ABRIR_CORTO",
                "status": "BLOCKED",
                "filled": 0.0,
                "price": 0.0,
                "position":
                    position,
                "error": (
                    "Ya existe una posicion abierta."
                )
            }

        result = self.send_order(
            "SELL"
        )

        if result["success"]:

            result["signal_action"] = (
                "ABRIR_CORTO"
            )

        return result

    # ========================================================
    # CLOSE POSITION
    # ========================================================

    def close_position(
        self
    ):

        position = (
            self.get_position()
        )

        print()
        print(
            f"Posicion actual: "
            f"{position} contratos"
        )

        if position == 0:

            return {
                "success": False,
                "action":
                    "CERRAR_POSICION",
                "status": "BLOCKED",
                "filled": 0.0,
                "price": 0.0,
                "position": 0.0,
                "error": (
                    "No existe ninguna posicion."
                )
            }

        if position > 0:

            action = "SELL"
            signal_action = (
                "CERRAR_LARGO"
            )

        else:

            action = "BUY"
            signal_action = (
                "CERRAR_CORTO"
            )

        quantity = abs(
            position
        )

        if quantity != self.order_quantity:

            return {
                "success": False,
                "action":
                    signal_action,
                "status": "BLOCKED",
                "filled": 0.0,
                "price": 0.0,
                "position":
                    position,
                "error": (
                    "La posicion no es de "
                    "1 contrato."
                )
            }

        result = self.send_order(
            action
        )

        if result["success"]:

            result["signal_action"] = (
                signal_action
            )

        return result

    # ========================================================
    # ALIASES COMPATIBILIDAD
    # ========================================================

    def open_long_position(
        self
    ):

        return self.open_long()

    def open_short_position(
        self
    ):

        return self.open_short()

    def close_current_position(
        self
    ):

        return self.close_position()

    # ========================================================
    # RECONCILIACION DE ORDEN
    # ========================================================
    #
    # Mantiene la interfaz necesaria para el motor de estado.
    #
    # IMPORTANTE:
    # No modifica ninguna posicion y no envia ninguna orden.
    #
    # Para una orden concreta consulta open orders + executions
    # y devuelve la informacion que el motor necesita.
    # ========================================================

    def openOrder(
        self,
        orderId,
        contract,
        order,
        orderState
    ):

        if (
            int(orderId)
            not in self.reconciliation_orders
        ):

            self.reconciliation_orders[
                int(orderId)
            ] = {
                "order_id":
                    int(orderId),
                "status":
                    "OPEN",
                "filled":
                    0.0,
                "price":
                    0.0
            }

        self.reconciliation_orders[
            int(orderId)
        ]["contract"] = {
            "con_id":
                getattr(
                    contract,
                    "conId",
                    0
                ),
            "symbol":
                getattr(
                    contract,
                    "symbol",
                    ""
                ),
            "exchange":
                getattr(
                    contract,
                    "exchange",
                    ""
                )
        }

        self.reconciliation_orders[
            int(orderId)
        ]["status"] = (
            getattr(
                orderState,
                "status",
                None
            )
            or "OPEN"
        )

    def openOrderEnd(
        self
    ):

        self.reconciliation_event.set()

    def execDetails(
        self,
        reqId,
        contract,
        execution
    ):

        order_id = int(
            execution.orderId
        )

        if order_id not in (
            self.reconciliation_orders
        ):

            self.reconciliation_orders[
                order_id
            ] = {
                "order_id":
                    order_id,
                "status":
                    "Filled",
                "filled":
                    0.0,
                "price":
                    0.0
            }

        record = (
            self.reconciliation_orders[
                order_id
            ]
        )

        previous_filled = float(
            record.get(
                "filled",
                0.0
            )
            or 0.0
        )

        previous_price = float(
            record.get(
                "price",
                0.0
            )
            or 0.0
        )

        execution_shares = float(
            getattr(
                execution,
                "shares",
                0.0
            )
            or 0.0
        )

        execution_price = float(
            getattr(
                execution,
                "price",
                0.0
            )
            or 0.0
        )

        new_filled = (
            previous_filled
            + execution_shares
        )

        if new_filled > 0:

            weighted_price = (
                (
                    previous_price
                    * previous_filled
                )
                + (
                    execution_price
                    * execution_shares
                )
            ) / new_filled

        else:

            weighted_price = 0.0

        record["filled"] = (
            new_filled
        )

        record["price"] = (
            weighted_price
        )

        record["status"] = "Filled"

    def reconcile_order(
        self,
        order_id,
        timeout=5
    ):

        order_id = int(
            order_id
        )

        self.reconciliation_orders = {}

        self.reconciliation_event.clear()

        try:

            self.reqOpenOrders()

        except Exception as error:

            return {
                "found": False,
                "source": "ERROR",
                "status": "ERROR",
                "filled": 0.0,
                "price": 0.0,
                "order_id": order_id,
                "error": str(error)
            }

        self.reconciliation_event.wait(
            timeout=timeout
        )

        record = (
            self.reconciliation_orders.get(
                order_id
            )
        )

        if record is not None:

            return {
                "found": True,
                "source": "OPEN",
                "status":
                    record.get(
                        "status",
                        "OPEN"
                    ),
                "filled":
                    record.get(
                        "filled",
                        0.0
                    ),
                "price":
                    record.get(
                        "price",
                        0.0
                    ),
                "order_id":
                    order_id
            }

        # ----------------------------------------------------
        # Si no aparece como open, consultamos executions
        # mediante reqExecutions.
        # ----------------------------------------------------

        self.reconciliation_orders = {}
        self.reconciliation_event.clear()

        try:

            from ibapi.execution import ExecutionFilter

            execution_filter = (
                ExecutionFilter()
            )

            self.reqExecutions(
                9001,
                execution_filter
            )

            # executionDetailsEnd usa el mismo event.
            self.reconciliation_event.wait(
                timeout=timeout
            )

            try:

                self.cancelOrder(
                    9001
                )

            except Exception:

                pass

        except Exception as error:

            return {
                "found": False,
                "source": "UNKNOWN",
                "status": "UNKNOWN",
                "filled": 0.0,
                "price": 0.0,
                "order_id": order_id,
                "error": str(error)
            }

        record = (
            self.reconciliation_orders.get(
                order_id
            )
        )

        if record is None:

            return {
                "found": False,
                "source": "UNKNOWN",
                "status": "UNKNOWN",
                "filled": 0.0,
                "price": 0.0,
                "order_id": order_id
            }

        return {
            "found": True,
            "source": "EXECUTION",
            "status":
                record.get(
                    "status",
                    "Filled"
                ),
            "filled":
                record.get(
                    "filled",
                    0.0
                ),
            "price":
                record.get(
                    "price",
                    0.0
                ),
            "order_id":
                order_id
        }

    def executionDetailsEnd(
        self,
        reqId
    ):

        self.reconciliation_event.set()

    # ========================================================
    # CONECTAR LIVE + VALIDACION
    # ========================================================

    def connect_live(
        self,
        timeout=10
    ):

        print()
        print(
            "========================================"
        )
        print(
            "      DAX BOT - VALIDACION LIVE"
        )
        print(
            "========================================"
        )

        print(
            "*** NO SE ENVIARAN ORDENES "
            "EN ESTA FASE ***"
        )

        print(
            f"Host: {HOST}"
        )

        print(
            f"Puerto LIVE: {PORT}"
        )

        print(
            f"Client ID: {CLIENT_ID}"
        )

        print(
            f"FDXM conId: {CON_ID}"
        )

        print(
            f"Exchange: {EXCHANGE}"
        )

        print(
            "========================================"
        )

        if PORT != 4001:

            raise RuntimeError(
                "Bloqueo de seguridad: "
                "LiveExecutor solo admite "
                "el puerto LIVE 4001."
            )

        self.connect(
            HOST,
            PORT,
            CLIENT_ID
        )

        api_thread = threading.Thread(
            target=self.run,
            daemon=True
        )

        self.api_thread = (
            api_thread
        )

        api_thread.start()

        if not self.connection_ready.wait(
            timeout=timeout
        ):

            try:
                self.disconnect()
            except Exception:
                pass

            raise RuntimeError(
                "No se recibio nextValidId "
                "desde IB Gateway LIVE."
            )

        if not self.positions_ready.wait(
            timeout=timeout
        ):

            try:
                self.disconnect()
            except Exception:
                pass

            raise RuntimeError(
                "No se recibieron las posiciones "
                "iniciales LIVE."
            )

        snapshot = (
            self.readiness_snapshot()
        )

        if not snapshot["connected"]:

            self.disconnect()

            raise RuntimeError(
                "IBKR LIVE no figura conectado."
            )

        if not snapshot["positions_ready"]:

            self.disconnect()

            raise RuntimeError(
                "Las posiciones LIVE no estan preparadas."
            )

        if not snapshot[
            "contract"
        ]["valid"]:

            self.disconnect()

            raise RuntimeError(
                "La configuracion del contrato "
                "FDXM no es valida."
            )

        print()
        print(
            "========================================"
        )
        print(
            "VALIDACION LIVE COMPLETADA"
        )
        print(
            "========================================"
        )

        print(
            f"Cuenta: "
            f"{snapshot['account_id'] or 'N/D'}"
        )

        print(
            f"FDXM: "
            f"{snapshot['position']}"
        )

        print(
            f"Precio medio: "
            f"{snapshot['avg_cost']}"
        )

        print(
            f"Contrato: "
            f"{snapshot['contract']}"
        )

        print(
            "ORDENES LIVE: DESHABILITADAS"
        )

        print(
            "========================================"
        )

        return snapshot


# ============================================================
# FUNCIONES COMPATIBLES CON PAPER_EXECUTOR
# ============================================================

def open_long(
    app
):

    return app.open_long()


def open_short(
    app
):

    return app.open_short()


def close_position(
    app
):

    return app.close_position()


# ============================================================
# PRUEBA DIRECTA
# ============================================================

def main():

    app = (
        LiveExecutor()
    )

    try:

        snapshot = (
            app.connect_live()
        )

        print()
        print(
            "SNAPSHOT LIVE:"
        )

        print(
            snapshot
        )

        print()
        print(
            "VALIDACION FINAL: OK"
        )

        return 0

    except Exception as error:

        print()
        print(
            "========================================"
        )

        print(
            "VALIDACION LIVE FALLIDA"
        )

        print(
            "========================================"
        )

        print(
            f"{type(error).__name__}: "
            f"{error}"
        )

        return 1

    finally:

        try:

            if app.isConnected():

                app.disconnect()

                print()
                print(
                    "Conexion LIVE cerrada."
                )

        except Exception:

            pass


# ============================================================
# INICIO
# ============================================================

if __name__ == "__main__":

    raise SystemExit(
        main()
    )
