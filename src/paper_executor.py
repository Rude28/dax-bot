import threading

from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order
from ibapi.execution import ExecutionFilter

from logger import (
    log_info,
    log_warning,
    log_error,
)

from bot_state import (
    bot_state,
    CONNECTED,
    RECONNECTING_IBKR,
    SAFETY_LOCK,
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

HOST = "127.0.0.1"
PORT = 4002
CLIENT_ID = 4

# FDXM SEP26
CON_ID = 655095900
EXCHANGE = "EUREX"

# MVP
QUANTITY = 1


# ============================================================
# ESTADOS TERMINALES DE ORDEN
# ============================================================

TERMINAL_ORDER_STATUSES = (
    "Filled",
    "Cancelled",
    "ApiCancelled",
    "Inactive"
)


# ============================================================
# APLICACIÓN IBKR
# ============================================================

class PaperExecutor(EWrapper, EClient):

    def __init__(self):

        EClient.__init__(
            self,
            self
        )

        # ====================================================
        # CONEXIÓN
        # ====================================================

        self.next_order_id = None

        self.connection_ready = (
            threading.Event()
        )

        self.connection_lost = (
            threading.Event()
        )

        self.api_thread = None

        # ====================================================
        # POSICIÓN
        # ====================================================

        self.current_position = 0.0
        self.position_avg_cost = 0.0

        self.positions_ready = (
            threading.Event()
        )

        self.position_update_event = (
            threading.Event()
        )

        # ====================================================
        # ORDEN ACTUAL
        # ====================================================

        self.current_order_id = None

        self.order_event = (
            threading.Event()
        )

        self.order_status = None
        self.order_filled = 0.0
        self.order_remaining = 0.0
        self.order_avg_fill_price = 0.0

        self.error_message = None
        self.error_code = None

        # ====================================================
        # PROTECCIÓN CONTRA ÓRDENES SIMULTÁNEAS
        # ====================================================

        self.order_lock = (
            threading.Lock()
        )

        # ====================================================
        # RECONCILIACIÓN
        # ====================================================

        self.open_orders = {}

        self.open_orders_event = (
            threading.Event()
        )

        self.completed_orders = {}

        self.completed_orders_event = (
            threading.Event()
        )

        self.executions = {}

        self.execution_request_id = 9000

        self.executions_event = (
            threading.Event()
        )

        # ====================================================
        # CUENTA IBKR
        # ====================================================

        self.account_summary = {}

        self.account_summary_event = (
            threading.Event()
        )

        self.account_request_id = 10000

        self.account_summary_currency = None

    # ========================================================
    # CONEXIÓN
    # ========================================================

    def nextValidId(
        self,
        orderId
    ):

        self.next_order_id = (
            int(orderId)
        )

        self.connection_lost.clear()
        self.connection_ready.set()

        bot_state.set_ibkr_connected(True)
        bot_state.set_status(CONNECTED)

        print()
        print(
            "========================================"
        )

        print(
            "CONEXIÓN CON IBKR CORRECTA"
        )

        print(
            f"Next Order ID: {orderId}"
        )

        print(
            "========================================"
        )

        log_info(
            f"Conexión IBKR correcta | "
            f"Next Order ID={orderId}"
        )

        # ----------------------------------------------------
        # Solicitar posiciones iniciales.
        # ----------------------------------------------------

        self.current_position = 0.0
        self.position_avg_cost = 0.0

        self.positions_ready.clear()

        print(
            "Solicitando posiciones iniciales..."
        )

        log_info(
            "Solicitando posiciones iniciales a IBKR."
        )

        self.reqPositions()

    # ========================================================
    # DESCONEXIÓN
    # ========================================================

    def connectionClosed(self):
        """
        Callback de IBKR cuando la conexión se cierra.

        Esta función NO intenta reconectar.
        El coordinador (bot_auto.py) será responsable de la
        reconexión y de la reconciliación de cualquier orden
        que pudiera estar en PROCESSING.
        """

        self.connection_lost.set()
        self.connection_ready.clear()

        bot_state.set_ibkr_connected(False)
        bot_state.set_status(RECONNECTING_IBKR)

        log_warning(
            "Conexión IBKR cerrada | "
            "El ejecutor queda bloqueado hasta reconexión."
        )

        print()
        print(
            "IBKR DESCONECTADO."
        )

        print(
            "Nuevas órdenes bloqueadas hasta reconexión."
        )

        try:
            super().connectionClosed()
        except Exception:
            pass

    def is_trading_connection_ready(self):
        """
        Devuelve True únicamente si la conexión IBKR está
        disponible y no se ha detectado una desconexión.
        """

        try:
            api_connected = bool(
                self.isConnected()
            )
        except Exception:
            api_connected = False

        return (
            api_connected
            and not self.connection_lost.is_set()
            and self.connection_ready.is_set()
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

        # ----------------------------------------------------
        # Eventos de conectividad.
        # ----------------------------------------------------

        if errorCode in (
            1100,
            1300
        ):

            self.connection_lost.set()
            self.connection_ready.clear()

            bot_state.set_ibkr_connected(False)
            bot_state.set_status(RECONNECTING_IBKR)

            log_warning(
                f"IBKR conectividad perdida | "
                f"code={errorCode} | {errorString}"
            )

            print()
            print(
                "IBKR CONEXIÓN NO DISPONIBLE."
            )

            return

        if errorCode in (
            1101,
            1102
        ):

            log_info(
                f"IBKR conectividad restaurada | "
                f"code={errorCode} | {errorString}"
            )

            bot_state.set_ibkr_connected(True)

            return

        # ----------------------------------------------------
        # Mensajes informativos normales de IBKR.
        # ----------------------------------------------------

        if errorCode in (
            2104,
            2106,
            2107,
            2158
        ):

            print(
                f"IBKR INFO | code={errorCode} | "
                f"{errorString}"
            )

            log_info(
                f"IBKR INFO | reqId={reqId} | "
                f"code={errorCode} | "
                f"{errorString}"
            )

            return

        # ----------------------------------------------------
        # Error.
        # ----------------------------------------------------

        print(
            f"IBKR ERROR | reqId={reqId} | "
            f"code={errorCode} | "
            f"message={errorString}"
        )

        log_error(
            f"IBKR ERROR | reqId={reqId} | "
            f"code={errorCode} | "
            f"message={errorString}"
        )

        self.error_message = (
            errorString
        )

        self.error_code = (
            errorCode
        )

        # ----------------------------------------------------
        # Si corresponde a la orden actual.
        # ----------------------------------------------------

        if (
            self.current_order_id is not None
            and reqId == self.current_order_id
        ):

            self.order_status = (
                "ERROR"
            )

            self.order_event.set()

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

        if contract.conId != CON_ID:
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
            "ACTUALIZACIÓN DE POSICIÓN"
        )

        print(
            f"FDXM:          "
            f"{self.current_position}"
        )

        print(
            f"Precio medio:  "
            f"{self.position_avg_cost}"
        )

        print(
            "----------------------------------------"
        )

        log_info(
            f"Posición FDXM actualizada | "
            f"Position={self.current_position} | "
            f"AvgCost={self.position_avg_cost}"
        )

        self.position_update_event.set()

    def positionEnd(self):

        print()
        print(
            "Posiciones iniciales recibidas."
        )

        log_info(
            "Posiciones iniciales recibidas."
        )

        self.positions_ready.set()

    # ========================================================
    # POSICIÓN
    # ========================================================

    def get_position(self):

        return self.current_position

    # ========================================================
    # CONTRATO
    # ========================================================

    def create_contract(self):

        contract = Contract()

        contract.conId = CON_ID
        contract.exchange = EXCHANGE

        return contract

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
    # ESTADO DE ORDEN
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

        # ----------------------------------------------------
        # Ignorar órdenes que no sean la actual cuando estamos
        # esperando una respuesta activa.
        # ----------------------------------------------------

        if orderId != self.current_order_id:
            return

        self.order_status = status

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

        log_info(
            f"Estado orden | "
            f"OrderID={orderId} | "
            f"Status={status} | "
            f"Filled={filled} | "
            f"Remaining={remaining} | "
            f"AvgFillPrice={avgFillPrice}"
        )

        if status in (
            "Filled",
            "Cancelled",
            "ApiCancelled",
            "Inactive"
        ):

            self.order_event.set()

    # ========================================================
    # OPEN ORDERS
    # ========================================================

    def openOrder(
        self,
        orderId,
        contract,
        order,
        orderState
    ):

        self.open_orders[
            int(orderId)
        ] = {
            "contract": contract,
            "order": order,
            "order_state": orderState
        }

        print(
            f"IBKR OPEN ORDER | "
            f"Order ID: {orderId} | "
            f"Status: {orderState.status}"
        )

        log_info(
            f"IBKR OPEN ORDER | "
            f"OrderID={orderId} | "
            f"Status={orderState.status}"
        )

    def openOrderEnd(self):

        self.open_orders_event.set()

        log_info(
            "Fin de consulta de órdenes abiertas."
        )

    # ========================================================
    # COMPLETED ORDERS
    # ========================================================

    def completedOrder(
        self,
        contract,
        order,
        orderState
    ):

        order_id = getattr(
            order,
            "orderId",
            None
        )

        if order_id is None:
            return

        self.completed_orders[
            int(order_id)
        ] = {
            "contract": contract,
            "order": order,
            "order_state": orderState
        }

        print(
            f"IBKR COMPLETED ORDER | "
            f"Order ID: {order_id} | "
            f"Status: {orderState.status}"
        )

        log_info(
            f"IBKR COMPLETED ORDER | "
            f"OrderID={order_id} | "
            f"Status={orderState.status}"
        )

    def completedOrdersEnd(self):

        self.completed_orders_event.set()

        log_info(
            "Fin de consulta de órdenes completadas."
        )

    # ========================================================
    # EJECUCIONES
    # ========================================================

    def execDetails(
        self,
        reqId,
        contract,
        execution
    ):

        order_id = int(
            execution.orderId
        )

        if order_id not in self.executions:

            self.executions[
                order_id
            ] = []

        self.executions[
            order_id
        ].append(
            {
                "exec_id": execution.execId,
                "order_id": order_id,
                "shares": float(
                    execution.shares
                ),
                "price": float(
                    execution.price
                ),
                "side": execution.side,
                "time": execution.time,
                "perm_id": execution.permId,
                "client_id": execution.clientId
            }
        )

        print()
        print(
            "IBKR EXECUTION"
        )

        print(
            f"Order ID: {order_id}"
        )

        print(
            f"Shares:   {execution.shares}"
        )

        print(
            f"Price:    {execution.price}"
        )

        log_info(
            f"IBKR EXECUTION | "
            f"OrderID={order_id} | "
            f"ExecID={execution.execId} | "
            f"Shares={execution.shares} | "
            f"Price={execution.price} | "
            f"Side={execution.side}"
        )

    def execDetailsEnd(
        self,
        reqId
    ):

        if reqId == (
            self.execution_request_id
        ):

            self.executions_event.set()

            log_info(
                f"Fin de consulta de ejecuciones | "
                f"RequestID={reqId}"
            )

    # ========================================================
    # CUENTA IBKR
    # ========================================================

    def accountSummary(
        self,
        reqId,
        account,
        tag,
        value,
        currency
    ):
        """Recibe una fila del Account Summary de IBKR."""

        if reqId != self.account_request_id:
            return

        self.account_summary[tag] = {
            "value": value,
            "currency": currency,
            "account": account
        }

        if currency:
            self.account_summary_currency = currency

        log_info(
            f"IBKR ACCOUNT SUMMARY | "
            f"RequestID={reqId} | "
            f"Tag={tag} | "
            f"Value={value} | "
            f"Currency={currency}"
        )

    def accountSummaryEnd(
        self,
        reqId
    ):

        if reqId != self.account_request_id:
            return

        self.account_summary_event.set()

        log_info(
            f"Fin consulta ACCOUNT SUMMARY | "
            f"RequestID={reqId}"
        )

    def request_account_summary(
        self
    ):
        """Solicita datos de cuenta a IBKR sin modificar nada."""

        if not self.is_trading_connection_ready():

            log_warning(
                "No se puede solicitar ACCOUNT SUMMARY: "
                "IBKR no está conectado."
            )

            return None

        with self.order_lock:

            self.account_request_id += 1
            request_id = self.account_request_id

            self.account_summary = {}
            self.account_summary_currency = None
            self.account_summary_event.clear()

            tags = (
                "NetLiquidation,"
                "TotalCashValue,"
                "AvailableFunds,"
                "BuyingPower"
            )

            log_info(
                f"Solicitando ACCOUNT SUMMARY | "
                f"RequestID={request_id}"
            )

            try:

                self.reqAccountSummary(
                    request_id,
                    "All",
                    tags
                )

            except Exception as error:

                log_error(
                    f"Error solicitando ACCOUNT SUMMARY | "
                    f"RequestID={request_id} | "
                    f"{type(error).__name__}: {error}"
                )

                return None

            return request_id

    def get_account_summary(
        self,
        request_id,
        timeout=10
    ):
        """Espera y devuelve el Account Summary de IBKR."""

        if request_id != self.account_request_id:

            log_error(
                f"Request ID de ACCOUNT SUMMARY incorrecto | "
                f"Expected={self.account_request_id} | "
                f"Received={request_id}"
            )

            return {}

        completed = self.account_summary_event.wait(
            timeout=timeout
        )

        if not completed:

            log_error(
                f"TIMEOUT consultando ACCOUNT SUMMARY | "
                f"RequestID={request_id}"
            )

            try:
                self.cancelAccountSummary(request_id)
            except Exception as error:
                log_warning(
                    f"Error cancelando ACCOUNT SUMMARY | "
                    f"{type(error).__name__}: {error}"
                )

            return {}

        try:
            self.cancelAccountSummary(request_id)
        except Exception as error:
            log_warning(
                f"Error cancelando ACCOUNT SUMMARY | "
                f"{type(error).__name__}: {error}"
            )

        result = {}

        for tag, data in self.account_summary.items():

            value = data.get("value")

            if value in (None, "", "N/A"):
                result[tag] = None
            else:
                try:
                    result[tag] = float(value)
                except (TypeError, ValueError):
                    result[tag] = value

        if self.account_summary_currency:
            result["Currency"] = self.account_summary_currency
        else:
            for data in self.account_summary.values():
                currency = data.get("currency")
                if currency:
                    result["Currency"] = currency
                    break

        log_info(
            f"ACCOUNT SUMMARY recibido | "
            f"RequestID={request_id} | "
            f"Datos={result}"
        )

        return result

    # ========================================================
    # ESPERAR POSICIÓN
    # ========================================================

    def wait_for_position(
        self,
        expected_position,
        timeout=5
    ):
        """
        Espera hasta que la posición real coincida con
        la esperada.
        """

        if self.current_position == (
            expected_position
        ):

            return True

        self.position_update_event.clear()

        updated = (
            self.position_update_event.wait(
                timeout=timeout
            )
        )

        if not updated:

            return (
                self.current_position
                == expected_position
            )

        return (
            self.current_position
            == expected_position
        )

    # ========================================================
    # ENVIAR ORDEN
    # ========================================================

    def send_order(
        self,
        action
    ):
        """
        Envía una orden MKT.

        La posición inicial se captura antes de enviar
        la orden para calcular correctamente la posición
        esperada.
        """

        if not self.is_trading_connection_ready():

            log_warning(
                f"Orden bloqueada por desconexión IBKR | "
                f"Action={action} | "
                f"Position={self.current_position}"
            )

            return {
                "success": False,
                "action": action,
                "status": "IBKR_DISCONNECTED",
                "filled": 0.0,
                "price": 0.0,
                "position": self.current_position,
                "error": (
                    "IBKR no está conectado. "
                    "La orden no se ha enviado."
                )
            }

        log_info(
            f"Solicitud de orden | "
            f"Action={action} | "
            f"CurrentPosition={self.current_position}"
        )

        with self.order_lock:

            return self._send_order_locked(
                action
            )

    # ========================================================
    # ENVÍO INTERNO
    # ========================================================

    def _send_order_locked(
        self,
        action
    ):

        if not self.is_trading_connection_ready():

            log_warning(
                f"Orden cancelada antes de placeOrder por desconexión | "
                f"Action={action}"
            )

            return {
                "success": False,
                "action": action,
                "status": "IBKR_DISCONNECTED",
                "filled": 0.0,
                "price": 0.0,
                "position": self.current_position,
                "error": (
                    "IBKR se desconectó antes de enviar la orden."
                )
            }

        # ----------------------------------------------------
        # Comprobar Order ID.
        # ----------------------------------------------------

        if self.next_order_id is None:

            log_error(
                "No existe Order ID disponible."
            )

            return {
                "success": False,
                "action": action,
                "status": "ERROR",
                "filled": 0.0,
                "price": 0.0,
                "position": (
                    self.current_position
                ),
                "error": (
                    "No existe Order ID."
                )
            }

        # ----------------------------------------------------
        # Posición inicial.
        # ----------------------------------------------------

        initial_position = (
            self.current_position
        )

        # ----------------------------------------------------
        # Posición esperada.
        # ----------------------------------------------------

        if action == "BUY":

            expected_position = (
                initial_position
                + QUANTITY
            )

        elif action == "SELL":

            expected_position = (
                initial_position
                - QUANTITY
            )

        else:

            log_error(
                f"Acción no válida: {action}"
            )

            return {
                "success": False,
                "action": action,
                "status": "ERROR",
                "filled": 0.0,
                "price": 0.0,
                "position": initial_position,
                "error": (
                    f"Acción no válida: {action}"
                )
            }

        # ----------------------------------------------------
        # Preparar contrato y orden.
        # ----------------------------------------------------

        contract = (
            self.create_contract()
        )

        order = (
            self.create_market_order(
                action
            )
        )

        order_id = (
            int(self.next_order_id)
        )

        self.current_order_id = (
            order_id
        )

        # ----------------------------------------------------
        # Reset estado.
        # ----------------------------------------------------

        self.order_event.clear()

        self.position_update_event.clear()

        self.order_status = None

        self.order_filled = 0.0

        self.order_remaining = (
            float(QUANTITY)
        )

        self.order_avg_fill_price = 0.0

        self.error_message = None
        self.error_code = None

        # ----------------------------------------------------
        # Mostrar.
        # ----------------------------------------------------

        print()
        print(
            "========================================"
        )

        print(
            "ENVIANDO ORDEN"
        )

        print(
            f"Acción:           {action}"
        )

        print(
            f"Cantidad:         {QUANTITY}"
        )

        print(
            "Tipo:             MKT"
        )

        print(
            f"Order ID:         {order_id}"
        )

        print(
            f"Posición inicial: "
            f"{initial_position}"
        )

        print(
            f"Posición esperada: "
            f"{expected_position}"
        )

        print(
            "========================================"
        )

        log_info(
            f"Enviando orden | "
            f"OrderID={order_id} | "
            f"Action={action} | "
            f"Quantity={QUANTITY} | "
            f"InitialPosition={initial_position} | "
            f"ExpectedPosition={expected_position}"
        )

        # ----------------------------------------------------
        # ENVIAR
        # ----------------------------------------------------

        if not self.is_trading_connection_ready():

            log_warning(
                f"Orden no enviada: conexión perdida justo antes de placeOrder | "
                f"OrderID={order_id} | Action={action}"
            )

            return {
                "success": False,
                "action": action,
                "status": "IBKR_DISCONNECTED",
                "filled": 0.0,
                "price": 0.0,
                "position": self.current_position,
                "expected_position": expected_position,
                "order_id": order_id,
                "error": (
                    "IBKR se desconectó antes de enviar la orden."
                )
            }

        self.placeOrder(
            order_id,
            contract,
            order
        )

        self.next_order_id = (
            order_id + 1
        )

        # ----------------------------------------------------
        # Esperar respuesta.
        # ----------------------------------------------------

        finished = (
            self.order_event.wait(
                timeout=30
            )
        )

        # ----------------------------------------------------
        # TIMEOUT
        # ----------------------------------------------------

        if not finished:

            print()
            print(
                "TIMEOUT: no se confirmó "
                "la ejecución."
            )

            log_error(
                f"TIMEOUT de orden | "
                f"OrderID={order_id} | "
                f"Action={action} | "
                f"Filled={self.order_filled}"
            )

            return {
                "success": False,
                "action": action,
                "status": "TIMEOUT",
                "filled": (
                    self.order_filled
                ),
                "price": (
                    self.order_avg_fill_price
                ),
                "position": (
                    self.current_position
                ),
                "expected_position": (
                    expected_position
                ),
                "order_id": order_id,
                "error": (
                    "No se recibió confirmación "
                    "de la orden en 30 segundos."
                )
            }

        # ----------------------------------------------------
        # ERROR
        # ----------------------------------------------------

        if self.order_status == "ERROR":

            log_error(
                f"Orden con error | "
                f"OrderID={order_id} | "
                f"Action={action} | "
                f"ErrorCode={self.error_code} | "
                f"Error={self.error_message}"
            )

            return {
                "success": False,
                "action": action,
                "status": "ERROR",
                "filled": (
                    self.order_filled
                ),
                "price": (
                    self.order_avg_fill_price
                ),
                "position": (
                    self.current_position
                ),
                "expected_position": (
                    expected_position
                ),
                "order_id": order_id,
                "error": (
                    self.error_message
                ),
                "error_code": (
                    self.error_code
                )
            }

        # ----------------------------------------------------
        # FILLED
        # ----------------------------------------------------

        if self.order_status == "Filled":

            print()
            print(
                "========================================"
            )

            print(
                "ORDEN FILLED"
            )

            print(
                f"Order ID:     {order_id}"
            )

            print(
                f"Acción:       {action}"
            )

            print(
                f"Cantidad:     "
                f"{self.order_filled}"
            )

            print(
                f"Precio medio: "
                f"{self.order_avg_fill_price}"
            )

            print(
                "========================================"
            )

            log_info(
                f"Orden FILLED | "
                f"OrderID={order_id} | "
                f"Action={action} | "
                f"Filled={self.order_filled} | "
                f"Price={self.order_avg_fill_price}"
            )

            # ------------------------------------------------
            # Cantidad completa.
            # ------------------------------------------------

            if self.order_filled != float(
                QUANTITY
            ):

                log_warning(
                    f"Ejecución parcial | "
                    f"OrderID={order_id} | "
                    f"Filled={self.order_filled} | "
                    f"Expected={QUANTITY}"
                )

                return {
                    "success": False,
                    "action": action,
                    "status": "PARTIAL",
                    "filled": (
                        self.order_filled
                    ),
                    "price": (
                        self.order_avg_fill_price
                    ),
                    "position": (
                        self.current_position
                    ),
                    "expected_position": (
                        expected_position
                    ),
                    "order_id": order_id,
                    "error": (
                        "Cantidad ejecutada incompleta."
                    )
                }

            # ------------------------------------------------
            # Posición final.
            # ------------------------------------------------

            position_confirmed = (
                self.wait_for_position(
                    expected_position,
                    timeout=5
                )
            )

            if not position_confirmed:

                print()
                print(
                    "POSITION_MISMATCH"
                )

                print(
                    f"Esperada: "
                    f"{expected_position}"
                )

                print(
                    f"Real: "
                    f"{self.current_position}"
                )

                log_error(
                    f"POSITION_MISMATCH | "
                    f"OrderID={order_id} | "
                    f"Expected={expected_position} | "
                    f"Actual={self.current_position}"
                )

                return {
                    "success": False,
                    "action": action,
                    "status": (
                        "POSITION_MISMATCH"
                    ),
                    "filled": (
                        self.order_filled
                    ),
                    "price": (
                        self.order_avg_fill_price
                    ),
                    "position": (
                        self.current_position
                    ),
                    "expected_position": (
                        expected_position
                    ),
                    "order_id": order_id,
                    "error": (
                        "La orden fue Filled pero "
                        "la posición real no coincide."
                    )
                }

            # ------------------------------------------------
            # ÉXITO
            # ------------------------------------------------

            log_info(
                f"Orden completada correctamente | "
                f"OrderID={order_id} | "
                f"Action={action} | "
                f"Price={self.order_avg_fill_price} | "
                f"Position={self.current_position}"
            )

            return {
                "success": True,
                "action": action,
                "status": "Filled",
                "filled": (
                    self.order_filled
                ),
                "price": (
                    self.order_avg_fill_price
                ),
                "position": (
                    self.current_position
                ),
                "expected_position": (
                    expected_position
                ),
                "order_id": order_id
            }

        # ----------------------------------------------------
        # OTROS ESTADOS
        # ----------------------------------------------------

        log_warning(
            f"Orden terminó en estado no esperado | "
            f"OrderID={order_id} | "
            f"Status={self.order_status} | "
            f"Filled={self.order_filled}"
        )

        return {
            "success": False,
            "action": action,
            "status": self.order_status,
            "filled": (
                self.order_filled
            ),
            "price": (
                self.order_avg_fill_price
            ),
            "position": (
                self.current_position
            ),
            "expected_position": (
                expected_position
            ),
            "order_id": order_id,
            "error": (
                f"Estado final: "
                f"{self.order_status}"
            )
        }

    # ========================================================
    # RECONCILIAR ORDEN
    # ========================================================

    def reconcile_order(
        self,
        order_id,
        timeout=10
    ):
        """
        Consulta una orden existente sin modificarla.

        Busca:
            1. órdenes abiertas;
            2. órdenes completadas;
            3. ejecuciones.

        IMPORTANTE:

        UNKNOWN NO significa "no ejecutada".
        Significa que no tenemos evidencia suficiente.
        """

        order_id = int(
            order_id
        )

        if not self.is_trading_connection_ready():

            log_warning(
                f"No se puede reconciliar OrderID={order_id}: "
                "IBKR no está conectado."
            )

            return {
                "found": False,
                "source": None,
                "order_id": order_id,
                "status": "IBKR_DISCONNECTED",
                "filled": 0.0,
                "price": 0.0,
                "executions": [],
                "action": None,
                "total_quantity": None,
                "error": (
                    "No se puede reconciliar sin conexión IBKR."
                )
            }

        print()
        print(
            "========================================"
        )

        print(
            "RECONCILIANDO ORDEN"
        )

        print(
            f"Order ID: {order_id}"
        )

        print(
            "========================================"
        )

        log_info(
            f"Iniciando reconciliación | "
            f"OrderID={order_id}"
        )

        # ----------------------------------------------------
        # Limpiar resultados.
        # ----------------------------------------------------

        self.open_orders = {}

        self.completed_orders = {}

        self.executions = {}

        self.open_orders_event.clear()

        self.completed_orders_event.clear()

        self.executions_event.clear()

        # ====================================================
        # 1. OPEN ORDERS
        # ====================================================

        print(
            "Consultando órdenes abiertas..."
        )

        log_info(
            f"Consultando órdenes abiertas | "
            f"OrderID={order_id}"
        )

        self.reqOpenOrders()

        if not self.open_orders_event.wait(
            timeout=timeout
        ):

            print(
                "TIMEOUT consultando "
                "órdenes abiertas."
            )

            log_warning(
                "TIMEOUT consultando órdenes abiertas."
            )

        open_order = (
            self.open_orders.get(
                order_id
            )
        )

        # ====================================================
        # 2. COMPLETED ORDERS
        # ====================================================

        print(
            "Consultando órdenes completadas..."
        )

        log_info(
            f"Consultando órdenes completadas | "
            f"OrderID={order_id}"
        )

        self.reqCompletedOrders(
            True
        )

        if not self.completed_orders_event.wait(
            timeout=timeout
        ):

            print(
                "TIMEOUT consultando "
                "órdenes completadas."
            )

            log_warning(
                "TIMEOUT consultando órdenes completadas."
            )

        completed_order = (
            self.completed_orders.get(
                order_id
            )
        )

        # ====================================================
        # 3. EJECUCIONES
        # ====================================================

        self.execution_request_id += 1

        execution_req_id = (
            self.execution_request_id
        )

        self.executions_event.clear()

        print(
            "Consultando ejecuciones..."
        )

        log_info(
            f"Consultando ejecuciones | "
            f"RequestID={execution_req_id} | "
            f"OrderID={order_id}"
        )

        execution_filter = (
            ExecutionFilter()
        )

        # No filtramos aquí por orderId.
        self.reqExecutions(
            execution_req_id,
            execution_filter
        )

        if not self.executions_event.wait(
            timeout=timeout
        ):

            print(
                "TIMEOUT consultando "
                "ejecuciones."
            )

            log_warning(
                f"TIMEOUT consultando ejecuciones | "
                f"OrderID={order_id}"
            )

        executions = (
            self.executions.get(
                order_id,
                []
            )
        )

        # ====================================================
        # 4. ORDEN ABIERTA
        # ====================================================

        if open_order is not None:

            order_state = (
                open_order[
                    "order_state"
                ]
            )

            order = (
                open_order[
                    "order"
                ]
            )

            status = getattr(
                order_state,
                "status",
                None
            )

            print()
            print(
                "ORDEN ENCONTRADA COMO ABIERTA"
            )

            print(
                f"Estado: {status}"
            )

            log_warning(
                f"Orden encontrada abierta | "
                f"OrderID={order_id} | "
                f"Status={status}"
            )

            return {
                "found": True,
                "source": "OPEN",
                "order_id": order_id,
                "status": status,
                "filled": 0.0,
                "price": 0.0,
                "executions": executions,
                "action": getattr(
                    order,
                    "action",
                    None
                ),
                "total_quantity": getattr(
                    order,
                    "totalQuantity",
                    None
                )
            }

        # ====================================================
        # 5. ORDEN COMPLETADA
        # ====================================================

        if completed_order is not None:

            order_state = (
                completed_order[
                    "order_state"
                ]
            )

            order = (
                completed_order[
                    "order"
                ]
            )

            status = getattr(
                order_state,
                "status",
                None
            )

            filled = 0.0

            weighted_price = 0.0

            for execution in executions:

                shares = float(
                    execution[
                        "shares"
                    ]
                )

                price = float(
                    execution[
                        "price"
                    ]
                )

                filled += (
                    shares
                )

                weighted_price += (
                    shares * price
                )

            average_price = 0.0

            if filled > 0:

                average_price = (
                    weighted_price
                    / filled
                )

            print()
            print(
                "ORDEN ENCONTRADA COMO COMPLETADA"
            )

            print(
                f"Estado: "
                f"{status}"
            )

            print(
                f"Ejecutado: "
                f"{filled}"
            )

            print(
                f"Precio medio: "
                f"{average_price}"
            )

            log_info(
                f"Orden reconciliada | "
                f"OrderID={order_id} | "
                f"Status={status} | "
                f"Filled={filled} | "
                f"Price={average_price}"
            )

            return {
                "found": True,
                "source": "COMPLETED",
                "order_id": order_id,
                "status": status,
                "filled": filled,
                "price": average_price,
                "executions": executions,
                "action": getattr(
                    order,
                    "action",
                    None
                ),
                "total_quantity": getattr(
                    order,
                    "totalQuantity",
                    None
                )
            }

        # ====================================================
        # 6. UNKNOWN
        # ====================================================

        print()
        print(
            "ORDEN NO ENCONTRADA"
        )

        print(
            "No existe evidencia suficiente "
            "para determinar su resultado."
        )

        log_warning(
            f"Orden UNKNOWN | "
            f"OrderID={order_id}"
        )

        return {
            "found": False,
            "source": None,
            "order_id": order_id,
            "status": "UNKNOWN",
            "filled": 0.0,
            "price": 0.0,
            "executions": executions,
            "action": None,
            "total_quantity": None,
            "error": (
                "Orden no encontrada en las consultas "
                "realizadas."
            )
        }


# ============================================================
# ABRIR LARGO
# ============================================================

def open_long(
    app
):

    position = (
        app.get_position()
    )

    print()
    print(
        f"Posición actual: "
        f"{position} contratos"
    )

    if position != 0:

        print(
            "Ya existe una posición."
        )

        log_warning(
            f"ABRIR_LARGO bloqueado | "
            f"Position={position}"
        )

        return {
            "success": False,
            "action": "BUY",
            "signal_action": (
                "ABRIR_LARGO"
            ),
            "status": "BLOCKED",
            "filled": 0.0,
            "price": 0.0,
            "position": position,
            "error": (
                "Ya existe una posición abierta."
            ),
            "operations": []
        }

    result = (
        app.send_order(
            "BUY"
        )
    )

    result[
        "signal_action"
    ] = "ABRIR_LARGO"

    if result.get(
        "success",
        False
    ):

        print()
        print(
            ">>> OPERACIÓN ABIERTA: "
            "LARGO <<<"
        )

        log_info(
            f"ABRIR_LARGO ejecutado | "
            f"OrderID={result.get('order_id')} | "
            f"Price={result.get('price')} | "
            f"Position={result.get('position')}"
        )

    return result


# ============================================================
# ABRIR CORTO
# ============================================================

def open_short(
    app
):

    position = (
        app.get_position()
    )

    print()
    print(
        f"Posición actual: "
        f"{position} contratos"
    )

    if position != 0:

        print(
            "Ya existe una posición."
        )

        log_warning(
            f"ABRIR_CORTO bloqueado | "
            f"Position={position}"
        )

        return {
            "success": False,
            "action": "SELL",
            "signal_action": (
                "ABRIR_CORTO"
            ),
            "status": "BLOCKED",
            "filled": 0.0,
            "price": 0.0,
            "position": position,
            "error": (
                "Ya existe una posición abierta."
            ),
            "operations": []
        }

    result = (
        app.send_order(
            "SELL"
        )
    )

    result[
        "signal_action"
    ] = "ABRIR_CORTO"

    if result.get(
        "success",
        False
    ):

        print()
        print(
            ">>> OPERACIÓN ABIERTA: "
            "CORTO <<<"
        )

        log_info(
            f"ABRIR_CORTO ejecutado | "
            f"OrderID={result.get('order_id')} | "
            f"Price={result.get('price')} | "
            f"Position={result.get('position')}"
        )

    return result


# ============================================================
# CERRAR POSICIÓN
# ============================================================

def close_position(
    app
):

    position = (
        app.get_position()
    )

    print()
    print(
        f"Posición actual: "
        f"{position} contratos"
    )

    if position == 0:

        log_warning(
            "CERRAR_POSICION bloqueado | "
            "No existe posición."
        )

        return {
            "success": False,
            "action": None,
            "signal_action": (
                "CERRAR_POSICION"
            ),
            "status": "BLOCKED",
            "filled": 0.0,
            "price": 0.0,
            "position": 0.0,
            "error": (
                "No existe ninguna posición."
            ),
            "operations": []
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

    if quantity != QUANTITY:

        log_warning(
            f"Cierre bloqueado | "
            f"Position={position} | "
            f"Quantity={quantity}"
        )

        return {
            "success": False,
            "action": action,
            "signal_action":
                signal_action,
            "status": "BLOCKED",
            "filled": 0.0,
            "price": 0.0,
            "position": position,
            "error": (
                "La posición no es de "
                "1 contrato."
            ),
            "operations": []
        }

    result = (
        app.send_order(
            action
        )
    )

    result[
        "signal_action"
    ] = signal_action

    if result.get(
        "success",
        False
    ):

        print()
        print(
            ">>> OPERACIÓN CERRADA <<<"
        )

        log_info(
            f"{signal_action} ejecutado | "
            f"OrderID={result.get('order_id')} | "
            f"Price={result.get('price')} | "
            f"Position={result.get('position')}"
        )

    return result


# ============================================================
# MAIN MANUAL
# ============================================================

def main():

    log_info(
        "PaperExecutor iniciado en modo manual."
    )

    app = PaperExecutor()

    print(
        "Conectando con IB Gateway..."
    )

    app.connect(
        HOST,
        PORT,
        CLIENT_ID
    )

    api_thread = threading.Thread(
        target=app.run,
        daemon=True
    )

    api_thread.start()

    if not app.connection_ready.wait(
        timeout=10
    ):

        print(
            "No se pudo establecer correctamente "
            "la conexión con IBKR."
        )

        log_error(
            "No se pudo establecer conexión con IBKR "
            "en modo manual."
        )

        app.disconnect()

        return

    print()
    print(
        "Esperando posiciones de IBKR..."
    )

    if not app.positions_ready.wait(
        timeout=10
    ):

        print(
            "No se recibieron las posiciones "
            "iniciales de IBKR."
        )

        log_error(
            "No se recibieron posiciones iniciales "
            "en modo manual."
        )

        app.disconnect()

        return

    print()
    print(
        "========================================"
    )

    print(
        "POSICIÓN INICIAL"
    )

    print(
        "========================================"
    )

    print(
        f"FDXM: "
        f"{app.current_position} contratos"
    )

    if app.current_position > 0:

        print(
            "Dirección: LARGO"
        )

    elif app.current_position < 0:

        print(
            "Dirección: CORTO"
        )

    else:

        print(
            "Sin posición"
        )

    print(
        "========================================"
    )

    log_info(
        f"PaperExecutor manual preparado | "
        f"Position={app.current_position}"
    )

    # --------------------------------------------------------
    # MENÚ MANUAL
    # --------------------------------------------------------

    while True:

        print()
        print(
            "========================================"
        )

        print(
            "       EJECUTOR FDXM PAPER"
        )

        print(
            "========================================"
        )

        print(
            "1 - Abrir LARGO"
        )

        print(
            "2 - Abrir CORTO"
        )

        print(
            "3 - Cerrar posición"
        )

        print(
            "4 - Mostrar posición"
        )

        print(
            "5 - Salir"
        )

        print(
            "========================================"
        )

        option = input(
            "Selecciona una opción: "
        ).strip()

        if option == "1":

            open_long(
                app
            )

        elif option == "2":

            open_short(
                app
            )

        elif option == "3":

            close_position(
                app
            )

        elif option == "4":

            position = (
                app.get_position()
            )

            print()
            print(
                f"Posición FDXM: "
                f"{position} contratos"
            )

            log_info(
                f"Consulta manual de posición | "
                f"Position={position}"
            )

        elif option == "5":

            print()
            print(
                "Cerrando programa..."
            )

            log_info(
                "PaperExecutor manual detenido."
            )

            app.disconnect()

            break

        else:

            print()
            print(
                "Opción no válida."
            )

            log_warning(
                f"Opción manual no válida | "
                f"Option={option}"
            )


# ============================================================
# INICIO
# ============================================================

if __name__ == "__main__":

    main()