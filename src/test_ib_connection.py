from ibapi.client import EClient
from ibapi.wrapper import EWrapper


class IBConnection(EWrapper, EClient):

    def __init__(self):
        EClient.__init__(self, self)

    def nextValidId(self, orderId: int):
        print("================================")
        print("CONEXIÓN CON IBKR CORRECTA")
        print(f"Next Order ID: {orderId}")
        print("================================")

        self.disconnect()


if __name__ == "__main__":
    app = IBConnection()

    print("Conectando con IB Gateway...")
    
    app.connect(
        "127.0.0.1",
        4002,
        clientId=1
    )

    app.run()

    print("Programa finalizado.")