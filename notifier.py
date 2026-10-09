import threading
import os
from typing import List, Optional

def _async_toast(title: str, message: str, icon: Optional[str] = None):
    try:
        from win11toast import toast
        # Run toast in thread so it doesn't block the caller
        toast(title, message, icon=icon, duration='long')
    except Exception as e:
        # Fallback to PowerShell balloon / toast if win11toast fails
        try:
            import subprocess
            escaped_title = title.replace('"', '`"')
            escaped_msg = message.replace('"', '`"')
            ps_script = f"""
            [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
            $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
            $textNodes = $template.GetElementsByTagName("text")
            $textNodes.Item(0).AppendChild($template.CreateTextNode("{escaped_title}")) > $null
            $textNodes.Item(1).AppendChild($template.CreateTextNode("{escaped_msg}")) > $null
            $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("VALORANT Skin Alarm")
            $notification = [Windows.UI.Notifications.ToastNotification]::new($template)
            $notifier.Show($notification)
            """
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True)
        except Exception:
            pass

def send_notification(title: str, message: str, icon_path: Optional[str] = None):
    """Sends a desktop notification asynchronously."""
    thread = threading.Thread(target=_async_toast, args=(title, message, icon_path), daemon=True)
    thread.start()

def notify_wishlist_match(skin_names: List[str]):
    """Sends notification when tracked skins are detected in the daily store."""
    if not skin_names:
        return
    title = "🎯 Будильник скинов VALORANT!"
    if len(skin_names) == 1:
        message = f"В вашем магазине появился скин: {skin_names[0]}! Успейте забрать."
    else:
        skins_str = ", ".join(skin_names)
        message = f"В магазине появились скины из вишлиста: {skins_str}!"
    send_notification(title, message)

def send_test_notification():
    """Sends a test notification to verify system toast functionality."""
    send_notification(
        "🔔 Будильник скинов VALORANT",
        "Уведомления успешно работают! Вы получите оповещение, как только скин из вишлиста появится в магазине."
    )
