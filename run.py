import webbrowser
from threading import Timer

from app import create_app


app = create_app()


def local_url(flask_app) -> str:
    return f"http://127.0.0.1:{flask_app.config['PORT']}"


def lan_url(flask_app) -> str:
    lan_host = flask_app.config.get("LAN_ACCESS_HOST") or flask_app.config["HOST"]
    return f"http://{lan_host}:{flask_app.config['PORT']}"


def should_auto_open_browser(app_env: str) -> bool:
    return str(app_env or "").strip().lower() == "local"


def open_browser(flask_app) -> None:
    webbrowser.open_new(local_url(flask_app))


def print_startup_banner(flask_app) -> None:
    app_env = flask_app.config.get("APP_ENV", "local")
    print()
    print("=" * 72)
    if app_env == "local":
        print(f"{flask_app.config['PROJECT_NAME']} 已启动（local 模式）")
        print(f"本地入口：{flask_app.config.get('LOCAL_ENTRYPOINT', 'python run.py')}")
        print(f"本机访问地址：{local_url(flask_app)}")
        print(f"局域网访问地址：{lan_url(flask_app)}")
        print("说明：run.py 仅保留本地调试语义，会自动打开浏览器。")
    else:
        print(f"{flask_app.config['PROJECT_NAME']} 启动中（production 模式）")
        print(f"推荐服务器入口：{flask_app.config.get('SERVER_ENTRYPOINT', 'wsgi:app')}")
        print(f"Host: {flask_app.config['HOST']}  Port: {flask_app.config['PORT']}")
        print(f"Runtime root: {flask_app.config['APP_RUNTIME_ROOT']}")
        print("说明：production 场景请通过服务器入口运行，而不是继续依赖本地桌面入口。")
    print("=" * 72)
    print()


if __name__ == "__main__":
    print_startup_banner(app)
    if should_auto_open_browser(app.config.get("APP_ENV")):
        Timer(1.2, lambda: open_browser(app)).start()
    app.run(host=app.config["HOST"], port=app.config["PORT"], debug=False, use_reloader=False)
