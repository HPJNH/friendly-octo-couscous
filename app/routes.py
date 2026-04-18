import math

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, url_for

from .admin_auth import (
    access_control_enabled,
    access_required,
    admin_required,
    build_safe_next,
    change_access_identity_code,
    clear_access_session,
    create_access_identity,
    current_access_label,
    current_access_role,
    current_access_session,
    generate_access_code,
    get_access_management_view,
    get_current_access_identity,
    is_access_verified,
    is_admin_verified,
    update_access_identity_status,
    verify_access_secret,
)
from .constants import SECTION_DEFINITIONS
from .mark_service import deactivate_entry_mark, upsert_entry_mark
from .security import (
    clear_auth_failures,
    csrf_input,
    get_auth_lock_state,
    get_csrf_token,
    get_request_csrf_token,
    log_audit_event,
    register_auth_failure,
    validate_csrf_token,
)
from .services import (
    activate_document,
    create_day_pdf_export,
    delete_document,
    delete_export_file,
    get_day_snapshot,
    get_document_download_path,
    get_document_library_detail,
    get_export_download_path,
    get_export_library_detail,
    get_file_library_view,
    get_history_overview,
    get_layout_context,
    get_latest_report_date,
    get_recent_days,
    get_section_debug_view,
    get_section_detail,
    process_uploaded_files,
    withdraw_document,
)
from .utils import today_string


bp = Blueprint("main", __name__)


def _resolve_display_name() -> str:
    payload = current_access_session() or {}
    candidates = [
        payload.get("display_name"),
        payload.get("name"),
        payload.get("label"),
    ]
    blocked_keywords = ("Bootstrap", "访问码", "管理员")
    blocked_values = {"未验证", "guest", "viewer", "admin"}
    for value in candidates:
        text = str(value or "").strip()
        if not text:
            continue
        if text in blocked_values:
            continue
        if any(keyword in text for keyword in blocked_keywords):
            continue
        return text
    return ""


def _csrf_redirect_target(endpoint: str) -> str:
    mapping = {
        "main.access_login": url_for("main.access_login"),
        "main.admin_verify": url_for("main.admin_verify"),
        "main.access_manage": url_for("main.access_manage"),
        "main.access_manage_action": url_for("main.access_manage"),
        "main.access_change_code": url_for("main.access_change_code"),
        "main.upload": url_for("main.upload"),
        "main.access_logout": url_for("main.index"),
    }
    return mapping.get(endpoint, build_safe_next(request.referrer, url_for("main.index")))


def _lock_message(scope: str, state: dict) -> dict:
    minutes = max(1, math.ceil((state.get("remaining_seconds") or 0) / 60))
    title = "访问验证已临时锁定" if scope == "access_login" else "管理验证已临时锁定"
    return {
        "title": title,
        "body": f"当前设备连续失败次数过多，请在 {minutes} 分钟后重试。",
    }


@bp.context_processor
def inject_globals():
    access_session = current_access_session()
    return {
        "project_name": current_app.config["PROJECT_NAME"],
        "brand_name": current_app.config["BRAND_NAME"],
        "product_subtitle": current_app.config["PRODUCT_SUBTITLE"],
        "brand_slogan": current_app.config["BRAND_SLOGAN"],
        "section_catalog": SECTION_DEFINITIONS,
        "access_control_enabled": access_control_enabled(),
        "access_verified": is_access_verified(),
        "access_role": current_access_role(),
        "access_label": current_access_label(),
        "access_session": access_session,
        "admin_verified": is_admin_verified(),
        "display_name": _resolve_display_name(),
        "can_change_access_code": bool((access_session or {}).get("identity_id")),
        "max_upload_size_mb": current_app.config["MAX_CONTENT_LENGTH_MB"],
        "csrf_token": get_csrf_token,
        "csrf_input": csrf_input,
    }


@bp.before_app_request
def enforce_csrf():
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    endpoint = request.endpoint or ""
    if endpoint.startswith("static"):
        return None
    if validate_csrf_token(get_request_csrf_token()):
        return None
    flash(
        {
            "title": "请求已失效",
            "body": "表单安全令牌已失效或缺失，请刷新页面后重新提交。",
        },
        "error",
    )
    return redirect(_csrf_redirect_target(endpoint))


@bp.before_app_request
def enforce_access_control():
    if not access_control_enabled():
        return None
    endpoint = request.endpoint or ""
    if endpoint.startswith("static"):
        return None
    if endpoint in {
        "main.access_login",
        "main.admin_verify",
        "main.access_logout",
        "main.handle_file_too_large",
    }:
        return None
    if is_access_verified():
        return None
    return redirect(url_for("main.access_login", next=build_safe_next(request.full_path.rstrip("?"), url_for("main.index"))))


@bp.app_errorhandler(413)
def handle_file_too_large(_error):
    flash(
        {
            "title": "上传失败",
            "body": f"文件超过 {current_app.config['MAX_CONTENT_LENGTH_MB']}MB 上限，请压缩后重试。",
        },
        "error",
    )
    return redirect(build_safe_next(request.referrer, url_for("main.upload")))


@bp.route("/access/login", methods=["GET", "POST"])
def access_login():
    next_url = build_safe_next(request.values.get("next"), url_for("main.index"))
    if request.method == "POST":
        lock_state = get_auth_lock_state("access_login")
        if lock_state["locked"]:
            flash(_lock_message("access_login", lock_state), "error")
            return redirect(url_for("main.access_login", next=next_url))

        secret = request.form.get("access_secret", "")
        verified, reason = verify_access_secret(secret, required_role="viewer")
        if verified:
            clear_auth_failures("access_login")
            flash({"title": "访问验证通过", "body": "当前浏览器会话已通过访问验证，可以继续浏览系统。"}, "success")
            return redirect(next_url)

        state = register_auth_failure("access_login")
        if state["locked"]:
            flash(_lock_message("access_login", state), "error")
            return redirect(url_for("main.access_login", next=next_url))

        body = "访问码不正确，或该访问资格已停用。"
        if reason == "role-denied":
            body = "这串访问码存在，但权限不足，不能进入当前页面。"
        flash({"title": "访问验证失败", "body": body}, "error")
    layout = get_layout_context()
    return render_template("access_login.html", next_url=next_url, current_page="access", mode="access", **layout)


@bp.route("/admin/verify", methods=["GET", "POST"])
def admin_verify():
    next_url = build_safe_next(request.values.get("next"), url_for("main.upload"))
    if request.method == "POST":
        lock_state = get_auth_lock_state("admin_verify")
        if lock_state["locked"]:
            flash(_lock_message("admin_verify", lock_state), "error")
            return redirect(url_for("main.admin_verify", next=next_url))

        secret = request.form.get("access_secret", "")
        verified, reason = verify_access_secret(secret, required_role="admin")
        if verified:
            clear_auth_failures("admin_verify")
            flash({"title": "管理权限已解锁", "body": "当前浏览器会话已具备管理员权限。"}, "success")
            return redirect(next_url)

        state = register_auth_failure("admin_verify")
        if state["locked"]:
            flash(_lock_message("admin_verify", state), "error")
            return redirect(url_for("main.admin_verify", next=next_url))

        body = "管理员访问码不正确。"
        if reason == "role-denied":
            body = "这串访问码只能浏览，不能执行管理操作。"
        flash({"title": "管理验证失败", "body": body}, "error")
    layout = get_layout_context()
    return render_template("admin_verify.html", next_url=next_url, current_page="admin", **layout)


@bp.route("/access/logout", methods=["POST"])
def access_logout():
    log_audit_event(
        action="access.logout",
        target_type="session",
        target_label="current-session",
        actor=current_access_session(),
    )
    clear_access_session()
    flash({"title": "已退出访问会话", "body": "当前浏览器需要重新输入访问码或管理员口令后才能继续进入系统。"}, "success")
    return redirect(url_for("main.access_login"))


@bp.route("/access/manage", methods=["GET", "POST"])
@admin_required
def access_manage():
    generated_code = ""
    if request.method == "POST":
        label = request.form.get("label", "")
        role = request.form.get("role", "viewer")
        notes = request.form.get("notes", "")
        raw_code = request.form.get("raw_code", "").strip()
        if request.form.get("generate_code") == "yes" and not raw_code:
            raw_code = generate_access_code()
            generated_code = raw_code
        try:
            result = create_access_identity(label, raw_code, role, notes)
            log_audit_event(
                action="access_identity.create",
                target_type="access_identity",
                target_id=result["id"],
                target_label=result["label"],
                detail={"role": result["role"], "generated_code": bool(generated_code)},
                actor=current_access_session(),
            )
            flash(
                {
                    "title": "访问资格已创建",
                    "body": f"{result['label']} 已创建为 {result['role']} 权限，请妥善保存访问码：{raw_code}",
                },
                "success",
            )
            return redirect(url_for("main.access_manage"))
        except ValueError as error:
            flash({"title": "创建失败", "body": str(error)}, "error")

    layout = get_layout_context()
    return render_template(
        "access_manage.html",
        access_view=get_access_management_view(),
        generated_code=generated_code,
        current_page="access_manage",
        **layout,
    )


@bp.route("/access/change-code", methods=["GET", "POST"])
@access_required
def access_change_code():
    identity = get_current_access_identity()
    if not identity:
        flash({"title": "访问资格已失效", "body": "请重新验证访问码后再修改当前访问码。"}, "error")
        return redirect(url_for("main.access_login", next=build_safe_next(url_for("main.access_change_code"))))

    if request.method == "POST":
        try:
            result = change_access_identity_code(
                identity["id"],
                request.form.get("current_code", ""),
                request.form.get("new_code", ""),
                request.form.get("confirm_new_code", ""),
            )
            log_audit_event(
                action="access_identity.change_code",
                target_type="access_identity",
                target_id=result["id"],
                target_label=result["label"],
                detail={"role": result["role"]},
                actor=current_access_session(),
            )
            flash({"title": "访问码已更新", "body": "新的访问码已经生效，请在后续会话中使用新访问码登录。"}, "success")
            return redirect(url_for("main.access_change_code"))
        except ValueError as error:
            flash({"title": "修改失败", "body": str(error)}, "error")

    layout = get_layout_context()
    return render_template(
        "access_change_code.html",
        current_identity=identity,
        current_page="access_change",
        **layout,
    )


@bp.route("/access/manage/<int:identity_id>/<action>", methods=["POST"])
@admin_required
def access_manage_action(identity_id: int, action: str):
    target_status = {"disable": "disabled", "activate": "active", "delete": "deleted"}.get(action)
    if not target_status:
        abort(404)
    try:
        result = update_access_identity_status(identity_id, target_status)
        log_audit_event(
            action=f"access_identity.{action}",
            target_type="access_identity",
            target_id=result["id"],
            target_label=result["label"],
            detail={"status": result["status"]},
            actor=current_access_session(),
        )
        flash({"title": "访问资格已更新", "body": f"{result['label']} 当前状态已切换为 {result['status']}。"}, "success")
    except ValueError as error:
        flash({"title": "操作失败", "body": str(error)}, "error")
    return redirect(url_for("main.access_manage"))


@bp.route("/")
@access_required
def index():
    report_date = get_latest_report_date() or today_string()
    return render_day_page(report_date, is_home=True)


@bp.route("/day/<report_date>")
@access_required
def day(report_date: str):
    return render_day_page(report_date, is_home=False)


def render_day_page(report_date: str, is_home: bool):
    access_identity = get_current_access_identity()
    snapshot = get_day_snapshot(
        report_date,
        viewer_identity_id=access_identity["id"] if access_identity else None,
        viewer_role=access_identity["role"] if access_identity else current_access_role(),
    )
    layout = get_layout_context(report_date)
    return render_template(
        "day.html",
        snapshot=snapshot,
        recent_days=get_recent_days(),
        current_page="home",
        is_home=is_home,
        **layout,
    )


@bp.route("/export/pdf/<report_date>")
@access_required
def export_day_pdf(report_date: str):
    next_url = sanitize_next_url(request.args.get("next"), report_date)
    try:
        result = create_day_pdf_export(report_date)
    except ValueError as error:
        flash({"title": "PDF 导出失败", "body": str(error)}, "error")
        return redirect(next_url)

    flash(
        {
            "title": "PDF 导出成功",
            "body": f"已生成 {result['filename']}",
            "download_url": url_for("main.download_day_pdf", report_date=report_date),
        },
        "success",
    )
    return redirect(next_url)


@bp.route("/download/pdf/<report_date>")
@access_required
def download_day_pdf(report_date: str):
    result = create_day_pdf_export(report_date)
    return send_file(
        result["download_path"],
        as_attachment=True,
        download_name=result["filename"],
        mimetype="application/pdf",
    )


@bp.route("/history")
@access_required
def history():
    layout = get_layout_context()
    return render_template(
        "history.html",
        history_days=get_history_overview(limit=60),
        current_page="history",
        **layout,
    )


@bp.route("/upload", methods=["GET", "POST"])
@admin_required
def upload():
    results = []
    if request.method == "POST":
        files = [file for file in request.files.getlist("files") if file and file.filename]
        if not files:
            flash({"title": "尚未选择文件", "body": "请选择至少一个文件后再上传。"}, "error")
        else:
            results = process_uploaded_files(files)
            success_count = len([item for item in results if item.success])
            if success_count:
                log_audit_event(
                    action="document.upload",
                    target_type="upload_batch",
                    target_label=f"{success_count}-success",
                    detail={"success_count": success_count, "file_count": len(results)},
                    actor=current_access_session(),
                )

    layout = get_layout_context()
    return render_template(
        "upload.html",
        upload_results=results,
        recent_days=get_recent_days(limit=12),
        current_page="upload",
        **layout,
    )


@bp.route("/library")
@access_required
def library():
    layout = get_layout_context()
    return render_template(
        "library.html",
        library_view=get_file_library_view(),
        current_page="library",
        **layout,
    )


@bp.route("/library/document/<int:document_id>")
@access_required
def library_document_detail(document_id: int):
    detail = get_document_library_detail(document_id)
    if not detail:
        abort(404)
    layout = get_layout_context(detail["report_date"])
    return render_template(
        "library_detail.html",
        detail=detail,
        current_page="library",
        **layout,
    )


@bp.route("/library/export/<int:export_id>")
@access_required
def library_export_detail(export_id: int):
    detail = get_export_library_detail(export_id)
    if not detail:
        abort(404)
    layout = get_layout_context(detail["report_date"])
    return render_template(
        "library_detail.html",
        detail=detail,
        current_page="library",
        **layout,
    )


@bp.route("/library/document/<int:document_id>/withdraw", methods=["POST"])
@admin_required
def library_document_withdraw(document_id: int):
    next_url = sanitize_absolute_next(request.form.get("next"))
    try:
        result = withdraw_document(document_id)
        log_audit_event(
            action="document.withdraw",
            target_type="document",
            target_id=document_id,
            target_label=result["name"],
            detail={"report_date": result["report_date"], "doc_type": result["doc_type"]},
            actor=current_access_session(),
        )
        flash(
            {
                "title": "文件已撤回",
                "body": f"{result['name']} 已撤回，不再参与当前展示与新增判断。",
            },
            "success",
        )
    except ValueError as error:
        flash({"title": "撤回失败", "body": str(error)}, "error")
    return redirect(next_url or url_for("main.library"))


@bp.route("/library/document/<int:document_id>/activate", methods=["POST"])
@admin_required
def library_document_activate(document_id: int):
    next_url = sanitize_absolute_next(request.form.get("next"))
    try:
        result = activate_document(document_id)
        log_audit_event(
            action="document.activate",
            target_type="document",
            target_id=document_id,
            target_label=result["name"],
            detail={"report_date": result["report_date"], "doc_type": result["doc_type"]},
            actor=current_access_session(),
        )
        flash(
            {
                "title": "文件已设为当前生效版本",
                "body": f"{result['name']} 已启用，并已刷新 {result['report_date']} 的展示结果。",
            },
            "success",
        )
    except ValueError as error:
        flash({"title": "启用失败", "body": str(error)}, "error")
    return redirect(next_url or url_for("main.library"))


@bp.route("/library/document/<int:document_id>/delete", methods=["POST"])
@admin_required
def library_document_delete(document_id: int):
    next_url = sanitize_absolute_next(request.form.get("next"))
    try:
        result = delete_document(document_id)
        log_audit_event(
            action="document.delete",
            target_type="document",
            target_id=document_id,
            target_label=result["name"],
            detail={"report_date": result["report_date"], "doc_type": result["doc_type"]},
            actor=current_access_session(),
        )
        flash(
            {
                "title": "文件已删除",
                "body": f"{result['name']} 已从当前可用版本链中移除。",
            },
            "success",
        )
    except ValueError as error:
        flash({"title": "删除失败", "body": str(error)}, "error")
    return redirect(next_url or url_for("main.library"))


@bp.route("/library/export/<int:export_id>/delete", methods=["POST"])
@admin_required
def library_export_delete(export_id: int):
    next_url = sanitize_absolute_next(request.form.get("next"))
    try:
        result = delete_export_file(export_id)
        log_audit_event(
            action="export.delete",
            target_type="export",
            target_id=export_id,
            target_label=result["name"],
            detail={"report_date": result["report_date"]},
            actor=current_access_session(),
        )
        flash({"title": "导出文件已删除", "body": f"{result['name']} 已从文件库移除。"}, "success")
    except ValueError as error:
        flash({"title": "删除失败", "body": str(error)}, "error")
    return redirect(next_url or url_for("main.library"))


@bp.route("/library/document/<int:document_id>/download")
@access_required
def library_document_download(document_id: int):
    try:
        download_path = get_document_download_path(document_id)
    except ValueError as error:
        flash({"title": "下载失败", "body": str(error)}, "error")
        return redirect(url_for("main.library"))
    return send_file(download_path, as_attachment=True, download_name=download_path.name)


@bp.route("/library/export/<int:export_id>/download")
@access_required
def library_export_download(export_id: int):
    try:
        download_path = get_export_download_path(export_id)
    except ValueError as error:
        flash({"title": "下载失败", "body": str(error)}, "error")
        return redirect(url_for("main.library"))
    return send_file(download_path, as_attachment=True, download_name=download_path.name, mimetype="application/pdf")


@bp.route("/section/<report_date>/<section_key>")
@access_required
def section_detail(report_date: str, section_key: str):
    access_identity = get_current_access_identity()
    detail = get_section_detail(
        report_date,
        section_key,
        viewer_identity_id=access_identity["id"] if access_identity else None,
        viewer_role=access_identity["role"] if access_identity else current_access_role(),
    )
    if not detail:
        abort(404)
    layout = get_layout_context(report_date)
    return render_template(
        "section_detail.html",
        detail=detail,
        current_page="section",
        **layout,
    )


@bp.route("/marks/<int:entry_id>/upsert", methods=["POST"])
@access_required
def entry_mark_upsert(entry_id: int):
    identity = get_current_access_identity()
    if not identity:
        flash({"title": "标记失败", "body": "当前访问资格已失效，请重新登录后再试。"}, "error")
        return redirect(sanitize_absolute_next(request.form.get("next")) or url_for("main.index"))

    next_url = sanitize_absolute_next(request.form.get("next")) or request.referrer or url_for("main.index")
    try:
        result = upsert_entry_mark(
            entry_id=entry_id,
            marker_identity_id=identity["id"],
            marker_label=identity["label"],
            marker_role=identity["role"],
            mark_type=request.form.get("mark_type", "focus"),
            note=request.form.get("note", ""),
        )
        log_audit_event(
            action=f"entry_mark.{result['action']}",
            target_type="entry_mark",
            target_id=result["id"],
            target_label=result["entry_title"],
            detail={
                "entry_id": result["entry_id"],
                "module_key": result["module_key"],
                "mark_type": result["mark_type"],
                "has_note": bool(result["note"]),
            },
            actor=current_access_session(),
        )
        flash({"title": "重点标记已保存", "body": "这条情报已加入你的重点提醒，其他成员现在也能看到。"}, "success")
    except ValueError as error:
        flash({"title": "标记失败", "body": str(error)}, "error")
    return redirect(next_url)


@bp.route("/marks/<int:mark_id>/deactivate", methods=["POST"])
@access_required
def entry_mark_deactivate(mark_id: int):
    identity = get_current_access_identity()
    if not identity:
        flash({"title": "取消失败", "body": "当前访问资格已失效，请重新登录后再试。"}, "error")
        return redirect(sanitize_absolute_next(request.form.get("next")) or url_for("main.index"))

    next_url = sanitize_absolute_next(request.form.get("next")) or request.referrer or url_for("main.index")
    try:
        result = deactivate_entry_mark(
            mark_id=mark_id,
            actor_identity_id=identity["id"],
            actor_role=identity["role"],
        )
        log_audit_event(
            action="entry_mark.deactivate",
            target_type="entry_mark",
            target_id=result["id"],
            target_label=result["entry_title"],
            detail={
                "entry_id": result["entry_id"],
                "module_key": result["module_key"],
                "mark_type": result["mark_type"],
            },
            actor=current_access_session(),
        )
        flash({"title": "重点标记已取消", "body": "这条重点提醒已从当前卡片中移除。"}, "success")
    except PermissionError as error:
        flash({"title": "无法取消", "body": str(error)}, "error")
    except ValueError as error:
        flash({"title": "取消失败", "body": str(error)}, "error")
    return redirect(next_url)


@bp.route("/debug/sections/<report_date>")
@admin_required
def debug_sections(report_date: str):
    debug_view = get_section_debug_view(report_date)
    if not debug_view:
        abort(404)
    layout = get_layout_context(report_date)
    return render_template(
        "section_debug.html",
        debug_view=debug_view,
        current_page="debug",
        **layout,
    )


def sanitize_next_url(next_url: str | None, report_date: str) -> str:
    if next_url and next_url.startswith("/"):
        return next_url
    return url_for("main.day", report_date=report_date)


def sanitize_absolute_next(next_url: str | None) -> str | None:
    if next_url and next_url.startswith("/"):
        return next_url
    return None
