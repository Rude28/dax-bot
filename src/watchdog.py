import json
import os
import smtplib
import subprocess
import sys
import time

from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from dotenv import load_dotenv


# ============================================================
# CONFIGURACIÓN
# ============================================================

load_dotenv()

HEARTBEAT_FILE = os.path.join(
    "data",
    "bot_heartbeat.json"
)

STATUS_FILE = os.path.join(
    "data",
    "bot_status.json"
)

BOT_SCRIPT = os.path.join(
    "src",
    "bot_auto.py"
)

BOT_SCRIPT_NAME = "bot_auto.py"

HEARTBEAT_TIMEOUT = float(
    os.getenv(
        "HEARTBEAT_TIMEOUT",
        "30"
    )
)

WATCHDOG_INTERVAL = float(
    os.getenv(
        "WATCHDOG_INTERVAL",
        "5"
    )
)

REQUIRED_TIMEOUTS = int(
    os.getenv(
        "WATCHDOG_REQUIRED_TIMEOUTS",
        "2"
    )
)

RECOVERY_TIMEOUT = float(
    os.getenv(
        "WATCHDOG_RECOVERY_TIMEOUT",
        "90"
    )
)

RECOVERY_CHECK_INTERVAL = float(
    os.getenv(
        "WATCHDOG_RECOVERY_CHECK_INTERVAL",
        "5"
    )
)

RESTART_COOLDOWN = float(
    os.getenv(
        "WATCHDOG_RESTART_COOLDOWN",
        "60"
    )
)

WATCHDOG_AUTO_RECOVER = (
    os.getenv(
        "WATCHDOG_AUTO_RECOVER",
        "true"
    )
    .strip()
    .lower()
    in (
        "1",
        "true",
        "yes",
        "on"
    )
)

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

NOTIFY_EMAIL = os.getenv(
    "NOTIFY_EMAIL",
    GMAIL_USER
)


# ============================================================
# FECHA
# ============================================================

def utc_now_text():
    return (
        datetime.now(
            timezone.utc
        ).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
    )


# ============================================================
# EMAIL DE ALERTA
# ============================================================

def send_watchdog_email(
    subject,
    body
):
    if not GMAIL_USER:
        print(
            "WATCHDOG EMAIL ERROR: falta GMAIL_USER."
        )
        return False

    if not GMAIL_APP_PASSWORD:
        print(
            "WATCHDOG EMAIL ERROR: "
            "falta GMAIL_APP_PASSWORD."
        )
        return False

    if not NOTIFY_EMAIL:
        print(
            "WATCHDOG EMAIL ERROR: falta NOTIFY_EMAIL."
        )
        return False

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

    smtp = None

    try:
        print(
            f"WATCHDOG | Enviando alerta | "
            f"Subject={subject}"
        )

        smtp = smtplib.SMTP_SSL(
            SMTP_SERVER,
            SMTP_PORT,
            timeout=15
        )

        smtp.login(
            GMAIL_USER,
            GMAIL_APP_PASSWORD
        )

        smtp.sendmail(
            GMAIL_USER,
            [NOTIFY_EMAIL],
            message.as_string()
        )

        print(
            "WATCHDOG | Alerta enviada correctamente."
        )

        return True

    except Exception as error:
        print(
            "WATCHDOG EMAIL ERROR | "
            f"{type(error).__name__}: {error}"
        )
        return False

    finally:
        if smtp is not None:
            try:
                smtp.quit()
            except Exception:
                pass


# ============================================================
# LEER HEARTBEAT
# ============================================================

def load_heartbeat():
    try:
        with open(
            HEARTBEAT_FILE,
            "r",
            encoding="utf-8"
        ) as file:
            data = json.load(file)

    except FileNotFoundError as error:
        raise RuntimeError(
            f"No existe el archivo heartbeat: "
            f"{HEARTBEAT_FILE}"
        ) from error

    except json.JSONDecodeError as error:
        raise RuntimeError(
            "El archivo heartbeat contiene JSON corrupto."
        ) from error

    except OSError as error:
        raise RuntimeError(
            f"No se pudo leer heartbeat: "
            f"{type(error).__name__}: {error}"
        ) from error

    if not isinstance(data, dict):
        raise RuntimeError(
            "El heartbeat no contiene un objeto JSON válido."
        )

    return data


# ============================================================
# LEER ESTADO BOT
# ============================================================

def load_bot_status():
    try:
        with open(
            STATUS_FILE,
            "r",
            encoding="utf-8"
        ) as file:
            data = json.load(file)

    except FileNotFoundError as error:
        raise RuntimeError(
            f"No existe el archivo de estado: "
            f"{STATUS_FILE}"
        ) from error

    except json.JSONDecodeError as error:
        raise RuntimeError(
            "bot_status.json contiene JSON corrupto."
        ) from error

    except OSError as error:
        raise RuntimeError(
            f"No se pudo leer bot_status.json: "
            f"{type(error).__name__}: {error}"
        ) from error

    if not isinstance(data, dict):
        raise RuntimeError(
            "bot_status.json no contiene "
            "un objeto JSON válido."
        )

    return data


# ============================================================
# PARSEAR TIMESTAMP
# ============================================================

def parse_timestamp(
    timestamp
):
    if not timestamp:
        raise RuntimeError(
            "El heartbeat no contiene last_heartbeat."
        )

    try:
        parsed = datetime.fromisoformat(
            str(timestamp)
        )

    except ValueError as error:
        raise RuntimeError(
            f"Timestamp heartbeat inválido: {timestamp}"
        ) from error

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed.astimezone(
        timezone.utc
    )


# ============================================================
# COMPROBAR HEARTBEAT
# ============================================================

def check_heartbeat(
    timeout=HEARTBEAT_TIMEOUT
):
    data = load_heartbeat()

    last_heartbeat = parse_timestamp(
        data.get(
            "last_heartbeat"
        )
    )

    last_cycle = data.get(
        "last_cycle"
    )

    heartbeat_status = data.get(
        "status",
        "UNKNOWN"
    )

    now = datetime.now(
        timezone.utc
    )

    age = (
        now - last_heartbeat
    ).total_seconds()

    alive = (
        age <= float(timeout)
    )

    return {
        "alive": alive,
        "heartbeat_status": heartbeat_status,
        "last_heartbeat": last_heartbeat.isoformat(),
        "last_cycle": last_cycle,
        "age_seconds": age,
        "timeout_seconds": float(timeout),
        "heartbeat_file": HEARTBEAT_FILE,
    }


# ============================================================
# COMPROBAR READY
# ============================================================

def check_bot_ready():
    try:
        data = load_bot_status()

        status = data.get(
            "status",
            "UNKNOWN"
        )

        ibkr_connected = bool(
            data.get(
                "ibkr_connected",
                False
            )
        )

        gmail_connected = bool(
            data.get(
                "gmail_connected",
                False
            )
        )

        ready = (
            status == "READY"
            and ibkr_connected
            and gmail_connected
        )

        return {
            "ready": ready,
            "status": status,
            "ibkr_connected": ibkr_connected,
            "gmail_connected": gmail_connected,
        }

    except Exception as error:
        return {
            "ready": False,
            "status": "UNKNOWN",
            "ibkr_connected": False,
            "gmail_connected": False,
            "error": (
                f"{type(error).__name__}: {error}"
            ),
        }


# ============================================================
# PROCESOS PYTHON
# ============================================================

def _query_python_processes():
    try:
        result = subprocess.run(
            [
                "wmic",
                "process",
                "where",
                "name='python.exe'",
                "get",
                "ProcessId,CommandLine",
                "/format:list"
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False
        )

        return result.stdout or ""

    except FileNotFoundError:
        pass

    except Exception:
        pass

    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "Get-CimInstance Win32_Process "
                    "-Filter \"Name = 'python.exe'\" "
                    "| Select-Object ProcessId,CommandLine "
                    "| Format-List"
                )
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False
        )

        return result.stdout or ""

    except Exception:
        return ""


def is_bot_process_running():
    output = _query_python_processes()

    return (
        BOT_SCRIPT_NAME.lower()
        in output.lower()
    )


def get_bot_process_info():
    output = _query_python_processes()

    matching = []

    for line in output.splitlines():
        if BOT_SCRIPT_NAME.lower() in line.lower():
            matching.append(line)

    return {
        "running": bool(matching),
        "info": "\n".join(matching) if matching else None
    }


# ============================================================
# INICIAR BOT
# ============================================================

def start_bot():
    script_path = os.path.abspath(
        BOT_SCRIPT
    )

    project_dir = os.path.dirname(
        os.path.dirname(
            script_path
        )
    )

    venv_python = os.path.join(
        project_dir,
        ".venv",
        "Scripts",
        "python.exe"
    )

    if os.path.exists(venv_python):
        python_executable = venv_python
    else:
        python_executable = sys.executable

    if not os.path.exists(script_path):
        raise RuntimeError(
            f"No existe bot_auto.py: {script_path}"
        )

    print()
    print(
        "========================================"
    )
    print(
        "            INICIANDO BOT"
    )
    print(
        "========================================"
    )
    print(
        f"Python: {python_executable}"
    )
    print(
        f"Script: {script_path}"
    )
    print(
        f"Directorio: {project_dir}"
    )
    print()

    process = subprocess.Popen(
        [
            python_executable,
            script_path
        ],
        cwd=project_dir,
        creationflags=(
            subprocess.CREATE_NEW_PROCESS_GROUP
        )
    )

    print(
        f"Bot iniciado | PID={process.pid}"
    )

    return process


# ============================================================
# ESPERAR RECUPERACIÓN COMPLETA
# ============================================================

def wait_for_recovery(
    old_heartbeat,
    timeout=RECOVERY_TIMEOUT
):
    start_time = time.time()

    while (
        time.time() - start_time
        < timeout
    ):
        heartbeat_ok = False
        heartbeat_result = None

        try:
            heartbeat_result = check_heartbeat()

            current_heartbeat = (
                heartbeat_result.get(
                    "last_heartbeat"
                )
            )

            heartbeat_changed = (
                current_heartbeat
                != old_heartbeat
            )

            heartbeat_ok = (
                heartbeat_result["alive"]
                and heartbeat_changed
            )

        except Exception:
            pass

        ready_result = check_bot_ready()

        print(
            "RECOVERY CHECK | "
            f"Heartbeat="
            f"{'OK' if heartbeat_ok else 'NO'} | "
            f"READY="
            f"{'YES' if ready_result['ready'] else 'NO'} | "
            f"IBKR="
            f"{'OK' if ready_result['ibkr_connected'] else 'NO'} | "
            f"Gmail="
            f"{'OK' if ready_result['gmail_connected'] else 'NO'}"
        )

        if (
            heartbeat_ok
            and ready_result["ready"]
        ):
            return {
                "heartbeat": heartbeat_result,
                "ready": ready_result,
            }

        time.sleep(
            RECOVERY_CHECK_INTERVAL
        )

    return None


# ============================================================
# ALERTA CAÍDA
# ============================================================

def send_failure_alert(
    heartbeat_result,
    ready_result
):
    body = (
        "DAX BOT - ALERTA CRÍTICA\n"
        "========================\n\n"

        "El watchdog ha confirmado que "
        "bot_auto.py no responde.\n\n"

        f"Hora de detección: "
        f"{utc_now_text()}\n\n"

        f"Último heartbeat: "
        f"{heartbeat_result.get('last_heartbeat')}\n"

        f"Edad del heartbeat: "
        f"{heartbeat_result.get('age_seconds'):.2f} segundos\n"

        f"Estado registrado: "
        f"{ready_result.get('status')}\n"

        f"IBKR: "
        f"{'CONECTADO' if ready_result.get('ibkr_connected') else 'DESCONECTADO'}\n"

        f"Gmail: "
        f"{'CONECTADO' if ready_result.get('gmail_connected') else 'DESCONECTADO'}\n\n"

        f"Recuperación automática: "
        f"{'ACTIVADA' if WATCHDOG_AUTO_RECOVER else 'DESACTIVADA'}\n\n"

        "INTERVENCIÓN MANUAL NECESARIA "
        "si el bot no puede recuperarse."
    )

    return send_watchdog_email(
        "DAX BOT - ALERTA: BOT NO RESPONDE",
        body
    )


# ============================================================
# ALERTA RECUPERACIÓN
# ============================================================

def send_recovery_alert(
    recovered
):
    heartbeat_result = (
        recovered["heartbeat"]
    )

    ready_result = (
        recovered["ready"]
    )

    body = (
        "DAX BOT - BOT RECUPERADO\n"
        "========================\n\n"

        "El watchdog ha confirmado la "
        "recuperación completa del bot.\n\n"

        f"Hora de recuperación: "
        f"{utc_now_text()}\n\n"

        f"Heartbeat: "
        f"{heartbeat_result.get('last_heartbeat')}\n"

        f"Edad heartbeat: "
        f"{heartbeat_result.get('age_seconds'):.2f} segundos\n"

        f"Estado: "
        f"{ready_result.get('status')}\n"

        f"IBKR: "
        f"{'CONECTADO' if ready_result.get('ibkr_connected') else 'DESCONECTADO'}\n"

        f"Gmail: "
        f"{'CONECTADO' if ready_result.get('gmail_connected') else 'DESCONECTADO'}\n\n"

        "El bot vuelve a estar READY."
    )

    return send_watchdog_email(
        "DAX BOT - BOT RECUPERADO",
        body
    )


# ============================================================
# RECUPERACIÓN
# ============================================================

def recover_bot():
    print()
    print(
        "########################################"
    )
    print(
        "     INICIANDO RECUPERACIÓN DEL BOT"
    )
    print(
        "########################################"
    )

    try:
        old_data = load_heartbeat()
        old_heartbeat = old_data.get(
            "last_heartbeat"
        )

    except Exception as error:
        print(
            "No se pudo leer heartbeat anterior:"
        )
        print(
            f"{type(error).__name__}: {error}"
        )
        old_heartbeat = None

    bot_running = (
        is_bot_process_running()
    )

    print(
        f"Proceso bot_auto.py detectado: "
        f"{bot_running}"
    )

    if bot_running:
        print()
        print(
            "Existe una instancia de bot_auto.py."
        )

        info = get_bot_process_info()

        if info.get("info"):
            print(
                info["info"]
            )

        print()
        print(
            "No se iniciará una segunda instancia."
        )

        print(
            "Recuperación cancelada por seguridad."
        )

        return None

    try:
        process = start_bot()

    except Exception as error:
        print()
        print(
            "ERROR iniciando bot:"
        )
        print(
            f"{type(error).__name__}: {error}"
        )
        return None

    print()
    print(
        "Esperando heartbeat nuevo + READY..."
    )

    recovered = wait_for_recovery(
        old_heartbeat
    )

    if recovered is None:
        print()
        print(
            "========================================"
        )
        print(
            "RECUPERACIÓN NO CONFIRMADA"
        )
        print(
            "========================================"
        )
        print(
            f"PID iniciado: {process.pid}"
        )
        return None

    print()
    print(
        "========================================"
    )
    print(
        "BOT RECUPERADO Y READY"
    )
    print(
        "========================================"
    )

    ready_result = recovered["ready"]

    print(
        f"Estado: {ready_result['status']}"
    )

    print(
        f"IBKR: "
        f"{'CONECTADO' if ready_result['ibkr_connected'] else 'DESCONECTADO'}"
    )

    print(
        f"Gmail: "
        f"{'CONECTADO' if ready_result['gmail_connected'] else 'DESCONECTADO'}"
    )

    return recovered


# ============================================================
# ESTADO WATCHDOG
# ============================================================

def print_status(
    result,
    consecutive_timeouts
):
    ready_result = check_bot_ready()

    print()
    print(
        "========================================"
    )
    print(
        "              WATCHDOG"
    )
    print(
        "========================================"
    )

    print(
        f"Hora: {utc_now_text()}"
    )

    print(
        f"Estado bot: "
        f"{ready_result['status']}"
    )

    print(
        f"IBKR: "
        f"{'CONECTADO' if ready_result['ibkr_connected'] else 'DESCONECTADO'}"
    )

    print(
        f"Gmail: "
        f"{'CONECTADO' if ready_result['gmail_connected'] else 'DESCONECTADO'}"
    )

    print(
        f"READY: "
        f"{'SI' if ready_result['ready'] else 'NO'}"
    )

    print(
        f"Heartbeat: "
        f"{'OK' if result['alive'] else 'TIMEOUT'}"
    )

    print(
        f"Edad heartbeat: "
        f"{result['age_seconds']:.2f} s"
    )

    print(
        f"Timeout: "
        f"{result['timeout_seconds']:.2f} s"
    )

    print(
        f"Time-outs consecutivos: "
        f"{consecutive_timeouts}/"
        f"{REQUIRED_TIMEOUTS}"
    )

    print(
        f"Último heartbeat: "
        f"{result['last_heartbeat']}"
    )

    print()

    if result["alive"]:
        print(
            "RESULTADO: BOT VIVO"
        )

    elif (
        consecutive_timeouts
        >= REQUIRED_TIMEOUTS
    ):
        print(
            "RESULTADO: BOT NO RESPONDE CONFIRMADO"
        )

    else:
        print(
            "RESULTADO: TIMEOUT NO CONFIRMADO"
        )

    print(
        "========================================"
    )


# ============================================================
# WATCHDOG PRINCIPAL
# ============================================================

def watchdog_loop():
    print()
    print(
        "========================================"
    )
    print(
        "         DAX BOT WATCHDOG"
    )
    print(
        "========================================"
    )

    print(
        f"Heartbeat: {HEARTBEAT_FILE}"
    )

    print(
        f"Bot script: {BOT_SCRIPT}"
    )

    print(
        f"Heartbeat timeout: "
        f"{HEARTBEAT_TIMEOUT} s"
    )

    print(
        f"Comprobación: "
        f"{WATCHDOG_INTERVAL} s"
    )

    print(
        f"Timeouts necesarios: "
        f"{REQUIRED_TIMEOUTS}"
    )

    print(
        f"Auto recovery: "
        f"{'ON' if WATCHDOG_AUTO_RECOVER else 'OFF'}"
    )

    print()

    print(
        "Watchdog iniciado."
    )

    consecutive_timeouts = 0
    last_recovery_attempt = 0.0

    incident_active = False
    failure_alert_sent = False

    while True:

        try:

            result = check_heartbeat()

            if result["alive"]:

                consecutive_timeouts = 0

                print_status(
                    result,
                    consecutive_timeouts
                )

                if incident_active:

                    ready_result = (
                        check_bot_ready()
                    )

                    if ready_result["ready"]:

                        recovery_data = {
                            "heartbeat":
                                result,
                            "ready":
                                ready_result
                        }

                        if send_recovery_alert(
                            recovery_data
                        ):

                            print(
                                "WATCHDOG | "
                                "Correo de recuperación enviado."
                            )

                        incident_active = False
                        failure_alert_sent = False

            else:

                consecutive_timeouts += 1

                if (
                    consecutive_timeouts
                    > REQUIRED_TIMEOUTS
                ):

                    consecutive_timeouts = (
                        REQUIRED_TIMEOUTS
                    )

                print_status(
                    result,
                    consecutive_timeouts
                )

                if (
                    consecutive_timeouts
                    >= REQUIRED_TIMEOUTS
                ):

                    ready_result = (
                        check_bot_ready()
                    )

                    incident_active = True

                    if not failure_alert_sent:

                        if send_failure_alert(
                            result,
                            ready_result
                        ):

                            failure_alert_sent = True

                    if WATCHDOG_AUTO_RECOVER:

                        now = time.time()

                        cooldown_finished = (
                            now
                            - last_recovery_attempt
                            >= RESTART_COOLDOWN
                        )

                        if cooldown_finished:

                            print()
                            print(
                                "BOT NO RESPONDE CONFIRMADO."
                            )

                            print(
                                "Iniciando recuperación..."
                            )

                            last_recovery_attempt = now

                            recovered = (
                                recover_bot()
                            )

                            if recovered is not None:

                                print()
                                print(
                                    "Recuperación completada."
                                )

                                # Evitamos que se envíe
                                # dos veces la alerta de
                                # recuperación.
                                send_recovery_alert(
                                    recovered
                                )

                                incident_active = False
                                failure_alert_sent = False
                                consecutive_timeouts = 0

                            else:

                                print()
                                print(
                                    "Recuperación no confirmada."
                                )

                                consecutive_timeouts = 0

                    else:

                        print()
                        print(
                            "AUTO RECOVERY DESACTIVADA."
                        )

                        print(
                            "Intervención manual necesaria."
                        )

                        consecutive_timeouts = (
                            REQUIRED_TIMEOUTS
                        )

        except Exception as error:

            print()
            print(
                "========================================"
            )
            print(
                "WATCHDOG ERROR"
            )
            print(
                "========================================"
            )
            print(
                f"{type(error).__name__}: {error}"
            )
            print(
                "RESULTADO: NO SE PUEDE DETERMINAR "
                "EL ESTADO DEL BOT"
            )

        time.sleep(
            WATCHDOG_INTERVAL
        )


# ============================================================
# INICIO
# ============================================================

if __name__ == "__main__":

    try:
        watchdog_loop()

    except KeyboardInterrupt:

        print()
        print(
            "Watchdog detenido manualmente."
        )
