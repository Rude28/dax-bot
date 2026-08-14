from ibapi.client import EClient
from ibapi.wrapper import EWrapper


class IBAccount(EWrapper, EClient):

    def __init__(self):
        EClient.__init__(self, self)

    def nextValidId(self, orderId: int):
        print("Conexión con IBKR establecida.")
        print(f"Next Order ID: {orderId}")

        self.reqAccountSummary(
            1,
            "All",
            "AccountType,NetLiquidation"
        )

    def accountSummary(self, reqId, account, tag, value, currency):
        print("--------------------------------")
        print(f"Cuenta: {account}")
        print(f"{tag}: {value} {currency}")
        print("--------------------------------")

    def accountSummaryEnd(self, reqId):
        print("Información de cuenta recibida.")
        self.cancelAccountSummary(reqId)
        self.disconnect()

    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        print(
            f"IBKR Error | reqId={reqId} | "
            f"code={errorCode} | message={errorString}"
        )


if __name__ == "__main__":
    app = IBAccount()

    print("Conectando con IB Gateway...")

    app.connect(
        "127.0.0.1",
        4002,
        clientId=2
    )

    app.run()

    print("Programa finalizado.")
