import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Tuple


@dataclass
class RegistrationCallbacks:
    log: Callable[[str], None]
    cancelled: Callable[[], bool]


@dataclass
class RegistrationOperations:
    start_browser: Callable[[], None]
    restart_browser: Callable[[], None]
    browser_missing: Callable[[], bool]
    open_signup_page: Callable[[], None]
    fill_email_and_submit: Callable[[], Tuple[str, str]]
    save_mail_credential: Callable[[str, str], bool]
    fill_code_and_submit: Callable[[str, str], str]
    fill_profile_and_submit: Callable[[], Dict[str, Any]]
    wait_for_sso_cookie: Callable[[], str]
    enable_nsfw: Callable[[str], Tuple[bool, str]]
    persist_account_line: Callable[[str, str, str], None]
    queue_unsaved_result: Callable[[Dict[str, Any], str], bool]
    persist_sso_token: Callable[[str], None]
    add_tokens: Callable[[str, str], Dict[str, Dict[str, Any]]]
    export_cpa: Callable[[str, str, str], Dict[str, Any]]
    cleanup: Callable[[str], None]
    sleep: Callable[[float], None]
    cancelled_exception: type
    retry_exception: type
    rotate_proxy: Callable[[], str] = None


@dataclass
class RegistrationResult:
    ok: bool
    email: str = ""
    password: str = ""
    sso: str = ""
    profile: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    retryable: bool = False
    step_times: Dict[str, int] = field(default_factory=dict)


@dataclass
class OutputResult:
    registered: bool
    saved: bool
    pending_saved: bool = False
    save_error: str = ""
    pools: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    cpa: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RegistrationSettings:
    count: int
    enable_nsfw: bool = True
    fast_sso_mode: bool = False
    max_mail_retry: int = 3
    max_slot_retry: int = 3
    cleanup_interval: int = 5


@dataclass
class BatchResult:
    success_count: int = 0
    fail_count: int = 0
    processed_count: int = 0
    registered_unsaved_count: int = 0
    postprocess_warning_count: int = 0
    cancelled: bool = False
    results: list = field(default_factory=list)


def register_one_account(callbacks, ops, enable_nsfw=True, max_mail_retry=3, fast_sso_mode=False):
    email = ""
    dev_token = ""
    code = ""
    mail_ok = False
    step_times = {}
    t_start = time.perf_counter()
    for mail_try in range(1, max_mail_retry + 1):
        if callbacks.cancelled():
            raise ops.cancelled_exception()
        callbacks.log(f"[*] 1. 打开注册页 (尝试 {mail_try}/{max_mail_retry})")
        t0 = time.perf_counter()
        ops.open_signup_page()
        step_times["open_page_ms"] = int((time.perf_counter() - t0) * 1000)

        callbacks.log("[*] 2. 创建邮箱并提交")
        t0 = time.perf_counter()
        email, dev_token = ops.fill_email_and_submit()
        step_times["submit_email_ms"] = int((time.perf_counter() - t0) * 1000)
        callbacks.log(f"[*] 邮箱: {email}")
        callbacks.log(f"[Debug] 邮箱credential(jwt): {dev_token}")
        if not ops.save_mail_credential(email, dev_token):
            callbacks.log("[!] 邮箱凭据保存失败，注册继续，但已明确记录该异常")
        callbacks.log("[*] 3. 拉取验证码")
        try:
            t0 = time.perf_counter()
            code = ops.fill_code_and_submit(email, dev_token)
            step_times["fetch_code_ms"] = int((time.perf_counter() - t0) * 1000)
            mail_ok = True
            break
        except Exception as exc:
            message = str(exc)
            if ("未收到验证码" in message or "验证码" in message) and mail_try < max_mail_retry:
                callbacks.log(f"[!] 本邮箱未取到验证码，自动更换新邮箱重试: {message}")
                ops.restart_browser()
                ops.sleep(1)
                continue
            raise
    if not mail_ok:
        raise RuntimeError("验证码阶段失败，已达到最大重试次数")
    callbacks.log(f"[*] 验证码: {code}")
    callbacks.log("[*] 4. 填写资料")
    t0 = time.perf_counter()
    profile = ops.fill_profile_and_submit()
    step_times["fill_profile_ms"] = int((time.perf_counter() - t0) * 1000)
    callbacks.log(f"[*] 资料已填: {profile.get('given_name')} {profile.get('family_name')}")
    callbacks.log("[*] 5. 等待 sso cookie")
    t0 = time.perf_counter()
    sso = ops.wait_for_sso_cookie()
    step_times["wait_sso_ms"] = int((time.perf_counter() - t0) * 1000)
    if fast_sso_mode:
        callbacks.log("[+] 激进极速模式开启：SSO 捕获成功，跳过 NSFW 与后续非核心流程")
    elif enable_nsfw:
        callbacks.log("[*] 6. 开启 NSFW")
        t0 = time.perf_counter()
        try:
            nsfw_ok, nsfw_msg = ops.enable_nsfw(sso)
            step_times["enable_nsfw_ms"] = int((time.perf_counter() - t0) * 1000)
            if nsfw_ok:
                callbacks.log(f"[+] NSFW 开启成功: {nsfw_msg}")
            else:
                callbacks.log(f"[!] NSFW 未开启，继续保存账号: {nsfw_msg}")
        except Exception as exc:
            callbacks.log(f"[!] NSFW 开启异常，继续保存账号: {exc}")
            step_times["enable_nsfw_ms"] = int((time.perf_counter() - t0) * 1000)
    total_ms = int((time.perf_counter() - t_start) * 1000)
    step_times["total_ms"] = total_ms
    callbacks.log(
        f"[耗时统计] 总计:{total_ms}ms | 打开页:{step_times.get('open_page_ms', 0)}ms | 提交邮箱:{step_times.get('submit_email_ms', 0)}ms | 验证码:{step_times.get('fetch_code_ms', 0)}ms | 填资料:{step_times.get('fill_profile_ms', 0)}ms | 等SSO:{step_times.get('wait_sso_ms', 0)}ms"
    )
    return RegistrationResult(
        ok=True,
        email=email,
        password=str(profile.get("password") or ""),
        sso=sso,
        profile=profile,
        step_times=step_times,
    )


def persist_account_result(result, callbacks, ops, fast_sso_mode=False):
    if getattr(result, "sso", ""):
        try:
            ops.persist_sso_token(result.sso)
        except Exception as exc:
            callbacks.log(f"[!] sso.txt 写入异常（不影响账号保存）: {exc}")

    try:
        ops.persist_account_line(result.email, result.password, result.sso)
        saved = True
        save_error = ""
        pending_saved = False
    except Exception as exc:
        saved = False
        save_error = str(exc)
        try:
            pending_saved = bool(
                ops.queue_unsaved_result(
                    {
                        "email": result.email,
                        "password": result.password,
                        "sso": result.sso,
                        "profile": result.profile,
                    },
                    save_error,
                )
            )
        except Exception as pending_exc:
            pending_saved = False
            callbacks.log(f"[!] pending 队列写入异常: {pending_exc}")
        callbacks.log(f"[!] 账号已注册但主结果文件保存失败: {save_error}")
        if pending_saved:
            callbacks.log("[!] 未保存账号已写入 pending 队列，等待人工重试")
        else:
            callbacks.log("[!] pending 队列也写入失败，请立即复制当前账号信息")

    if fast_sso_mode:
        callbacks.log("[+] 激进模式：账号及 SSO 已完成极速落盘交割")
        return OutputResult(
            registered=True,
            saved=saved,
            pending_saved=pending_saved,
            save_error=save_error,
            pools={},
            cpa={"ok": True, "skipped": True},
        )

    try:
        pools = ops.add_tokens(result.sso, result.email)
        if not isinstance(pools, dict):
            raise TypeError("token pool result must be a dict")
    except Exception as exc:
        callbacks.log(f"[!] token 入池后处理异常，账号结果已保留: {exc}")
        pools = {
            "internal": {
                "enabled": True,
                "ok": False,
                "error": str(exc),
            }
        }
    for name, state in pools.items():
        if isinstance(state, dict) and state.get("enabled") and not state.get("ok"):
            callbacks.log(f"[!] grok2api {name} 入池失败: {state.get('error')}")

    try:
        cpa = ops.export_cpa(result.email, result.password, result.sso)
        if not isinstance(cpa, dict):
            raise TypeError("CPA result must be a dict")
    except Exception as exc:
        callbacks.log(f"[!] CPA 导出后处理异常，账号结果已保留: {exc}")
        cpa = {"ok": False, "skipped": False, "error": str(exc)}

    return OutputResult(
        registered=True,
        saved=saved,
        pending_saved=pending_saved,
        save_error=save_error,
        pools=pools,
        cpa=cpa,
    )


def _notify_observer(observer, result, account, output, callbacks):
    try:
        observer(result, account, output)
    except Exception as exc:
        callbacks.log(f"[Debug] observer 执行失败: {exc}")


def _run_cleanup_safely(ops, callbacks, reason):
    try:
        ops.cleanup(reason)
        return True
    except Exception as exc:
        callbacks.log(f"[!] 清理失败，已忽略且不影响账号统计: {reason}: {exc}")
        return False


def _prepare_next_account(result, settings, callbacks, ops):
    if result.processed_count >= settings.count:
        return False
    if callbacks.cancelled():
        result.cancelled = True
        return False
    try:
        # 进入下一个账号前，尝试轮换代理（如果提供 rotate_proxy）
        if getattr(ops, "rotate_proxy", None):
            try:
                chosen = ops.rotate_proxy()
                if chosen:
                    callbacks.log(f"[*] 下一个账号使用代理: {chosen}")
            except Exception as e:
                callbacks.log(f"[!] 代理轮换异常: {e}")

        if ops.browser_missing():
            ops.start_browser()
        else:
            ops.restart_browser()
        ops.sleep(1)
        return True
    except ops.cancelled_exception:
        result.cancelled = True
        callbacks.log("[!] 已在账号间准备阶段停止")
        return False


def run_batch(count, callbacks, observer, ops, enable_nsfw=True, cleanup_interval=5,
              max_slot_retry=3, max_mail_retry=3, settings=None):
    if settings is None:
        settings = RegistrationSettings(
            count=int(count),
            enable_nsfw=bool(enable_nsfw),
            cleanup_interval=int(cleanup_interval),
            max_slot_retry=int(max_slot_retry),
            max_mail_retry=int(max_mail_retry),
        )
    result = BatchResult()
    retry_count_for_slot = 0
    last_cleanup_success_count = 0
    try:
        # 首个账号前选取代理
        if getattr(ops, "rotate_proxy", None):
            try:
                chosen = ops.rotate_proxy()
                if chosen:
                    callbacks.log(f"[*] 本次账号使用代理: {chosen}")
                else:
                    # 可能因为“仅测试通过”但尚无好代理
                    callbacks.log("[*] 代理池为空或无可用测试通过代理，将使用直连")
            except Exception as e:
                callbacks.log(f"[!] 代理轮换异常: {e}")

        ops.start_browser()
        callbacks.log("[*] 浏览器已启动")
        while result.processed_count < settings.count:
            if callbacks.cancelled():
                result.cancelled = True
                break
            callbacks.log(f"--- 开始第 {result.processed_count + 1}/{settings.count} 个账号 ---")
            account = None
            output = None
            continue_batch = True
            try:
                account = register_one_account(
                    callbacks,
                    ops,
                    enable_nsfw=settings.enable_nsfw,
                    max_mail_retry=settings.max_mail_retry,
                    fast_sso_mode=settings.fast_sso_mode,
                )
                output = persist_account_result(account, callbacks, ops, fast_sso_mode=settings.fast_sso_mode)
                result.results.append({"registration": account, "output": output})
                retry_count_for_slot = 0
                result.processed_count += 1
                if output.saved:
                    result.success_count += 1
                    callbacks.log(f"[+] 注册并保存成功: {account.email}")
                    if (
                        settings.cleanup_interval > 0
                        and result.success_count % settings.cleanup_interval == 0
                        and result.success_count != last_cleanup_success_count
                        and result.processed_count < settings.count
                    ):
                        _run_cleanup_safely(
                            ops,
                            callbacks,
                            f"已成功 {result.success_count} 个账号，执行定期清理",
                        )
                        last_cleanup_success_count = result.success_count
                else:
                    result.fail_count += 1
                    result.registered_unsaved_count += 1
                    callbacks.log(f"[-] 注册成功但持久化未完成: {account.email}")
                pool_warning = any(
                    isinstance(state, dict) and state.get("enabled") and not state.get("ok")
                    for state in output.pools.values()
                )
                cpa_warning = bool(
                    output.cpa
                    and not output.cpa.get("skipped")
                    and (
                        not output.cpa.get("ok")
                        or output.cpa.get("warning")
                        or output.cpa.get("cpa_copy_error")
                    )
                )
                if pool_warning or cpa_warning:
                    result.postprocess_warning_count += 1
            except ops.cancelled_exception:
                result.cancelled = True
                callbacks.log("[!] 注册被停止")
                continue_batch = False
            except ops.retry_exception as exc:
                retry_count_for_slot += 1
                if retry_count_for_slot <= settings.max_slot_retry:
                    callbacks.log(
                        f"[!] 当前账号流程卡住，重试第 {retry_count_for_slot}/{settings.max_slot_retry} 次: {exc}"
                    )
                else:
                    result.fail_count += 1
                    result.processed_count += 1
                    retry_count_for_slot = 0
                    callbacks.log(f"[-] 当前账号已达到最大重试次数，跳过: {exc}")
            except Exception as exc:
                result.fail_count += 1
                result.processed_count += 1
                retry_count_for_slot = 0
                callbacks.log(f"[-] 注册失败: {exc}")
            finally:
                _notify_observer(observer, result, account, output, callbacks)

            if not continue_batch or result.cancelled:
                break
            if not _prepare_next_account(result, settings, callbacks, ops):
                break
    finally:
        if result.results:
            valid_times = [r["registration"].step_times for r in result.results if r.get("registration") and getattr(r["registration"], "step_times", None)]
            if valid_times:
                count_n = len(valid_times)
                avg_total = int(sum(t.get("total_ms", 0) for t in valid_times) / count_n)
                avg_open = int(sum(t.get("open_page_ms", 0) for t in valid_times) / count_n)
                avg_email = int(sum(t.get("submit_email_ms", 0) for t in valid_times) / count_n)
                avg_code = int(sum(t.get("fetch_code_ms", 0) for t in valid_times) / count_n)
                avg_profile = int(sum(t.get("fill_profile_ms", 0) for t in valid_times) / count_n)
                avg_sso = int(sum(t.get("wait_sso_ms", 0) for t in valid_times) / count_n)
                callbacks.log(
                    f"[批处理统计报告] 样本:{count_n}个账号 | 平均总耗时:{avg_total}ms | 打开页:{avg_open}ms | 提交邮箱:{avg_email}ms | 验证码:{avg_code}ms | 填资料:{avg_profile}ms | 等SSO:{avg_sso}ms"
                )
        _run_cleanup_safely(ops, callbacks, "任务结束")
    return result

