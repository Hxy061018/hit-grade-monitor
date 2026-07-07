import os
import json
import time
import re
import smtplib
import sys
import html
from pathlib import Path
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


def get_int_env(name, default):
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        print(f"环境变量 {name}={value!r} 不是整数，已使用默认值 {default}。")
        return default


def get_bool_env(name, default):
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def split_emails(value):
    if not value:
        return []
    return [email.strip() for email in re.split(r"[,;]", value) if email.strip()]


SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SMTP_AUTH_CODE = os.getenv("SMTP_AUTH_CODE") or os.getenv("SMTP_PASSWORD")
RECEIVER_EMAILS = split_emails(os.getenv("RECEIVER_EMAIL", "3508358116@qq.com"))
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.qq.com")
SMTP_PORT = get_int_env("SMTP_PORT", 465)
SMTP_USE_SSL = get_bool_env("SMTP_USE_SSL", True)
SMTP_STARTTLS = get_bool_env("SMTP_STARTTLS", not SMTP_USE_SSL)
MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME", "HIT教务检测系统")
CHECK_INTERVAL_MINUTES = get_int_env("CHECK_INTERVAL_MINUTES", 30)
KEEPALIVE_INTERVAL_MINUTES = get_int_env("KEEPALIVE_INTERVAL_MINUTES", 5)
LOGIN_ALERT_COOLDOWN_MINUTES = get_int_env("LOGIN_ALERT_COOLDOWN_MINUTES", 180)
LOGIN_ALERT_GRACE_SECONDS = get_int_env("LOGIN_ALERT_GRACE_SECONDS", 60)
DEBUG_PAGINATION = get_bool_env("DEBUG_PAGINATION", False)
JWTS_HOME_URL = os.getenv("JWTS_HOME_URL", "http://jwts.hit.edu.cn/")

CACHE_FILE = BASE_DIR / os.getenv("CACHE_FILE", "grades_cache.json")
LAST_LOGIN_ALERT_AT = 0


def email_enabled():
    return bool(SENDER_EMAIL and SMTP_AUTH_CODE and RECEIVER_EMAILS)

def send_email(subject, content):
    if not email_enabled():
        print("未配置邮箱发送信息，跳过邮件发送。")
        return False
    
    # 构造邮件
    message = MIMEText(content, 'html', 'utf-8')
    message['From'] = formataddr((Header(MAIL_FROM_NAME, 'utf-8').encode(), SENDER_EMAIL))
    message['To'] = ", ".join(RECEIVER_EMAILS)
    message['Subject'] = Header(subject, 'utf-8')

    try:
        if SMTP_USE_SSL:
            smtp = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30)
        else:
            smtp = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)

        with smtp:
            if not SMTP_USE_SSL and SMTP_STARTTLS:
                smtp.starttls()
            smtp.login(SENDER_EMAIL, SMTP_AUTH_CODE)
            smtp.sendmail(SENDER_EMAIL, RECEIVER_EMAILS, message.as_string())

        print(f"邮件发送成功 -> {', '.join(RECEIVER_EMAILS)}")
        return True
    except smtplib.SMTPException as e:
        print(f"Error: 无法发送邮件: {e}")
    except Exception as e:
        print(f"Error: 未知错误: {e}")
    return False


def default_cache():
    return {"gpa": "", "ranking": "", "courses": {}}


def normalize_cache(data):
    if not isinstance(data, dict):
        return default_cache()

    courses = data.get("courses", {})
    if not isinstance(courses, dict):
        courses = {}

    return {
        "gpa": str(data.get("gpa", "")),
        "ranking": str(data.get("ranking", "")),
        "courses": {str(k): str(v) for k, v in courses.items()},
    }


def load_cache():
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return normalize_cache(json.load(f))
        except Exception as e:
            print(f"读取缓存失败，已按空缓存处理: {e}")
    return default_cache()

def save_cache(data):
    data = normalize_cache(data)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def has_known_value(value):
    return bool(value and value != "未找到")


def html_lines(lines):
    return "<br>".join(html.escape(str(line)) for line in lines)


def build_changes(old_data, new_data):
    old_data = normalize_cache(old_data)
    new_data = normalize_cache(new_data)

    changes = []
    old_courses = old_data.get("courses", {})
    new_courses = new_data.get("courses", {})

    if not old_courses and new_courses:
        course_lines = [f"课程：{name}，成绩：{score}" for name, score in new_courses.items()]
        changes.append("检测到成绩已出：<br>" + html_lines(course_lines))
    elif old_courses and new_courses:
        course_changes = []
        for course_name, course_score in new_courses.items():
            old_score = old_courses.get(course_name)
            if old_score is None:
                course_changes.append(f"【新出成绩】课程：{course_name}，成绩：{course_score}")
            elif old_score != course_score:
                course_changes.append(f"【成绩变更】课程：{course_name}，成绩：{course_score}（原成绩：{old_score}）")

        if course_changes:
            changes.append("发现成绩更新：<br>" + html_lines(course_changes))

    return changes


def cache_for_save(old_data, new_data):
    old_data = normalize_cache(old_data)
    new_data = normalize_cache(new_data)
    if old_data.get("courses") and not new_data.get("courses"):
        new_data["courses"] = old_data["courses"]
    return new_data


def build_email_content(changes, new_data):
    new_data = normalize_cache(new_data)
    return f"""
    <h2>哈工大教务系统成绩通知</h2>
    <p><b>检测结果：</b></p>
    <p>{'<br><br>'.join(changes)}</p>
    <hr>
    <p><b>当前概览：</b></p>
    <ul>
        <li>平均学分绩：{html.escape(new_data['gpa'])}</li>
        <li>当前排名：{html.escape(new_data['ranking'])}</li>
        <li>已提取到成绩科目数：{len(new_data['courses'])}</li>
    </ul>
    <p><i>本邮件由自动检测脚本发送。</i></p>
    """


def send_test_email():
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    content = f"""
    <h2>哈工大教务系统成绩检测邮件测试</h2>
    <p>如果你收到这封邮件，说明 SMTP 配置可用。</p>
    <p>发送时间：{html.escape(now)}</p>
    """
    return send_email("【测试】哈工大成绩检测邮件发送测试", content)


def send_login_required_email(reason):
    global LAST_LOGIN_ALERT_AT

    now_monotonic = time.monotonic()
    cooldown_seconds = max(60, LOGIN_ALERT_COOLDOWN_MINUTES * 60)
    if LAST_LOGIN_ALERT_AT and now_monotonic - LAST_LOGIN_ALERT_AT < cooldown_seconds:
        print("-> 已发送过登录提醒，冷却期内不重复发送。")
        return False

    LAST_LOGIN_ALERT_AT = now_monotonic
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    content = f"""
    <h2>哈工大教务系统需要重新登录</h2>
    <p>成绩检测脚本检测到教务系统登录态可能已失效，需要你在弹出的浏览器窗口中手动完成登录。</p>
    <p>原因：{html.escape(reason)}</p>
    <p>检测时间：{html.escape(now)}</p>
    <p><i>完成登录后，脚本会继续自动检测。</i></p>
    """
    return send_email("【提醒】哈工大成绩检测需要重新登录", content)

def extract_gpa_info(page):
    # 遍历所有 frame 寻找学分绩
    gpa, ranking = "未找到", "未找到"
    for frame in page.frames:
        try:
            soup = BeautifulSoup(frame.content(), 'html.parser')
            text = soup.get_text(separator=' ', strip=True)
            
            if gpa == "未找到":
                gpa_patterns = [
                    r'平均学分绩(?:为|是)?[：:\s]*([\d.]+)',
                    r'您的平均学分绩(?:为|是)?[：:\s]*([\d.]+)',
                    r'平均成绩(?:为|是)?[：:\s]*([\d.]+)',
                ]
                for pattern in gpa_patterns:
                    gpa_match = re.search(pattern, text)
                    if gpa_match:
                        gpa = gpa_match.group(1)
                        break
            
            if ranking == "未找到":
                rank_match = re.search(r'(名次|排名|专业排名).*?(\d+(/\d+)?)', text)
                if rank_match: ranking = rank_match.group(2)
        except:
            pass
            
    return gpa, ranking


def choose_course_name_index(header_texts):
    negative_words = ("代码", "编号", "课号", "性质", "类别", "属性", "学分", "绩点", "类型")

    for i, header in enumerate(header_texts):
        if any(word in header for word in ("课程名称", "课程名")):
            return i

    for i, header in enumerate(header_texts):
        if "课程" in header and "名称" in header and not any(word in header for word in negative_words):
            return i

    for i, header in enumerate(header_texts):
        if "课程" in header and not any(word in header for word in negative_words):
            return i

    return -1


def is_released_score(score):
    score = score.strip()
    if not score:
        return False

    unreleased_words = ("未出", "未录", "未公布", "暂无", "无成绩", "缺考", "缓考")
    if any(word in score for word in unreleased_words):
        return False

    return score not in {"-", "--", "—", "N/A", "无"}


def extract_courses(page):
    courses = {}
    
    for frame in page.frames:
        try:
            soup = BeautifulSoup(frame.content(), 'html.parser')
            tables = soup.find_all('table')
            for table in tables:
                headers = table.find_all('th')
                if not headers:
                    headers = table.find('tr').find_all('td') if table.find('tr') else []
                    
                header_texts = [th.get_text(strip=True) for th in headers]
                if not any("课程" in h for h in header_texts):
                    continue
                
                name_idx, score_idx = choose_course_name_index(header_texts), -1
                for i, h in enumerate(header_texts):
                    if "成绩" in h or "分数" in h or "期末" in h:
                        score_idx = i
                        
                if name_idx == -1 or score_idx == -1:
                    continue
                    
                rows = table.find_all('tr')
                for row in rows:
                    cols = row.find_all(['td', 'th'])
                    if len(cols) > max(name_idx, score_idx):
                        course_name = cols[name_idx].get_text(strip=True)
                        score = cols[score_idx].get_text(strip=True)
                        
                        if (
                            course_name
                            and is_released_score(score)
                            and "课程" not in course_name
                            and "成绩" not in score
                        ):
                            courses[course_name] = score
        except:
            pass
                    
    return courses


def wait_for_page_settle(page, timeout_ms=5000, extra_ms=1500):
    try:
        page.wait_for_load_state('networkidle', timeout=timeout_ms)
    except Exception:
        pass
    page.wait_for_timeout(extra_ms)


def click_enabled_text(target, text):
    try:
        locs = target.locator(f'text="{text}"').all()
    except Exception:
        return False

    for loc in locs:
        try:
            if text.isdigit():
                in_pager = loc.evaluate(
                    """node => {
                        let current = node;
                        for (let i = 0; current && i < 8; i += 1) {
                            const text = current.innerText || current.textContent || '';
                            if (/首页|尾页|每页|条|<<|>>/.test(text)) return true;
                            current = current.parentElement;
                        }
                        return false;
                    }"""
                )
                if not in_pager:
                    continue

            is_clickable = loc.evaluate(
                """node => {
                    const clickable = node.closest('a,button,[onclick],.l-btn');
                    if (!clickable) return false;

                    const disabledAncestor = clickable.closest(
                        '.l-btn-disabled,.disabled,[disabled],[aria-disabled="true"]'
                    );
                    if (disabledAncestor) return false;

                    const style = window.getComputedStyle(clickable);
                    const rect = clickable.getBoundingClientRect();
                    return style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && rect.width > 0
                        && rect.height > 0;
                }"""
            )
            if not is_clickable:
                continue

            loc.evaluate(
                """node => {
                    const clickable = node.closest('a,button,[onclick],.l-btn') || node;
                    clickable.click();
                }"""
            )
            page = target.page if hasattr(target, "page") else target
            wait_for_page_settle(page)
            return True
        except Exception:
            pass
    return False


def click_text_anywhere(page, text):
    if click_enabled_text(page, text):
        return True

    for frame in page.frames:
        if click_enabled_text(frame, text):
            return True
    return False


def course_page_signature(page):
    pieces = []
    for frame in page.frames:
        try:
            soup = BeautifulSoup(frame.content(), 'html.parser')
            text = soup.get_text(separator=' ', strip=True)
            if "课程" in text or "成绩" in text or "每页" in text:
                pieces.append(text[-3000:])
        except Exception:
            pass
    return "\n".join(pieces)


def wait_for_course_page_change(page, before_signature, timeout_ms=5000):
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        page.wait_for_timeout(500)
        if course_page_signature(page) != before_signature:
            return True
    return False


def log_pagination_candidates(page, labels):
    print(" -> 翻页候选调试信息：")
    targets = [("page", page)] + [(f"frame:{i}", frame) for i, frame in enumerate(page.frames)]

    for target_name, target in targets:
        for label in labels:
            try:
                locs = target.locator(f'text="{label}"').all()
            except Exception:
                continue

            for index, loc in enumerate(locs[:5]):
                try:
                    info = loc.evaluate(
                        """node => {
                            const parent = node.parentElement;
                            const clickable = node.closest('a,button,[onclick],.l-btn') || node;
                            const rect = node.getBoundingClientRect();
                            return {
                                tag: node.tagName,
                                text: (node.innerText || node.textContent || '').trim(),
                                className: String(node.className || ''),
                                parentTag: parent ? parent.tagName : '',
                                parentClass: parent ? String(parent.className || '') : '',
                                clickableTag: clickable.tagName,
                                clickableClass: String(clickable.className || ''),
                                onclick: String(clickable.getAttribute('onclick') || ''),
                                href: String(clickable.getAttribute('href') || ''),
                                visible: rect.width > 0 && rect.height > 0,
                            };
                        }"""
                    )
                    print(f"    {target_name} label={label!r} #{index}: {info}")
                except Exception as e:
                    print(f"    {target_name} label={label!r} #{index}: 读取失败 {e}")


def advance_course_page(page, before_signature, next_page_number):
    labels = [str(next_page_number), ">>", "下一页", "下页"]
    tried = set()

    for label in labels:
        if label in tried:
            continue
        tried.add(label)

        if not click_text_anywhere(page, label):
            continue
        if wait_for_course_page_change(page, before_signature):
            return True
        print(f" -> 已尝试翻页按钮 {label}，但页面内容未变化。")

    if DEBUG_PAGINATION:
        log_pagination_candidates(page, labels)
    return False


def extract_all_course_pages(page, max_pages=20):
    all_courses = {}
    seen_signatures = set()

    for page_number in range(1, max_pages + 1):
        current_courses = extract_courses(page)
        all_courses.update(current_courses)
        print(
            f" -> 第 {page_number} 页提取到 {len(current_courses)} 门课程成绩，"
            f"累计 {len(all_courses)} 门。"
        )

        before_signature = course_page_signature(page)
        if before_signature in seen_signatures:
            print(" -> 检测到重复分页内容，停止翻页。")
            break
        seen_signatures.add(before_signature)

        if not advance_course_page(page, before_signature, page_number + 1):
            print(" -> 未找到可用下一页或页面未变化，分页结束。")
            break
    else:
        print(f" -> 已达到最大翻页数 {max_pages}，停止翻页以避免循环。")

    return all_courses


def click_in_frames(page, text):
    for frame in page.frames:
        try:
            locs = frame.locator(f'text="{text}"').all()
            if locs:
                locs[-1].evaluate("node => node.click()") # use last to avoid picking up invisible menu wrappers sometimes
                wait_for_page_settle(page, extra_ms=2000)
                return True
        except:
            pass
    return False


def has_text_anywhere(page, texts):
    for text in texts:
        selector = f'text="{text}"'
        try:
            if page.locator(selector).count() > 0:
                return True
        except Exception:
            pass

        for frame in page.frames:
            try:
                if frame.locator(selector).count() > 0:
                    return True
            except Exception:
                pass
    return False


def is_logged_in_page(page):
    return has_text_anywhere(
        page,
        [
            "本科教学管理与服务平台",
            "成绩管理",
            "个人中心",
            "学生事务",
        ],
    )


def should_wait_for_login(page):
    if is_logged_in_page(page):
        return False

    try:
        title = page.title()
    except Exception:
        title = ""

    url = page.url.lower()
    looks_like_login_url = "logincas" in url or "authserver" in url or "cas" in url
    has_login_entry = has_text_anywhere(page, ["统一身份认证登录"])
    return looks_like_login_url or has_login_entry or "登录" in title


def check_grades(page):
    print("正在查询学分绩...")
    try:
        # 模拟鼠标悬停以展开菜单
        page.locator('text="成绩管理"').first.hover(timeout=5000)
        # 点击学分绩查询
        page.locator('text="学分绩查询"').first.click(timeout=5000)
        wait_for_page_settle(page, extra_ms=2000) # 额外等待渲染
    except Exception as e:
        print("导航至学分绩查询时发生异常，尝试寻找任意链接...", e)
        if not click_in_frames(page, "学分绩查询"):
            # fall back
            links = page.locator('a:has-text("学分绩查询")').all()
            if links:
                links[-1].evaluate("node => node.click()")
                wait_for_page_settle(page, extra_ms=2000)

    gpa, ranking = extract_gpa_info(page)
    print(f" -> 当前学分绩: {gpa}, 排名: {ranking}")
    
    print("正在查询个人成绩...")
    try:
        page.locator('text="成绩管理"').first.hover(timeout=5000)
        page.locator('text="个人成绩"').first.click(timeout=5000)
        wait_for_page_settle(page, extra_ms=2000)
    except Exception as e:
        print("导航至个人成绩时发生异常，尝试寻找任意链接...", e)
        if not click_in_frames(page, "个人成绩"):
            links = page.locator('a:has-text("个人成绩")').all()
            if links:
                links[-1].evaluate("node => node.click()")
                wait_for_page_settle(page, extra_ms=2000)

    # 应对中间跳转页：检查是否有“期末成绩查询”按钮并点击
    if not click_in_frames(page, "期末成绩查询"):
        try:
            final_grades_links = page.locator('text="期末成绩查询"').all()
            if final_grades_links:
                final_grades_links[-1].evaluate("node => node.click()")
                wait_for_page_settle(page, extra_ms=2000)
        except:
            pass

    # 有些教务系统个人成绩页面需要再点击“查询”按钮才能列出所有成绩
    click_in_frames(page, "查询")

    courses = extract_all_course_pages(page)
    print(f" -> 共提取到 {len(courses)} 门课程成绩。")
    
    return {"gpa": gpa, "ranking": ranking, "courses": courses}

def open_browser_context(playwright):
    user_data_dir = str(BASE_DIR / "playwright_userdata")
    print("正在启动浏览器 (首次运行可能会弹出窗口供您登录)...")
    return playwright.chromium.launch_persistent_context(
        user_data_dir=user_data_dir,
        headless=False, # 保持 False 让用户可以手动输入账号密码/验证码
        viewport={"width": 1280, "height": 720}
    )


def close_browser_safely(browser):
    if browser is None:
        return
    try:
        browser.close()
    except Exception:
        pass


def open_browser_page(playwright):
    browser = open_browser_context(playwright)
    page = browser.pages[0] if browser.pages else browser.new_page()
    return browser, page


def goto_home(page):
    page.goto(JWTS_HOME_URL, wait_until="domcontentloaded", timeout=30000)
    wait_for_page_settle(page)


def wait_until_logged_in(page, notify_login_required=False, reason="检测到登录页"):
    # 等待直到进入教务系统主页（跳出 CAS 登录）
    login_hint_shown = False
    login_alert_sent = False
    login_wait_started_at = time.monotonic()
    while should_wait_for_login(page):
        if not login_hint_shown:
            print("-> 检测到在登录页面，请在弹出的浏览器窗口中手动登录，脚本将在此等待...")
            login_hint_shown = True
        if (
            notify_login_required
            and not login_alert_sent
            and time.monotonic() - login_wait_started_at >= LOGIN_ALERT_GRACE_SECONDS
        ):
            send_login_required_email(reason)
            login_alert_sent = True
        page.wait_for_timeout(2000)

    if login_hint_shown:
        print("-> 登录成功！")
        wait_for_page_settle(page, extra_ms=3000) # 给一点时间等教务系统加载完全


def run_check_once(page, notify=True):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 开始检查教务系统...")
    goto_home(page)
    wait_until_logged_in(page, notify_login_required=notify, reason="正式检测前发现需要登录")

    new_data = check_grades(page)
    old_data = load_cache()
    changes = build_changes(old_data, new_data)
    data_to_save = cache_for_save(old_data, new_data)

    if not notify:
        save_cache(data_to_save)
        print(
            f"-> 已刷新缓存：{len(data_to_save.get('courses', {}))} 门课程，"
            f"平均学分绩 {data_to_save.get('gpa')}，排名 {data_to_save.get('ranking')}。"
        )
        return new_data, changes

    if changes:
        print("!!! 检测到新出/变更课程成绩，准备发送邮件 !!!")
        email_content = build_email_content(changes, new_data)
        email_sent = send_email("【提醒】哈工大新出成绩通知", email_content)
        if email_sent or not email_enabled():
            save_cache(data_to_save)
        else:
            print("-> 邮件发送失败，本次不更新缓存；下次检查会继续尝试提醒。")
    else:
        print("-> 没有发现新出课程成绩。")
        if new_data.get("courses") or not old_data.get("courses"):
            save_cache(data_to_save)
        else:
            print("-> 本次未提取到成绩表，保留上次缓存。")

    return new_data, changes


def keep_session_alive(page):
    if page.is_closed():
        raise RuntimeError("浏览器页面已关闭，需要重新打开。")

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 正在保活教务系统登录态...")
    goto_home(page)

    if should_wait_for_login(page):
        print("-> 检测到登录态可能已失效，尝试恢复登录。")
        wait_until_logged_in(page, notify_login_required=True, reason="保活时发现登录态可能已失效")
    else:
        print("-> 保活成功，当前仍在教务系统登录态。")


def wait_with_keepalive(page, total_minutes):
    total_seconds = max(0, total_minutes * 60)
    keepalive_seconds = max(60, KEEPALIVE_INTERVAL_MINUTES * 60)
    deadline = time.monotonic() + total_seconds

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return

        sleep_seconds = min(keepalive_seconds, remaining)
        time.sleep(sleep_seconds)

        if time.monotonic() >= deadline:
            return

        keep_session_alive(page)


def refresh_cache_once():
    with sync_playwright() as p:
        browser, page = open_browser_page(p)
        try:
            run_check_once(page, notify=False)
        finally:
            browser.close()


def run_loop():
    with sync_playwright() as p:
        browser = None
        page = None
        
        while True:
            try:
                if browser is None or page is None or page.is_closed():
                    close_browser_safely(browser)
                    browser, page = open_browser_page(p)

                run_check_once(page, notify=True)
            except Exception as e:
                print(f"本次检查过程中发生错误: {e}")
                if page is None or page.is_closed() or "closed" in str(e).lower():
                    close_browser_safely(browser)
                    browser = None
                    page = None
                
            print(f"等待 {CHECK_INTERVAL_MINUTES} 分钟后进行下一次检查...\n")
            try:
                if page is None or page.is_closed():
                    raise RuntimeError("浏览器页面已关闭。")
                wait_with_keepalive(page, CHECK_INTERVAL_MINUTES)
            except Exception as e:
                print(f"等待期间保活失败: {e}")
                close_browser_safely(browser)
                browser = None
                page = None

if __name__ == "__main__":
    print("="*50)
    print("哈工大成绩自动检测系统启动")
    print("="*50)

    if "--test-email" in sys.argv:
        raise SystemExit(0 if send_test_email() else 1)

    if "--refresh-cache" in sys.argv:
        refresh_cache_once()
        raise SystemExit(0)
    
    if not email_enabled():
        print("【提示】未在 .env 中配置完整邮箱信息！")
        print("至少需要 SENDER_EMAIL、SMTP_AUTH_CODE、RECEIVER_EMAIL。")
        print("程序将正常运行并在控制台输出变化，但不会发送邮件。")
        print("="*50)
        
    run_loop()
