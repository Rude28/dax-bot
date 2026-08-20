import os
import smtplib

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from dotenv import load_dotenv


# ============================================================
# CONFIGURACIÓN
# ============================================================

load_dotenv()

GMAIL_USER = os.getenv(
    "GMAIL_USER"
)

GMAIL_APP_PASSWORD = os.getenv(
    "GMAIL_APP_PASSWORD"
)

SMTP_SERVER = os.getenv(
    "SMTP_SERVER",
    "smtp.gmail.com"
)

SMTP_PORT = int(
    os.getenv(
        "SMTP_PORT",
        "465"
    )
)

# ------------------------------------------------------------
# Destinatario de las notificaciones.
#
# Por defecto:
# la misma cuenta Gmail utilizada por el bot.
# ------------------------------------------------------------

NOTIFY_EMAIL = os.getenv(
    "NOTIFY_EMAIL",
    GMAIL_USER
)


# ============================================================
# UTILIDADES
# ============================================================

def format_number(value):
    """
    Formatea números para mostrarlos de forma legible.
    """

    if value is None:
        return "N/A"

    if isinstance(
        value,
        float
    ):

        if value.is_integer():

            return str(
                int(value)
            )

        return f"{value:.2f}"

    return str(value)


# ============================================================
# DETERMINAR TIPO DE NOTIFICACIÓN
# ============================================================

def get_notification_type(
    result
):
    """
    Determina el tipo de notificación.

    success=True
        -> Señal realizada

    success=False y alguna operación Filled
        -> Ejecución parcial

    success=False y ninguna operación Filled
        -> Fallo - señal no realizada
    """

    # --------------------------------------------------------
    # ÉXITO COMPLETO
    # --------------------------------------------------------

    if result.get(
        "success",
        False
    ):

        return "success"

    # --------------------------------------------------------
    # Comprobar operaciones ejecutadas.
    # --------------------------------------------------------

    operations = result.get(
        "operations",
        []
    )

    filled_operations = [
        operation
        for operation in operations
        if operation.get(
            "status"
        ) == "Filled"
    ]

    # --------------------------------------------------------
    # EJECUCIÓN PARCIAL
    # --------------------------------------------------------

    if filled_operations:

        return "partial"

    # --------------------------------------------------------
    # FALLO
    # --------------------------------------------------------

    return "failure"


# ============================================================
# CONSTRUIR ASUNTO
# ============================================================

def build_subject(
    result
):
    """
    Construye el asunto del correo.
    """

    notification_type = (
        get_notification_type(
            result
        )
    )

    if notification_type == "success":

        return "Señal realizada"

    if notification_type == "partial":

        return "Ejecución parcial"

    return "Fallo - señal no realizada"


# ============================================================
# CONSTRUIR CUERPO
# ============================================================

def build_body(
    result
):
    """
    Construye el cuerpo completo de la notificación.
    """

    notification_type = (
        get_notification_type(
            result
        )
    )

    # ========================================================
    # DATOS GENERALES
    # ========================================================

    message_id = result.get(
        "message_id",
        "N/A"
    )

    email_uid = result.get(
        "email_uid",
        "N/A"
    )

    sender = result.get(
        "sender",
        "N/A"
    )

    signal_subject = result.get(
        "subject",
        "N/A"
    )

    signal_date = result.get(
        "date",
        "N/A"
    )

    actions = result.get(
        "actions",
        []
    )

    final_position = result.get(
        "position",
        "N/A"
    )

    overall_status = result.get(
        "status",
        "N/A"
    )

    general_error = result.get(
        "error"
    )

    # ========================================================
    # CONSTRUIR CUERPO
    # ========================================================

    lines = []

    lines.append(
        "DAX BOT - INFORME DE OPERACIÓN"
    )

    lines.append(
        "========================================"
    )

    lines.append("")

    # ========================================================
    # RESULTADO GENERAL
    # ========================================================

    if notification_type == "success":

        lines.append(
            "RESULTADO: SEÑAL REALIZADA"
        )

    elif notification_type == "partial":

        lines.append(
            "RESULTADO: EJECUCIÓN PARCIAL"
        )

    else:

        lines.append(
            "RESULTADO: SEÑAL NO REALIZADA"
        )

    lines.append("")

    # ========================================================
    # INFORMACIÓN DEL CORREO
    # ========================================================

    lines.append(
        "INFORMACIÓN DE LA SEÑAL"
    )

    lines.append(
        "----------------------------------------"
    )

    lines.append(
        f"Message-ID: {message_id}"
    )

    lines.append(
        f"UID IMAP:   {email_uid}"
    )

    lines.append(
        f"Remitente:  {sender}"
    )

    lines.append(
        f"Fecha:      {signal_date}"
    )

    lines.append(
        f"Asunto:     {signal_subject}"
    )

    lines.append(
        f"Acciones:   {actions}"
    )

    lines.append("")

    # ========================================================
    # RESULTADO GENERAL
    # ========================================================

    lines.append(
        "RESULTADO DE EJECUCIÓN"
    )

    lines.append(
        "----------------------------------------"
    )

    lines.append(
        f"Estado general: {overall_status}"
    )

    lines.append(
        f"Posición final: "
        f"{format_number(final_position)} FDXM"
    )

    lines.append("")

    # ========================================================
    # OPERACIONES
    # ========================================================

    operations = result.get(
        "operations",
        []
    )

    if operations:

        lines.append(
            "OPERACIONES"
        )

        lines.append(
            "----------------------------------------"
        )

        for index, operation in enumerate(
            operations,
            start=1
        ):

            lines.append(
                f"OPERACIÓN {index}"
            )

            # ------------------------------------------------
            # Acción de la señal
            # ------------------------------------------------

            signal_action = operation.get(
                "signal_action"
            )

            if signal_action:

                lines.append(
                    f"  Acción señal: "
                    f"{signal_action}"
                )

            # ------------------------------------------------
            # Acción real IBKR
            # ------------------------------------------------

            lines.append(
                f"  Acción IBKR: "
                f"{operation.get('action', 'N/A')}"
            )

            # ------------------------------------------------
            # Estado
            # ------------------------------------------------

            lines.append(
                f"  Estado: "
                f"{operation.get('status', 'N/A')}"
            )

            # ------------------------------------------------
            # Cantidad
            # ------------------------------------------------

            lines.append(
                f"  Cantidad ejecutada: "
                f"{format_number(operation.get('filled', 0))}"
            )

            # ------------------------------------------------
            # Precio
            # ------------------------------------------------

            lines.append(
                f"  Precio ejecución: "
                f"{format_number(operation.get('price'))}"
            )

            # ------------------------------------------------
            # Posición resultante
            # ------------------------------------------------

            lines.append(
                f"  Posición tras operación: "
                f"{format_number(operation.get('position'))}"
            )

            # ------------------------------------------------
            # Posición esperada
            # ------------------------------------------------

            expected_position = operation.get(
                "expected_position"
            )

            if expected_position is not None:

                lines.append(
                    f"  Posición esperada: "
                    f"{format_number(expected_position)}"
                )

            # ------------------------------------------------
            # Order ID
            # ------------------------------------------------

            order_id = operation.get(
                "order_id"
            )

            if order_id is not None:

                lines.append(
                    f"  Order ID: "
                    f"{order_id}"
                )

            # ------------------------------------------------
            # Error
            # ------------------------------------------------

            operation_error = operation.get(
                "error"
            )

            if operation_error:

                lines.append(
                    f"  Error: "
                    f"{operation_error}"
                )

            # ------------------------------------------------
            # Código de error IBKR
            # ------------------------------------------------

            error_code = operation.get(
                "error_code"
            )

            if error_code is not None:

                lines.append(
                    f"  Código IBKR: "
                    f"{error_code}"
                )

            lines.append("")

    else:

        lines.append(
            "OPERACIONES"
        )

        lines.append(
            "----------------------------------------"
        )

        lines.append(
            "No se ejecutó ninguna operación."
        )

        lines.append("")

    # ========================================================
    # ERROR GENERAL
    # ========================================================

    if general_error:

        lines.append(
            "ERROR GENERAL"
        )

        lines.append(
            "----------------------------------------"
        )

        lines.append(
            str(general_error)
        )

        lines.append("")

    # ========================================================
    # POSICIÓN FINAL
    # ========================================================

    lines.append(
        "POSICIÓN FINAL"
    )

    lines.append(
        "----------------------------------------"
    )

    lines.append(
        f"{format_number(final_position)} FDXM"
    )

    lines.append("")

    # ========================================================
    # MENSAJE FINAL
    # ========================================================

    if notification_type == "success":

        lines.append(
            "La señal ha sido ejecutada correctamente "
            "y la posición final ha sido confirmada."
        )

    elif notification_type == "partial":

        lines.append(
            "ATENCIÓN: la señal se ha ejecutado "
            "parcialmente."
        )

        lines.append(
            "La posición debe revisarse antes "
            "de realizar nuevas operaciones."
        )

    else:

        lines.append(
            "La señal NO ha sido confirmada "
            "como ejecutada correctamente."
        )

    return "\n".join(
        lines
    )


# ============================================================
# ENVIAR NOTIFICACIÓN
# ============================================================

def send_notification(
    result
):
    """
    Envía el resultado de una operación mediante Gmail SMTP.

    No ejecuta operaciones y no modifica el estado de Gmail.
    """

    # --------------------------------------------------------
    # Comprobar configuración.
    # --------------------------------------------------------

    if not GMAIL_USER:

        print(
            "ERROR NOTIFIER: "
            "falta GMAIL_USER."
        )

        return False

    if not GMAIL_APP_PASSWORD:

        print(
            "ERROR NOTIFIER: "
            "falta GMAIL_APP_PASSWORD."
        )

        return False

    if not NOTIFY_EMAIL:

        print(
            "ERROR NOTIFIER: "
            "falta NOTIFY_EMAIL."
        )

        return False

    # --------------------------------------------------------
    # Construir mensaje.
    # --------------------------------------------------------

    subject = build_subject(
        result
    )

    body = build_body(
        result
    )

    try:

        message = MIMEMultipart()

        message["From"] = (
            GMAIL_USER
        )

        message["To"] = (
            NOTIFY_EMAIL
        )

        message["Subject"] = (
            subject
        )

        message.attach(
            MIMEText(
                body,
                "plain",
                "utf-8"
            )
        )

        print()
        print(
            "Enviando notificación..."
        )

        # ----------------------------------------------------
        # SMTP SSL Gmail
        # ----------------------------------------------------

        with smtplib.SMTP_SSL(
            SMTP_SERVER,
            SMTP_PORT
        ) as smtp:

            smtp.login(
                GMAIL_USER,
                GMAIL_APP_PASSWORD
            )

            smtp.sendmail(
                GMAIL_USER,
                NOTIFY_EMAIL,
                message.as_string()
            )

        print(
            f"Notificación enviada: "
            f"{subject}"
        )

        return True

    except Exception as error:

        print()
        print(
            "ERROR AL ENVIAR NOTIFICACIÓN"
        )

        print(
            f"Tipo: "
            f"{type(error).__name__}"
        )

        print(
            f"Mensaje: "
            f"{error}"
        )

        return False


# ============================================================
# PRUEBAS LOCALES
# ============================================================

def main():

    print(
        "========================================"
    )

    print(
        "       DAX BOT - NOTIFIER"
    )

    print(
        "========================================"
    )

    # ========================================================
    # PRUEBA 1 — ÉXITO SIMPLE
    # ========================================================

    test_success = {

        "success": True,

        "type": "single",

        "message_id": (
            "<test-success@gmail.com>"
        ),

        "email_uid": "TEST-001",

        "sender": (
            "Operativa Dax "
            "<operativadax@gmail.com>"
        ),

        "date": (
            "Thu, 20 Aug 2026 "
            "16:31:03 +0200"
        ),

        "subject": (
            "Operativa Dax - "
            "Abro Largos en 26421"
        ),

        "actions": [
            "ABRIR_LARGO"
        ],

        "status": "Filled",

        "filled": 1.0,

        "price": 26486.0,

        "position": 1.0,

        "expected_position": 1.0,

        "order_id": 100,

        "operations": [

            {
                "success": True,
                "signal_action": "ABRIR_LARGO",
                "action": "BUY",
                "status": "Filled",
                "filled": 1.0,
                "price": 26486.0,
                "position": 1.0,
                "expected_position": 1.0,
                "order_id": 100
            }

        ]

    }

    # ========================================================
    # PRUEBA 2 — TRANSICIÓN COMPLETA
    # ========================================================

    test_sequence = {

        "success": True,

        "type": "sequence",

        "message_id": (
            "<test-sequence@gmail.com>"
        ),

        "email_uid": "TEST-002",

        "sender": (
            "Operativa Dax "
            "<operativadax@gmail.com>"
        ),

        "date": (
            "Thu, 20 Aug 2026 "
            "16:35:03 +0200"
        ),

        "subject": (
            "Operativa Dax - "
            "Cierro Largos y Abro Cortos"
        ),

        "actions": [
            "CERRAR_LARGO",
            "ABRIR_CORTO"
        ],

        "status": "FILLED",

        "filled": 2.0,

        "price": 26490.0,

        "position": -1.0,

        "operations": [

            {
                "success": True,
                "signal_action": "CERRAR_LARGO",
                "action": "SELL",
                "status": "Filled",
                "filled": 1.0,
                "price": 26490.0,
                "position": 0.0,
                "expected_position": 0.0,
                "order_id": 101
            },

            {
                "success": True,
                "signal_action": "ABRIR_CORTO",
                "action": "SELL",
                "status": "Filled",
                "filled": 1.0,
                "price": 26488.0,
                "position": -1.0,
                "expected_position": -1.0,
                "order_id": 102
            }

        ]

    }

    # ========================================================
    # MOSTRAR PRUEBAS
    # ========================================================

    tests = [
        (
            "ÉXITO SIMPLE",
            test_success
        ),
        (
            "SECUENCIA COMPLETA",
            test_sequence
        )
    ]

    for test_name, test_result in tests:

        print()
        print(
            "========================================"
        )

        print(
            f"PRUEBA: {test_name}"
        )

        print(
            "========================================"
        )

        print(
            f"Asunto: "
            f"{build_subject(test_result)}"
        )

        print()

        print(
            build_body(
                test_result
            )
        )

        print(
            "========================================"
        )

    # --------------------------------------------------------
    # IMPORTANTE:
    #
    # Las pruebas NO envían correos.
    #
    # send_notification() solo se llamará desde
    # bot_auto.py cuando hagamos la integración.
    # --------------------------------------------------------


# ============================================================
# INICIO
# ============================================================

if __name__ == "__main__":

    main()