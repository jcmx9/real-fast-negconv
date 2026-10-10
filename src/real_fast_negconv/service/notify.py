"""Desktop notification at the end of a batch (best effort, per OS)."""

import logging
import shutil
import subprocess
import sys

from real_fast_negconv.service.batch import BatchResult, problem_message
from real_fast_negconv.service.daemon import Runner

log = logging.getLogger(__name__)

POWERSHELL_APP_ID = (
    r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
)


def summary_message(result: BatchResult) -> tuple[str, str]:
    """Title and German message for the end user."""
    message = f"{len(result.succeeded)} Fotos fertig, {len(result.failed)} Fehler"
    problem = problem_message(result)
    if problem is not None:
        message = f"{message}. {problem}"
    return "rfnegconv", message


def notification_command(title: str, message: str, platform: str) -> list[str] | None:
    """OS-specific command showing a notification, or None if unavailable."""
    if platform == "darwin":
        msg = _applescript(message)
        ttl = _applescript(title)
        script = f"display notification {msg} with title {ttl}"
        return ["osascript", "-e", script]
    if platform.startswith("linux"):
        executable = shutil.which("notify-send")
        return [executable, "--", title, message] if executable else None
    if platform == "win32":
        title_ps = _powershell(title)
        message_ps = _powershell(message)
        app_id_ps = _powershell(POWERSHELL_APP_ID)
        mgr = "[Windows.UI.Notifications.ToastNotificationManager"
        notify = "Windows.UI.Notifications"
        template = "[Windows.UI.Notifications.ToastTemplateType]::ToastText02"
        script = (
            f"{mgr}, {notify}, ContentType = WindowsRuntime] | Out-Null; "
            f"$t = {mgr}]::GetTemplateContent({template}); "
            "$x = $t.GetElementsByTagName('text'); "
            f"$x.Item(0).AppendChild($t.CreateTextNode({title_ps})) | "
            "Out-Null; "
            f"$x.Item(1).AppendChild($t.CreateTextNode({message_ps})) | "
            "Out-Null; "
            f"{mgr}]::CreateToastNotifier({app_id_ps}).Show("
            "[Windows.UI.Notifications.ToastNotification]::new($t))"
        )
        return ["powershell", "-NoProfile", "-NonInteractive", "-Command", script]
    return None


def notify(
    title: str,
    message: str,
    *,
    platform: str = sys.platform,
    runner: Runner = subprocess.run,
) -> None:
    """Show a notification; failures are only logged."""
    command = notification_command(title, message, platform)
    if command is None:
        return
    try:
        runner(command, check=True, capture_output=True, timeout=10)
    except Exception as exc:  # Best-effort: any failure (e.g., ValueError)
        log.warning("notification failed: %s", exc)


def _applescript(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _powershell(text: str) -> str:
    # Escape both ASCII and typographic single quotes
    for quote in (chr(39), "\u2018", "\u2019", "\u201a", "\u201b"):
        text = text.replace(quote, quote + quote)
    return chr(39) + text + chr(39)
