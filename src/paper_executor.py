import threading
import time

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

# FDXM SEP26 obtenido previamente mediante find_fdxm.py
CON_ID = 655095900
EXCHANGE = "EUREX"

QUANTITY = 1


# ============================================================
# APLICACIÓN IBKR
# ============================================================

class PaperExecutor(EWrapper, EClient):

    def __init__(self):
        EClient.__init__(self, self)

        self.next_order_id = None

        self.position = 0
        self.position_avg_cost = 0.0

        self.position_event = threading.Event()

        self.order_event = threading.Event()
        self.order_status = None
        self.order_filled = 0
        self.order_remaining = 0
        self.order_avg_fill_price = 0.0

        self.error_message = None

    # --------------------------------------------------------
    # CONEXIÓN
    # --------------------------------------------------------

    def nextValidId(self, orderId):
        self.next_order_id = orderId

        print()
        print("========================================")
        print("CONEXIÓN CON IBKR CORRECTA")
        print(f"Next Order ID: {orderId}")
        print("========================================")

    # --------------------------------------------------------
    # ERRORES
    # --------------------------------------------------------

    def error(
        self,
        reqId,
        errorCode,
        errorString,
        advancedOrderRejectJson=""
    ):
        # Mensajes informativos de IBKR
        if errorCode in (2104, 2106, 2107, 2158):
            print(
                f"IBKR INFO | code={errorCode} | "
                f"{errorString}"
            )
            return

        print(
            f"IBKR ERROR | reqId={reqId} | "
            f"code={errorCode} | message={errorString}"
        )

        self.error_message = errorString

    # --------------------------------------------------------
    # POSICIONES
    # --------------------------------------------------------

    def position(self, account, contract, position, avgCost):

        if contract.conId == CON_ID:
            self.position = float(position)
            self.position_avg_cost = float(avgCost)

    def positionEnd(self):
        self.position_event.set()

    # --------------------------------------------------------
    # ESTADO DE LA ORDEN
    # --------------------------------------------------------

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

        if orderId != getattr(self, "current_order_id", None):
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

        if status in (
            "Filled",
            "Cancelled",
            "ApiCancelled",
            "Inactive"
        ):
            self.order_event.set()

    # --------------------------------------------------------
    # CONTRATO
    # --------------------------------------------------------

    def create_contract(self):

        contract = Contract()

        contract.conId = CON_ID
        contract.exchange = EXCHANGE

        return contract

    # --------------------------------------------------------
    # CONSULTAR POSICIÓN
    # --------------------------------------------------------

    def get_position(self):

        self.position = 0
        self.position_avg_cost = 0.0
        self.position_event.clear()

        self.reqPositions()

        if not self.position_event.wait(timeout=5):
            print("No se recibió respuesta de posiciones.")
            return None

        self.cancelPositions()

        return self.position

    # --------------------------------------------------------
    # CREAR ORDEN
    # --------------------------------------------------------

    def create_market_order(self, action):

        order = Order()

        order.action = action
        order.orderType = "MKT"
        order.totalQuantity = QUANTITY
        order.tif = "DAY"

        # Queremos que se transmita inmediatamente.
        order.transmit = True

        return order

    # --------------------------------------------------------
    # ENVIAR ORDEN
    # --------------------------------------------------------

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

        # Esperamos hasta 30 segundos a que termine.
        finished = self.order_event.wait(timeout=30)

        if not finished:
            print()
            print("TIMEOUT: no se confirmó la ejecución.")
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
# FUNCIONES DE TRADING
# ============================================================

def open_long(app):

    position = app.get_position()

    if position is None:
        return

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


def open_short(app):

    position = app.get_position()

    if position is None:
        return

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


def close_position(app):

    position = app.get_position()

    if position is None:
        return

    if position == 0:

        print()
        print("No hay ninguna posición abierta.")
        return

    if position > 0:

        # Tenemos largo → vendemos para cerrar.
        action = "SELL"

    else:

        # Tenemos corto → compramos para cerrar.
        action = "BUY"

    quantity = abs(position)

    # Para este MVP solo permitimos cerrar
    # posiciones de 1 contrato.
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

    api_thread = threading.Thread(
        target=app.run,
        daemon=True
    )

    api_thread.start()

    # Esperamos a que llegue nextValidId.
    for _ in range(50):

        if app.next_order_id is not None:
            break

        time.sleep(0.1)

    if app.next_order_id is None:

        print()
        print(
            "No se pudo establecer correctamente "
            "la conexión con IBKR."
        )

        app.disconnect()
        return

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

        option = input("Selecciona una opción: ").strip()

        if option == "1":

            open_long(app)

        elif option == "2":

            open_short(app)

        elif option == "3":

            close_position(app)

        elif option == "4":

            position = app.get_position()

            if position is not None:

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

        elif option == "5":

            print("Cerrando programa...")

            app.disconnect()
            break

        else:

            print("Opción no válida.")


if __name__ == "__main__":
    main()