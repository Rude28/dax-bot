import threading

from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order
from ibapi.execution import ExecutionFilter


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

        self.connection_ready.set()

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

        # ----------------------------------------------------
        # Solicitar posiciones iniciales.
        # ----------------------------------------------------

        self.current_position = 0.0
        self.position_avg_cost = 0.0

        self.positions_ready.clear()

        print(
            "Solicitando posiciones iniciales..."
        )

        self.reqPositions()

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

            return

        # ----------------------------------------------------
        # Mostrar error.
        # ----------------------------------------------------

        print(
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

        self.position_update_event.set()

    def positionEnd(self):

        print()
        print(
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

    def openOrderEnd(self):

        self.open_orders_event.set()

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

    def completedOrdersEnd(self):

        self.completed_orders_event.set()

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

    def execDetailsEnd(
        self,
        reqId
    ):

        if reqId == (
            self.execution_request_id
        ):

            self.executions_event.set()

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

        # ----------------------------------------------------
        # Comprobar Order ID.
        # ----------------------------------------------------

        if self.next_order_id is None:

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

        # ----------------------------------------------------
        # ENVIAR
        # ----------------------------------------------------

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

            # ------------------------------------------------
            # Cantidad completa.
            # ------------------------------------------------

            if self.order_filled != float(
                QUANTITY
            ):

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

        self.reqOpenOrders()

        if not self.open_orders_event.wait(
            timeout=timeout
        ):

            print(
                "TIMEOUT consultando "
                "órdenes abiertas."
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

        execution_filter = (
            ExecutionFilter()
        )

        # IMPORTANTE:
        # No filtramos aquí por orderId.
        # Recibimos las ejecuciones y posteriormente
        # seleccionamos las que pertenecen al order_id.
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

    return result


# ============================================================
# MAIN MANUAL
# ============================================================

def main():

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

        elif option == "5":

            print()
            print(
                "Cerrando programa..."
            )

            app.disconnect()

            break

        else:

            print()
            print(
                "Opción no válida."
            )


# ============================================================
# INICIO
# ============================================================

if __name__ == "__main__":

    main()