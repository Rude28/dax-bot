import threading

from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order


# ============================================================
# CONFIGURACIÓN
# ============================================================

HOST = "127.0.0.1"
PORT = 4002
CLIENT_ID = 4

# FDXM SEP26 obtenido mediante find_fdxm.py
CON_ID = 655095900
EXCHANGE = "EUREX"

QUANTITY = 1


# ============================================================
# APLICACIÓN IBKR
# ============================================================

class PaperExecutor(EWrapper, EClient):

    def __init__(self):
        EClient.__init__(self, self)

        # -----------------------------
        # Conexión
        # -----------------------------

        self.next_order_id = None
        self.connection_ready = threading.Event()

        # -----------------------------
        # Posición
        # -----------------------------

        self.current_position = 0.0
        self.position_avg_cost = 0.0

        # Evento que indica que IBKR
        # terminó de enviar las posiciones iniciales.
        self.positions_ready = threading.Event()

        # -----------------------------
        # Órdenes
        # -----------------------------

        self.order_event = threading.Event()

        self.current_order_id = None

        self.order_status = None
        self.order_filled = 0
        self.order_remaining = 0
        self.order_avg_fill_price = 0.0

        self.error_message = None

    # ========================================================
    # CONEXIÓN
    # ========================================================

    def nextValidId(self, orderId):

        self.next_order_id = orderId
        self.connection_ready.set()
        print()
        print("========================================")
        print("CONEXIÓN CON IBKR CORRECTA")
        print(f"Next Order ID: {orderId}")
        print("========================================")

        # ----------------------------------------------------
        # IMPORTANTE:
        # Nos suscribimos UNA SOLA VEZ a las posiciones.
        # IBKR enviará las posiciones actuales y después
        # cualquier actualización.
        # ----------------------------------------------------

        self.current_position = 0.0
        self.position_avg_cost = 0.0
        self.positions_ready.clear()

        print("Solicitando posiciones iniciales...")

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

        # Mensajes informativos normales de IBKR.
        if errorCode in (2104, 2106, 2107, 2158):

            print(
                f"IBKR INFO | code={errorCode} | "
                f"{errorString}"
            )

            return

        print(
            f"IBKR ERROR | reqId={reqId} | "
            f"code={errorCode} | "
            f"message={errorString}"
        )

        self.error_message = errorString

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

        # Solo nos interesa nuestro FDXM.
        if contract.conId == CON_ID:

            self.current_position = float(position)
            self.position_avg_cost = float(avgCost)

            print()
            print("----------------------------------------")
            print("ACTUALIZACIÓN DE POSICIÓN")
            print(f"FDXM:          {self.current_position}")
            print(f"Precio medio:  {self.position_avg_cost}")
            print("----------------------------------------")

    def positionEnd(self):

        print()
        print("Posiciones iniciales recibidas.")

        self.positions_ready.set()

        # IMPORTANTE:
        # NO llamamos a cancelPositions().
        #
        # Queremos mantener la suscripción activa para
        # recibir futuras actualizaciones automáticamente.

    # ========================================================
    # OBTENER POSICIÓN ACTUAL
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

    def create_market_order(self, action):

        order = Order()

        order.action = action
        order.orderType = "MKT"
        order.totalQuantity = QUANTITY
        order.tif = "DAY"

        # Enviar inmediatamente.
        order.transmit = True

        return order

    # ========================================================
    # ESTADO DE LA ORDEN
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

        # Ignorar órdenes que no sean la nuestra.
        if orderId != self.current_order_id:
            return

        self.order_status = status
        self.order_filled = float(filled)
        self.order_remaining = float(remaining)
        self.order_avg_fill_price = float(avgFillPrice)

        print(
            f"Orden {orderId} | "
            f"Estado: {status} | "
            f"Ejecutado: {filled} | "
            f"Restante: {remaining}"
        )

        # Estados terminales.
        if status in (
            "Filled",
            "Cancelled",
            "ApiCancelled",
            "Inactive"
        ):

            self.order_event.set()

    # ========================================================
    # ENVIAR ORDEN
    # ========================================================

    def send_order(self, action):

        if self.next_order_id is None:

            print("Todavía no tenemos un Order ID.")

            return False

        contract = self.create_contract()
        order = self.create_market_order(action)

        order_id = self.next_order_id

        self.current_order_id = order_id

        self.order_event.clear()

        self.order_status = None
        self.order_filled = 0
        self.order_remaining = QUANTITY
        self.order_avg_fill_price = 0.0
        self.error_message = None

        print()
        print("========================================")
        print("ENVIANDO ORDEN")
        print(f"Acción:     {action}")
        print(f"Cantidad:   {QUANTITY}")
        print("Tipo:       MKT")
        print("========================================")

        self.placeOrder(
            order_id,
            contract,
            order
        )

        self.next_order_id += 1

        # Esperamos máximo 30 segundos.
        finished = self.order_event.wait(
            timeout=30
        )

        if not finished:

            print()
            print(
                "TIMEOUT: no se confirmó "
                "la ejecución."
            )

            return False

        if self.order_status == "Filled":

            print()
            print("========================================")
            print("OPERACIÓN EJECUTADA")
            print(f"Acción:       {action}")
            print(f"Cantidad:     {self.order_filled}")
            print(
                f"Precio medio: "
                f"{self.order_avg_fill_price}"
            )
            print("========================================")

            return True

        print()
        print(
            f"ORDEN NO EJECUTADA. "
            f"Estado: {self.order_status}"
        )

        return False


# ============================================================
# ABRIR LARGO
# ============================================================

def open_long(app):

    position = app.get_position()

    print()
    print(
        f"Posición actual: "
        f"{position} contratos"
    )

    if position != 0:

        print()
        print(
            f"Ya existe una posición: "
            f"{position} contratos."
        )

        print("Primero debes cerrarla.")

        return

    success = app.send_order("BUY")

    if success:

        print()
        print(">>> OPERACIÓN ABIERTA: LARGO <<<")


# ============================================================
# ABRIR CORTO
# ============================================================

def open_short(app):

    position = app.get_position()

    print()
    print(
        f"Posición actual: "
        f"{position} contratos"
    )

    if position != 0:

        print()
        print(
            f"Ya existe una posición: "
            f"{position} contratos."
        )

        print("Primero debes cerrarla.")

        return

    success = app.send_order("SELL")

    if success:

        print()
        print(">>> OPERACIÓN ABIERTA: CORTO <<<")


# ============================================================
# CERRAR POSICIÓN
# ============================================================

def close_position(app):

    position = app.get_position()

    print()
    print(
        f"Posición actual: "
        f"{position} contratos"
    )

    if position == 0:

        print()
        print("No hay ninguna posición abierta.")

        return

    # Largo → SELL para cerrar.
    if position > 0:

        action = "SELL"

    # Corto → BUY para cerrar.
    else:

        action = "BUY"

    quantity = abs(position)

    # Este MVP trabaja solamente con 1 contrato.
    if quantity != QUANTITY:

        print()
        print(
            f"La posición actual es de "
            f"{quantity} contratos."
        )

        print(
            "Este MVP solo permite "
            "cerrar 1 contrato."
        )

        return

    success = app.send_order(action)

    if success:

        print()
        print(">>> OPERACIÓN CERRADA <<<")


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    app = PaperExecutor()

    print("Conectando con IB Gateway...")

    app.connect(
        HOST,
        PORT,
        CLIENT_ID
    )

    # --------------------------------------------------------
    # Hilo que mantiene funcionando la API.
    # --------------------------------------------------------

    api_thread = threading.Thread(
        target=app.run,
        daemon=True
    )

    api_thread.start()

    # --------------------------------------------------------
    # Esperamos a que IBKR confirme la conexión.
    # --------------------------------------------------------

    if not app.connection_ready.wait(
        timeout=10
    ):

        print()
        print(
            "No se pudo establecer correctamente "
            "la conexión con IBKR."
        )

        app.disconnect()

        return

    # --------------------------------------------------------
    # Esperamos a recibir las posiciones iniciales.
    # --------------------------------------------------------

    print()
    print("Esperando posiciones de IBKR...")

    if not app.positions_ready.wait(
        timeout=10
    ):

        print()
        print(
            "No se recibieron las posiciones "
            "iniciales de IBKR."
        )

        app.disconnect()

        return

    # --------------------------------------------------------
    # Mostrar posición inicial.
    # --------------------------------------------------------

    print()
    print("========================================")
    print("POSICIÓN INICIAL")
    print("========================================")

    print(
        f"FDXM: "
        f"{app.current_position} contratos"
    )

    if app.current_position > 0:

        print("Dirección: LARGO")

    elif app.current_position < 0:

        print("Dirección: CORTO")

    else:

        print("Sin posición")

    print("========================================")

    # --------------------------------------------------------
    # MENÚ
    # --------------------------------------------------------

    while True:

        print()
        print("========================================")
        print("       EJECUTOR FDXM PAPER")
        print("========================================")

        print("1 - Abrir LARGO")
        print("2 - Abrir CORTO")
        print("3 - Cerrar posición")
        print("4 - Mostrar posición")
        print("5 - Salir")

        print("========================================")

        option = input(
            "Selecciona una opción: "
        ).strip()

        # ----------------------------------------------------
        # ABRIR LARGO
        # ----------------------------------------------------

        if option == "1":

            open_long(app)

        # ----------------------------------------------------
        # ABRIR CORTO
        # ----------------------------------------------------

        elif option == "2":

            open_short(app)

        # ----------------------------------------------------
        # CERRAR
        # ----------------------------------------------------

        elif option == "3":

            close_position(app)

        # ----------------------------------------------------
        # MOSTRAR POSICIÓN
        # ----------------------------------------------------

        elif option == "4":

            position = app.get_position()

            print()
            print(
                f"Posición FDXM: "
                f"{position} contratos"
            )

            if position > 0:

                print("Dirección: LARGO")

            elif position < 0:

                print("Dirección: CORTO")

            else:

                print("Sin posición")

        # ----------------------------------------------------
        # SALIR
        # ----------------------------------------------------

        elif option == "5":

            print()
            print("Cerrando programa...")

            app.disconnect()

            break

        # ----------------------------------------------------
        # OPCIÓN INCORRECTA
        # ----------------------------------------------------

        else:

            print()
            print("Opción no válida.")


# ============================================================
# INICIO
# ============================================================

if __name__ == "__main__":

    main()