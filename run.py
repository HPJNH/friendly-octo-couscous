import webbrowser
from threading import Timer

from app import create_app


app = create_app()


def local_url() -> str:
    return f"http://127.0.0.1:{app.config['PORT']}"


def lan_url() -> str:
    lan_host = app.config.get("LAN_ACCESS_HOST") or app.config["HOST"]
    return f"http://{lan_host}:{app.config['PORT']}"


def open_browser() -> None:
    webbrowser.open_new(local_url())


def print_startup_banner() -> None:
    print()
    print("=" * 72)
    print(f"{app.config['PROJECT_NAME']} 已启动")
    print(f"本机访问地址：{local_url()}")
    print(f"局域网访问地址：{lan_url()}")
    print("说明：如果手机无法访问，请确认电脑与手机位于同一 Wi-Fi / 局域网，并检查 Windows 防火墙是否已放行该端口。")
    print("=" * 72)
    print()


if __name__ == "__main__":
    print_startup_banner()
    Timer(1.2, open_browser).start()
    app.run(host=app.config["HOST"], port=app.config["PORT"], debug=False, use_reloader=False)
