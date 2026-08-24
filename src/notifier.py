import os
import smtplib

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from dotenv import load_dotenv

from logger import (
    log_info,
    log_warning,
    log_error,
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

load_dotenv()


# ============================================================
# GMAIL
# ============================================================

GMAIL_USER = os.getenv(
    "GMAIL_USER"
)

GMAIL_APP_PASSWORD = os.getenv(
    "GMAIL_APP_PASSWORD"
)


# ============================================================
# SMTP
# ============================================================

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


# ============================================================
# DESTINATARIO
# ============================================================

NOTIFY_EMAIL = os.getenv(
    "NOTIFY_EMAIL",
    GMAIL_USER
)


# ============================================================
# FORMATEAR VALORES
# ============================================================

def format_number(
    value
):

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

    if result.get(
        "success",
        False
    ):

        return "success"

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

    if filled_operations:

        return "partial"

    return "failure"


# ============================================================
# ASUNTO DEL CORREO
# ============================================================

def build_subject(
    result
):

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
# CUERPO DEL CORREO
# ============================================================

def build_body(
    result
):

    notification_type = (
        get_notification_type(
            result
        )
    )

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

    lines = []

    lines.append(
        "DAX BOT - INFORME DE OPERACIÓN"
    )

    lines.append(
        "========================================"
    )

    lines.append("")

    # --------------------------------------------------------
    # RESULTADO
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # INFORMACIÓN DE LA SEÑAL
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # RESULTADO GENERAL
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # OPERACIONES
    # --------------------------------------------------------

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

            signal_action = operation.get(
                "signal_action"
            )

            if signal_action:

                lines.append(
                    f"  Acción señal: "
                    f"{signal_action}"
                )

            lines.append(
                f"  Acción IBKR: "
                f"{operation.get('action', 'N/A')}"
            )

            lines.append(
                f"  Estado: "
                f"{operation.get('status', 'N/A')}"
            )

            lines.append(
                f"  Cantidad ejecutada: "
                f"{format_number(operation.get('filled', 0))}"
            )

            lines.append(
                f"  Precio ejecución: "
                f"{format_number(operation.get('price'))}"
            )

            lines.append(
                f"  Posición tras operación: "
                f"{format_number(operation.get('position'))}"
            )

            expected_position = operation.get(
                "expected_position"
            )

            if expected_position is not None:

                lines.append(
                    f"  Posición esperada: "
                    f"{format_number(expected_position)}"
                )

            order_id = operation.get(
                "order_id"
            )

            if order_id is not None:

                lines.append(
                    f"  Order ID: "
                    f"{order_id}"
                )

            operation_error = operation.get(
                "error"
            )

            if operation_error:

                lines.append(
                    f"  Error: "
                    f"{operation_error}"
                )

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

    # --------------------------------------------------------
    # ERROR GENERAL
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # POSICIÓN FINAL
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # MENSAJE FINAL
    # --------------------------------------------------------

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

    message_id = result.get(
        "message_id"
    )

    notification_type = (
        get_notification_type(
            result
        )
    )

    # --------------------------------------------------------
    # VALIDACIÓN DE CONFIGURACIÓN
    # --------------------------------------------------------

    if not GMAIL_USER:

        log_error(
            "Notifier: falta GMAIL_USER."
        )

        return False

    if not GMAIL_APP_PASSWORD:

        log_error(
            "Notifier: falta GMAIL_APP_PASSWORD."
        )

        return False

    if not NOTIFY_EMAIL:

        log_error(
            "Notifier: falta NOTIFY_EMAIL."
        )

        return False

    # --------------------------------------------------------
    # CONSTRUIR MENSAJE
    # --------------------------------------------------------

    subject = build_subject(
        result
    )

    body = build_body(
        result
    )

    log_info(
        f"Preparando notificación | "
        f"Message-ID={message_id} | "
        f"Type={notification_type} | "
        f"Subject={subject}"
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

        # ----------------------------------------------------
        # CONEXIÓN SMTP
        # ----------------------------------------------------

        log_info(
            f"Conectando SMTP | "
            f"Server={SMTP_SERVER} | "
            f"Port={SMTP_PORT}"
        )

        with smtplib.SMTP_SSL(
            SMTP_SERVER,
            SMTP_PORT
        ) as smtp:

            smtp.login(
                GMAIL_USER,
                GMAIL_APP_PASSWORD
            )

            log_info(
                f"Autenticación SMTP correcta | "
                f"User={GMAIL_USER}"
            )

            smtp.sendmail(
                GMAIL_USER,
                NOTIFY_EMAIL,
                message.as_string()
            )

        # ----------------------------------------------------
        # ÉXITO
        # ----------------------------------------------------

        log_info(
            f"Notificación enviada | "
            f"Message-ID={message_id} | "
            f"Type={notification_type} | "
            f"Subject={subject}"
        )

        print(
            f"Notificación enviada: "
            f"{subject}"
        )

        return True

    except Exception as error:

        # ----------------------------------------------------
        # ERROR SMTP
        # ----------------------------------------------------

        log_error(
            f"Error enviando notificación | "
            f"Message-ID={message_id} | "
            f"Type={notification_type} | "
            f"Subject={subject} | "
            f"{type(error).__name__}: {error}"
        )

        print()
        print(
            "ERROR AL ENVIAR NOTIFICACIÓN"
        )

        print(
            f"Tipo: {type(error).__name__}"
        )

        print(
            f"Mensaje: {error}"
        )

        return False


# ============================================================
# PRUEBA
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

    log_info(
        "Notifier cargado correctamente."
    )


# ============================================================
# INICIO
# ============================================================

if __name__ == "__main__":

    main()