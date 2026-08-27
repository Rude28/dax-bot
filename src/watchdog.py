import json
import os
import subprocess
import sys
import time

from datetime import datetime, timezone


# ============================================================
# CONFIGURACIÓN
# ============================================================

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

# ------------------------------------------------------------
# HEARTBEAT
# ------------------------------------------------------------

HEARTBEAT_TIMEOUT = 30.0

# ------------------------------------------------------------
# WATCHDOG
# ------------------------------------------------------------

WATCHDOG_INTERVAL = 5.0

# Número de timeouts consecutivos para confirmar caída.
REQUIRED_TIMEOUTS = 2

# ------------------------------------------------------------
# RECUPERACIÓN
# ------------------------------------------------------------

RECOVERY_TIMEOUT = 90.0
RECOVERY_CHECK_INTERVAL = 5.0

# Tiempo mínimo entre intentos de recuperación.
RESTART_COOLDOWN = 30.0


# ============================================================
# UTILIDADES DE TIEMPO
# ============================================================

def parse_timestamp(timestamp):
    if not timestamp:
        raise RuntimeError(
            "El heartbeat no contiene last_heartbeat."
        )

    try:
        parsed = datetime.fromisoformat(str(timestamp))
    except ValueError as error:
        raise RuntimeError(
            f"Timestamp heartbeat inválido: {timestamp}"
        ) from error

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


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
            f"No existe el archivo heartbeat: {HEARTBEAT_FILE}"
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
# LEER ESTADO DEL BOT
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
            f"No existe el archivo de estado: {STATUS_FILE}"
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
            "bot_status.json no contiene un objeto JSON válido."
        )

    return data


# ============================================================
# COMPROBAR HEARTBEAT
# ============================================================

def check_heartbeat(timeout=HEARTBEAT_TIMEOUT):
    data = load_heartbeat()

    last_heartbeat = parse_timestamp(
        data.get("last_heartbeat")
    )

    last_cycle = data.get("last_cycle")
    heartbeat_status = data.get(
        "status",
        "UNKNOWN"
    )

    now = datetime.now(timezone.utc)

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
# COMPROBAR READY REAL
# ============================================================

def check_bot_ready():
    """
    La recuperación no se considera completa solo porque
    aparezca un heartbeat nuevo.

    Exigimos además:
      - status == READY
      - IBKR conectado
      - Gmail conectado
    """

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
# COMPROBAR PROCESO ESPECÍFICO BOT_AUTO.PY
# ============================================================

def _query_python_processes():
    """
    Obtiene las líneas de comando de procesos python.exe.

    Primero intenta WMIC y, si no está disponible, PowerShell.
    """

    try:
        result = subprocess.run(
            [
                "wmic",
                "process",
                "where",
                "name='python.exe'",
                "get",
                "ProcessId,CommandLine",
                "/format:list",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

        return result.stdout or ""

    except FileNotFoundError:
        pass

    except Exception:
        return ""

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
                ),
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
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


# ============================================================
# INFORMACIÓN DEL PROCESO BOT
# ============================================================

def get_bot_process_info():
    output = _query_python_processes()

    matching_lines = []

    for line in output.splitlines():
        if BOT_SCRIPT_NAME.lower() in line.lower():
            matching_lines.append(line)

    return {
        "running": bool(matching_lines),
        "info": "\n".join(matching_lines) or None,
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
            script_path,
        ],
        cwd=project_dir,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
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
    """
    La recuperación solo se confirma cuando:

      1. El heartbeat cambia.
      2. El heartbeat está reciente.
      3. bot_status.json indica READY.
      4. IBKR está conectado.
      5. Gmail está conectado.
    """

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
                current_heartbeat != old_heartbeat
            )

            heartbeat_ok = (
                heartbeat_result["alive"]
                and heartbeat_changed
            )

        except Exception:
            heartbeat_result = None

        ready_result = check_bot_ready()

        print(
            "RECOVERY CHECK | "
            f"Heartbeat={'OK' if heartbeat_ok else 'NO'} | "
            f"READY={'YES' if ready_result['ready'] else 'NO'} | "
            f"IBKR={'OK' if ready_result['ibkr_connected'] else 'NO'} | "
            f"Gmail={'OK' if ready_result['gmail_connected'] else 'NO'}"
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

    # --------------------------------------------------------
    # Heartbeat anterior
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # El bot debe estar realmente ausente.
    # --------------------------------------------------------

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
            "No se iniciará una segunda instancia "
            "automáticamente."
        )
        print(
            "Recuperación cancelada por seguridad."
        )

        return False

    # --------------------------------------------------------
    # Arrancar
    # --------------------------------------------------------

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
        return False

    # --------------------------------------------------------
    # Esperar heartbeat + READY
    # --------------------------------------------------------

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
        print(
            "No se alcanzó READY con "
            "IBKR y Gmail conectados dentro "
            "del tiempo esperado."
        )
        return False

    heartbeat_result = recovered["heartbeat"]
    ready_result = recovered["ready"]

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
    print(
        f"Heartbeat nuevo: "
        f"{heartbeat_result['last_heartbeat']}"
    )
    print(
        f"Edad heartbeat: "
        f"{heartbeat_result['age_seconds']:.2f} s"
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

    return True


# ============================================================
# MOSTRAR ESTADO
# ============================================================

def print_status(
    result,
    consecutive_timeouts
):
    current_time = (
        datetime.now(
            timezone.utc
        ).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
    )

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
        f"Hora: {current_time}"
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
            "RESULTADO: BOT NO RESPONDE "
            "CONFIRMADO"
        )

    else:
        print(
            "RESULTADO: TIMEOUT "
            "NO CONFIRMADO"
        )

    print(
        "========================================"
    )


# ============================================================
# WATCHDOG
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
        f"Estado: {STATUS_FILE}"
    )
    print(
        f"Bot script: {BOT_SCRIPT}"
    )
    print(
        f"Timeout: {HEARTBEAT_TIMEOUT} segundos"
    )
    print(
        f"Comprobación cada "
        f"{WATCHDOG_INTERVAL} segundos"
    )
    print(
        f"Timeouts necesarios: "
        f"{REQUIRED_TIMEOUTS}"
    )
    print(
        f"Recovery timeout: "
        f"{RECOVERY_TIMEOUT} segundos"
    )
    print()
    print(
        "Watchdog iniciado."
    )

    consecutive_timeouts = 0
    last_restart = 0.0

    while True:
        try:
            result = check_heartbeat()

            if result["alive"]:
                consecutive_timeouts = 0
                print_status(
                    result,
                    consecutive_timeouts
                )

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
                    now = time.time()

                    cooldown_finished = (
                        now - last_restart
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

                        success = recover_bot()

                        last_restart = now

                        if success:
                            print()
                            print(
                                "Recuperación completada."
                            )
                        else:
                            print()
                            print(
                                "Recuperación no confirmada."
                            )

                        consecutive_timeouts = 0

                    else:
                        print()
                        print(
                            "Recovery cooldown activo."
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
