import re


# ============================================================
# TIPOS DE SEÑAL
# ============================================================

OPEN_LONG = "ABRIR_LARGO"
CLOSE_LONG = "CERRAR_LARGO"
OPEN_SHORT = "ABRIR_CORTO"
CLOSE_SHORT = "CERRAR_CORTO"


# ============================================================
# PARSER
# ============================================================

def parse_signal(subject):
    """
    Analiza el asunto de un correo de Operativa Dax.

    El precio se ignora completamente.

    Devuelve una lista de acciones:
        ["ABRIR_LARGO"]
        ["CERRAR_LARGO"]
        ["ABRIR_CORTO"]
        ["CERRAR_CORTO"]

    Para cambios de posición:
        ["CERRAR_LARGO", "ABRIR_CORTO"]
        ["CERRAR_CORTO", "ABRIR_LARGO"]

    Si la señal no es reconocida:
        None
    """

    if not subject:
        return None

    # --------------------------------------------------------
    # Normalizar asunto
    # --------------------------------------------------------

    text = subject.strip().lower()

    # Eliminamos acentos para facilitar la detección.
    replacements = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
    }

    for original, replacement in replacements.items():
        text = text.replace(
            original,
            replacement
        )

    # --------------------------------------------------------
    # Comprobar que pertenece a Operativa Dax
    # --------------------------------------------------------

    if "operativa dax" not in text:
        return None

    # --------------------------------------------------------
    # Detectar acciones
    # --------------------------------------------------------

    open_long = bool(
        re.search(
            r"\babro\s+largos?\b",
            text
        )
    )

    close_long = bool(
        re.search(
            r"\bcierro\s+largos?\b",
            text
        )
    )

    open_short = bool(
        re.search(
            r"\babro\s+cortos?\b",
            text
        )
    )

    close_short = bool(
        re.search(
            r"\bcierro\s+cortos?\b",
            text
        )
    )

    # --------------------------------------------------------
    # Ninguna acción reconocida
    # --------------------------------------------------------

    if not any([
        open_long,
        close_long,
        open_short,
        close_short
    ]):
        return None

    # --------------------------------------------------------
    # Validar combinaciones
    # --------------------------------------------------------

    actions = []

    # Cambio LARGO → CORTO
    if close_long and open_short:

        if (
            not open_long
            and not close_short
        ):
            actions = [
                CLOSE_LONG,
                OPEN_SHORT
            ]

            return actions

    # Cambio CORTO → LARGO
    if close_short and open_long:

        if (
            not close_long
            and not open_short
        ):
            actions = [
                CLOSE_SHORT,
                OPEN_LONG
            ]

            return actions

    # --------------------------------------------------------
    # Acciones individuales
    # --------------------------------------------------------

    if open_long and not (
        close_long
        or open_short
        or close_short
    ):
        return [OPEN_LONG]

    if close_long and not (
        open_long
        or open_short
        or close_short
    ):
        return [CLOSE_LONG]

    if open_short and not (
        open_long
        or close_long
        or close_short
    ):
        return [OPEN_SHORT]

    if close_short and not (
        open_long
        or close_long
        or open_short
    ):
        return [CLOSE_SHORT]

    # --------------------------------------------------------
    # Combinación desconocida / ambigua
    # --------------------------------------------------------

    return None


# ============================================================
# PRUEBAS
# ============================================================

def test_signal(subject, expected):

    result = parse_signal(subject)

    print("----------------------------------------")
    print(f"Asunto:   {subject}")
    print(f"Resultado: {result}")
    print(f"Esperado:  {expected}")

    if result == expected:
        print("OK")
    else:
        print("ERROR")


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print("========================================")
    print("       DAX BOT - SIGNAL PARSER")
    print("========================================")

    test_signal(
        "Operativa Dax - Abro Largos en 26421",
        [OPEN_LONG]
    )

    test_signal(
        "Operativa Dax - Cierro Largos en 26439",
        [CLOSE_LONG]
    )

    test_signal(
        "Operativa Dax - Abro Cortos en 26421",
        [OPEN_SHORT]
    )

    test_signal(
        "Operativa Dax - Cierro Cortos en 26421",
        [CLOSE_SHORT]
    )

    test_signal(
        "Operativa Dax - Cierro Largos y Abro Cortos en 26421",
        [
            CLOSE_LONG,
            OPEN_SHORT
        ]
    )

    test_signal(
        "Operativa Dax - Cierro Cortos y Abro Largos en 26421",
        [
            CLOSE_SHORT,
            OPEN_LONG
        ]
    )

    # --------------------------------------------------------
    # Pruebas que deben ser rechazadas
    # --------------------------------------------------------

    test_signal(
        "Operativa Dax - Abro Largos y Abro Cortos en 26421",
        None
    )

    test_signal(
        "Operativa Dax - Cierro Largos y Cierro Cortos en 26421",
        None
    )

    test_signal(
        "Otro proveedor - Abro Largos en 26421",
        None
    )

    print("----------------------------------------")
    print("Pruebas finalizadas.")