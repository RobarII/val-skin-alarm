import sys
import argparse

def main():
    parser = argparse.ArgumentParser(description="VALORANT Skin Alarm - Будильник скинов")
    parser.add_argument(
        "--daemon", "-d",
        action="store_true",
        help="Запустить в фоновом режиме (демон для автозагрузки Windows)"
    )
    parser.add_argument(
        "--test-toast",
        action="store_true",
        help="Отправить тестовое уведомление Windows и выйти"
    )

    args = parser.parse_args()

    if args.test_toast:
        from notifier import send_test_notification
        import time
        print("Отправка тестового уведомления Windows...")
        send_test_notification()
        time.sleep(2)
        print("Уведомление отправлено.")
        return 0

    if args.daemon:
        from daemon import run_daemon_check
        # Runs silent background check on system boot
        return run_daemon_check()

    # Default: Graphical User Interface
    from ui.app import ValorantAlarmApp
    app = ValorantAlarmApp()
    app.mainloop()
    return 0

if __name__ == "__main__":
    sys.exit(main())
