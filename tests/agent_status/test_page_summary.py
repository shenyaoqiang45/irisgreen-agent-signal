import json
import secrets
from http.client import HTTPConnection
from threading import Thread

from agent_status.http import make_server
from agent_status.page_summary import summarize
from agent_status.presentation import AgentPresentation
from agent_status.receiver import Receiver


LEAD = "咳嗽有痰时，处理重点不是单纯止咳，而是先判断是否存在需要尽快就医的情况"


def test_player_caption_is_the_sentence_and_the_video_name_stays_the_title():
    glance = summarize(
        "Grok Bot Q&A with Lauren Tan",
        "Skip navigation\nOkay. Gotta buy some, buy some clothes.",
        "https://www.youtube.com/watch?v=doLKqG8TefU",
    )
    assert glance["title"] == "Grok Bot Q&A with Lauren Tan"
    assert "buy some" in glance["message"]


def test_site_name_does_not_replace_the_reply():
    glance = summarize(
        "蚂蚁阿福-你的AI医生朋友",
        "睡眠质量这事，先分清你是睡不着还是睡不沉，方法不一样。下面这几条是最基础的。",
        "https://chat.antafu.com/?source=guanwang",
    )
    assert glance["title"] == "蚂蚁阿福-你的AI医生朋友"
    assert glance["message"].startswith("睡眠质量这事，先分清你是睡不着")


def test_tab_switch_keeps_the_open_reply_and_leaves_the_history_list():
    page = "\n".join([
        "睡眠质量怎么提高",
        "睡眠质量差怎么办",
        "这是一条比较长的历史对话标题，用来占住开头的位置。",
        "蚂蚁阿福开放平台",
        "下载蚂蚁阿福手机版",
        "用户q5Nn",
        "睡眠质量怎么提高",
        "睡眠质量这事，先分清你是睡不着还是睡不沉，方法不一样。",
        "每天同一时间起床，坚持一两周，生物钟自己就调过来了。",
    ])
    glance = summarize("蚂蚁阿福-你的AI医生朋友", page, "https://chat.antafu.com/?source=guanwang")
    assert glance["message"].startswith("睡眠质量这事，先分清你是睡不着")


def test_tab_switch_skips_the_page_footer():
    page = "\n".join([
        "探迹",
        "销售线索、客户管理和营销自动化都在这一页。",
        "首页", "产品", "价格", "关于", "登录", "注册", "解决方案", "客户案例",
        "友情链接：阿里巴巴 | 阿里云 | 版权局 | 商标局 | 国家知识产权局",
        "Copyright 2016 - 2026 广州探迹科技有限公司 粤ICP备16054963号",
    ])
    glance = summarize("探迹", page, "https://www.tungee.com/")
    assert glance["message"].startswith("销售线索、客户管理和营销自动化")
    assert "友情链接" not in glance["message"]
    assert "ICP" not in glance["message"]


def test_summary_skips_the_menu_and_uses_the_article_point():
    page = "\n".join([
        "首页", "热门话题（商务）", "官方产品",
        "给机器人配“眼睛”：全局快门、卷帘快门和RGB-D怎么选？",
        "机器人的视觉系统和人眼有一个本质区别。",
        "这篇文章从传感器选型讲起，帮你建立一套完整的视觉传感器选型框架。",
    ])
    glance = summarize("给机器人配“眼睛”", page, "https://www.unifolm.com/#/post/2274")
    assert glance["message"].startswith("这篇文章从传感器选型讲起")


def test_summary_uses_the_opening_point_and_replaces_the_previous_page():
    glance = summarize("蚂蚁阿福", "开启新对话\n" + LEAD + "。后续段落。", "https://chat.antafu.com/x")
    assert glance["title"] == "蚂蚁阿福"
    assert glance["message"] == LEAD
    assert len(summarize("标题", "句" * 400)["message"]) == 160

    receiver = Receiver()
    view = AgentPresentation(receiver)
    page = {"url": "https://chat.antafu.com/x", "title": "蚂蚁阿福", "text": LEAD}
    from agent_status.page_summary import open_page
    assert open_page(receiver, "browser", page)["expression"]["message"] == LEAD
    assert LEAD in view.current().lines[3]
    nxt = dict(page, title="下一页", text="这一页讲的是投影器把一句话投到墙上。")
    open_page(receiver, "browser", nxt)
    assert view.current().lines[1] == "下一页"
    assert len(receiver.snapshot("browser", "browser")["payload"]["expressions"]) == 1


def test_page_endpoint_requires_the_browser_token():
    token = secrets.token_urlsafe(24)
    server = make_server({"browser": token}, 0)
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        status, body = _post(server.server_port, token, {
            "url": "https://example.com/story", "title": "故事", "text": "打开页面之后，墙上只留这一句重点。"})
        assert status == 200 and body["expression"]["message"].startswith("打开页面之后")
        status, _ = _post(server.server_port, "x" * 24, {
            "url": "https://example.com/story", "title": "故事", "text": "打不开。"})
        assert status == 401
        status, _ = _post(server.server_port, token, {"url": "file:///secret", "title": "x", "text": "y" * 8})
        assert status == 400
    finally:
        server.shutdown()


def _post(port, token, body):
    connection = HTTPConnection("127.0.0.1", port, timeout=4)
    try:
        raw = json.dumps(body).encode()
        connection.request("POST", "/api/v1/page/open", raw, {
            "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        response = connection.getresponse()
        return response.status, json.loads(response.read().decode())
    finally:
        connection.close()
