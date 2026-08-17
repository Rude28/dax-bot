import imaplib
import email
import os
import smtplib

from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from dotenv import load_dotenv

from signal_parser import parse_signal


# ============================================================
# CONFIGURACIÓN
# ============================================================

load_dotenv()

# ------------------------------------------------------------
# GMAIL
# ------------------------------------------------------------

GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

# ------------------------------------------------------------
# IMAP
# ------------------------------------------------------------

IMAP_SERVER = os.getenv(
    "IMAP_SERVER",
    "imap.gmail.com"
)

IMAP_PORT = int(
    os.getenv(
        "IMAP_PORT",
        "993"
    )
)

# ------------------------------------------------------------
# SMTP
#
# Lo utilizaremos para enviar los avisos de operaciones.
# ------------------------------------------------------------

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
# CORREO AL QUE ENVIAREMOS LAS NOTIFICACIONES
#
# Si NOTIFY_EMAIL no está definido en .env,
# utilizaremos GMAIL_USER.
# ------------------------------------------------------------

NOTIFY_EMAIL = os.getenv(
    "NOTIFY_EMAIL",
    GMAIL_USER
)

# ------------------------------------------------------------
# PROVEEDOR DE SEÑALES
# ------------------------------------------------------------

SIGNAL_SENDER = "operativadax@gmail.com"

# ------------------------------------------------------------
# DURANTE LAS PRUEBAS SOLO LEEREMOS LOS ÚLTIMOS 10.
#
# IMPORTANTE:
# Cuando conectemos el bot en tiempo real NO debemos utilizar
# este sistema para ejecutar automáticamente los últimos
# correos históricos.
#
# Tendremos que implementar un sistema para detectar
# únicamente correos NUEVOS.
# ------------------------------------------------------------

MAX_EMAILS = 10


# ============================================================
# DECODIFICAR CABECERAS
# ============================================================

def decode_mime_header(value):

    if not value:
        return ""

    decoded = decode_header(value)

    result = ""

    for part, encoding in decoded:

        if isinstance(part, bytes):

            result += part.decode(
                encoding or "utf-8",
                errors="replace"
            )

        else:

            result += part

    return result


# ============================================================
# ENVIAR NOTIFICACIÓN POR EMAIL
# ============================================================

def send_notification(
    subject,
    body
):
    """
    Envía un correo de notificación.

    Esta función queda preparada para utilizarla cuando
    conectemos el lector de señales con el ejecutor IBKR.

    IMPORTANTE:
    Actualmente NO se llama desde el procesamiento de señales,
    porque todavía no estamos ejecutando operaciones.

    Cuando conectemos paper_executor.py tendremos que llamar
    a esta función:

        - DESPUÉS de recibir Filled
        - indicando el precio real de ejecución
        - indicando la acción realizada
        - indicando la posición final

    Y en caso de error:

        - enviar aviso de fallo
        - incluir el error recibido de IBKR
        - indicar que la operación NO ha sido confirmada
    """

    if not GMAIL_USER:

        print(
            "ERROR NOTIFICACIÓN: "
            "falta GMAIL_USER"
        )

        return False

    if not GMAIL_APP_PASSWORD:

        print(
            "ERROR NOTIFICACIÓN: "
            "falta GMAIL_APP_PASSWORD"
        )

        return False

    if not NOTIFY_EMAIL:

        print(
            "ERROR NOTIFICACIÓN: "
            "falta NOTIFY_EMAIL"
        )

        return False

    try:

        # ----------------------------------------------------
        # Crear mensaje
        # ----------------------------------------------------

        message = MIMEMultipart()

        message["From"] = GMAIL_USER
        message["To"] = NOTIFY_EMAIL
        message["Subject"] = subject

        message.attach(
            MIMEText(
                body,
                "plain",
                "utf-8"
            )
        )

        # ----------------------------------------------------
        # Conectar con Gmail SMTP mediante SSL
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
            "Notificación enviada correctamente."
        )

        return True

    except Exception as error:

        print()
        print(
            "ERROR AL ENVIAR NOTIFICACIÓN"
        )

        print(
            f"Tipo:    {type(error).__name__}"
        )

        print(
            f"Mensaje: {error}"
        )

        return False


# ============================================================
# MAIN
# ============================================================

def main():

    print("========================================")
    print("       DAX BOT - EMAIL READER")
    print("========================================")

    # --------------------------------------------------------
    # COMPROBAR CONFIGURACIÓN
    # --------------------------------------------------------

    if not GMAIL_USER:

        print("ERROR: falta GMAIL_USER")
        return

    if not GMAIL_APP_PASSWORD:

        print("ERROR: falta GMAIL_APP_PASSWORD")
        return

    print(
        f"Usuario:       {GMAIL_USER}"
    )

    print(
        f"Servidor IMAP: {IMAP_SERVER}"
    )

    print(
        f"Puerto IMAP:   {IMAP_PORT}"
    )

    print(
        f"Remitente:     {SIGNAL_SENDER}"
    )

    print(
        f"Notificaciones: {NOTIFY_EMAIL}"
    )

    print()

    try:

        # ----------------------------------------------------
        # CONEXIÓN IMAP
        # ----------------------------------------------------

        print(
            "Conectando con Gmail IMAP..."
        )

        mail = imaplib.IMAP4_SSL(
            IMAP_SERVER,
            IMAP_PORT
        )

        print(
            "Conexión IMAP establecida."
        )

        # ----------------------------------------------------
        # AUTENTICACIÓN
        # ----------------------------------------------------

        mail.login(
            GMAIL_USER,
            GMAIL_APP_PASSWORD
        )

        print(
            "Autenticación con Gmail correcta."
        )

        # ----------------------------------------------------
        # SELECCIONAR INBOX
        # ----------------------------------------------------

        status, data = mail.select(
            "INBOX"
        )

        if status != "OK":

            print(
                "ERROR: no se pudo abrir INBOX."
            )

            mail.logout()

            return

        print(
            "INBOX seleccionada."
        )

        # ----------------------------------------------------
        # BUSCAR CORREOS DEL PROVEEDOR
        # ----------------------------------------------------

        print()

        print(
            f"Buscando correos de "
            f"{SIGNAL_SENDER}..."
        )

        status, data = mail.search(
            None,
            f'FROM "{SIGNAL_SENDER}"'
        )

        if status != "OK":

            print(
                "ERROR: no se pudieron buscar "
                "los correos."
            )

            mail.logout()

            return

        email_ids = data[0].split()

        print(
            f"Correos encontrados: "
            f"{len(email_ids)}"
        )

        if not email_ids:

            print()

            print(
                "No se encontraron correos "
                f"de {SIGNAL_SENDER}."
            )

            mail.logout()

            return

        # ----------------------------------------------------
        # ÚLTIMOS CORREOS
        # ----------------------------------------------------

        latest_ids = email_ids[-MAX_EMAILS:]

        print()
        print(
            "========================================"
        )
        print(
            "SEÑALES DETECTADAS"
        )
        print(
            "========================================"
        )

        for email_id in reversed(
            latest_ids
        ):

            status, msg_data = mail.fetch(
                email_id,
                "(RFC822)"
            )

            if status != "OK":

                print(
                    "No se pudo leer el correo."
                )

                continue

            for response_part in msg_data:

                if not isinstance(
                    response_part,
                    tuple
                ):

                    continue

                msg = email.message_from_bytes(
                    response_part[1]
                )

                # --------------------------------------------
                # DATOS DEL CORREO
                # --------------------------------------------

                sender = decode_mime_header(
                    msg.get("From")
                )

                subject = decode_mime_header(
                    msg.get("Subject")
                )

                date = msg.get("Date")

                # --------------------------------------------
                # MOSTRAR CORREO
                # --------------------------------------------

                print()

                print(
                    "----------------------------------------"
                )

                print(
                    f"Remitente: {sender}"
                )

                print(
                    f"Asunto:    {subject}"
                )

                print(
                    f"Fecha:     {date}"
                )

                print(
                    "----------------------------------------"
                )

                # --------------------------------------------
                # PARSER
                # --------------------------------------------

                actions = parse_signal(
                    subject
                )

                if actions is None:

                    print(
                        ">>> SEÑAL NO RECONOCIDA <<<"
                    )

                else:

                    print(
                        ">>> SEÑAL DETECTADA <<<"
                    )

                    for action in actions:

                        print(
                            f"- {action}"
                        )

                    # ------------------------------------------------
                    # IMPORTANTE - TODAVÍA NO ENVIAMOS NOTIFICACIÓN
                    # DE "SEÑAL REALIZADA".
                    #
                    # En este momento únicamente hemos detectado
                    # la señal. Todavía NO hemos enviado ninguna
                    # orden a IBKR.
                    #
                    # Cuando conectemos paper_executor.py:
                    #
                    # 1. Parsearemos la señal.
                    # 2. Comprobaremos la posición actual.
                    # 3. Ejecutaremos la orden.
                    # 4. Esperaremos "Filled".
                    # 5. Obtendremos el precio REAL de ejecución.
                    # 6. Comprobaremos la posición final.
                    # 7. Entonces llamaremos a:
                    #
                    # send_notification(
                    #     "Señal realizada",
                    #     cuerpo_del_informe
                    # )
                    #
                    # Si IBKR devuelve un error:
                    #
                    # send_notification(
                    #     "FALLO - Señal no realizada",
                    #     cuerpo_del_error
                    # )
                    #
                    # Para cambios de posición como:
                    #
                    # Cierro Largos y Abro Cortos
                    #
                    # solo enviaremos "Señal realizada" cuando
                    # LAS DOS operaciones estén confirmadas.
                    #
                    # ------------------------------------------------

        print()

        print(
            "========================================"
        )

        print(
            "Procesamiento finalizado."
        )

        print(
            "========================================"
        )

        # ----------------------------------------------------
        # CERRAR CONEXIÓN IMAP
        # ----------------------------------------------------

        mail.logout()

        print(
            "Conexión cerrada correctamente."
        )

    except Exception as error:

        print()

        print(
            "========================================"
        )

        print(
            "ERROR AL LEER GMAIL"
        )

        print(
            "========================================"
        )

        print(
            f"Tipo:    {type(error).__name__}"
        )

        print(
            f"Mensaje: {error}"
        )


# ============================================================
# INICIO
# ============================================================

if __name__ == "__main__":

    main()