from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract


class ContractSearch(EWrapper, EClient):

    def __init__(self):
        EClient.__init__(self, self)

    def nextValidId(self, orderId: int):
        print("Conexión con IBKR establecida.")
        print("Buscando contratos DAX en EUREX...")

        contract = Contract()
        contract.symbol = "DAX"
        contract.secType = "FUT"
        contract.exchange = "EUREX"
        contract.currency = "EUR"

        self.reqContractDetails(1, contract)

    def contractDetails(self, reqId, contractDetails):
        contract = contractDetails.contract

        print("--------------------------------")
        print(f"ConId:          {contract.conId}")
        print(f"Symbol:         {contract.symbol}")
        print(f"Local Symbol:   {contract.localSymbol}")
        print(f"Vencimiento:    {contract.lastTradeDateOrContractMonth}")
        print(f"Exchange:       {contract.exchange}")
        print(f"Trading Class:  {contract.tradingClass}")
        print(f"Multiplier:     {contract.multiplier}")
        print("--------------------------------")

    def contractDetailsEnd(self, reqId):
        print("Búsqueda finalizada.")
        self.disconnect()

    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        print(
            f"IBKR Error | reqId={reqId} | "
            f"code={errorCode} | message={errorString}"
        )

        if reqId == 1 and errorCode == 200:
            print("Error en la búsqueda. Cerrando conexión.")
            self.disconnect()


if __name__ == "__main__":
    app = ContractSearch()

    print("Conectando con IB Gateway...")

    app.connect(
        "127.0.0.1",
        4002,
        clientId=3
    )

    app.run()

    print("Programa finalizado.")