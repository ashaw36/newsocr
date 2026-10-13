# -*- coding: utf-8 -*-
"""User-facing strings. ASCII source, unicode escapes."""

APP_NAME = "\u62a5\u7eb8\u6587\u7ae0\u8bc6\u522b"

UNTITLED = "\u672a\u8bc6\u522b\u6807\u9898"
NO_AUTHOR = ""

AUTHOR_STOP = {
    "\u4eca\u65e5",
    "\u6628\u65e5",
    "\u672c\u57e0",
    "\u4e0a\u6d77",
    "\u5317\u5e73",
    "\u5357\u4eac",
    "\u58f0\u660e",
    "\u8072\u660e",
    "\u5e7f\u544a",
    "\u5ee3\u544a",
    "\u542f\u4e8b",
    "\u5553\u4e8b",
    "\u7f16\u8f91",
    "\u7de8\u8f2f",
    "\u6765\u7a3f",
    "\u4f86\u7a3f",
    "\u8f6c\u8f7d",
    "\u8f49\u8f09",
    "\u5b8c",
    "\u672a\u5b8c",
    "\u7eed",
    "\u7e8c",
}

# suffix: zhu/zuo/zhuan/yi/bian/ji/shu
AUTHOR_SUFFIX = (
    "\u8457\u4f5c\u64b0\u8bd1\u8b6f\u7f16\u7de8\u8bb0\u8a18\u8ff0\u8349\u5f55\u9304"
)

AD_WORDS = (
    "\u5e7f\u544a",
    "\u5ee3\u544a",
    "\u5927\u51cf\u4ef7",
    "\u5927\u6e1b\u50f9",
    "\u7535\u8bdd",
    "\u96fb\u8a71",
    "\u4ef7\u76ee",
    "\u50f9\u76ee",
    "\u62db\u751f",
    "\u62db\u751f",
)
LAYOUT_LABEL = {
    "scan": "\u626b\u63cf\u7ad6\u6392",
    "news": "\u65b0\u95fb\u591a\u7bc7",
    "digest": "\u77ed\u8baf\u680f\u76ee",
    "essay": "\u526f\u520a\u957f\u6587",
    "magazine": "\u753b\u62a5\u6a2a\u6392",
    "ads": "\u5e7f\u544a\u542f\u4e8b",
}

NOTICE_WORDS = (
    "\u542f\u4e8b",
    "\u5553\u4e8b",
    "\u58f0\u660e",
    "\u8072\u660e",
    "\u516c\u544a",
    "\u516c\u544a",
)

UI = {
    "app_name": APP_NAME,
    "library": "\u62a5\u7eb8",
    "refresh": "\u5237\u65b0",
    "upload": "\u653e\u5165\u62a5\u7eb8",
    "recognize": "\u8bc6\u522b\u8fd9\u4e00\u4efd",
    "recognize_all": "\u5168\u90e8\u8bc6\u522b",
    "export_txt": "\u5bfc\u51fa TXT",
    "export_md": "\u5bfc\u51fa Markdown",
    "export_json": "\u5bfc\u51fa JSON",
    "articles": "\u6587\u7ae0",
    "title": "\u6807\u9898",
    "author": "\u4f5c\u8005",
    "body": "\u6b63\u6587",
    "merge_prev": "\u5e76\u5165\u4e0a\u4e00\u7bc7",
    "delete": "\u5220\u6389\u8fd9\u4e00\u5757",
    "prev_page": "\u4e0a\u4e00\u9875",
    "next_page": "\u4e0b\u4e00\u9875",
    "page": "\u9875",
    "hint": (
        "\u628a\u62a5\u7eb8 PDF \u6216\u56fe\u7247\u653e\u8fdb\u6765\u3002\u7ad6\u6392\u3001\u6a2a\u6392\u548c\u5206\u5757\u7248\u9762\u4f1a\u6309\u680f\u8bfb\u53d6\uff0c"
        "\u5e76\u5c3d\u91cf\u62c6\u51fa\u6bcf\u7bc7\u7684\u6807\u9898\u3001\u4f5c\u8005\u548c\u6b63\u6587\u3002"
        "\u65e7\u62a5\u626b\u63cf\u4f1a\u6709\u9519\u5b57\uff0c\u8bf7\u6838\u5bf9\u540e\u518d\u5bfc\u51fa\u3002"
        "\u91cd\u65b0\u8bc6\u522b\u4f1a\u8986\u76d6\u624b\u5de5\u4fee\u6539\u3002"
    ),
    "empty": "\u5de6\u8fb9\u9009\u4e00\u4efd\u62a5\u7eb8\uff0c\u518d\u70b9\u8bc6\u522b\u3002",
    "no_articles": "\u8fd9\u4e00\u9875\u6ca1\u6709\u62c6\u51fa\u6587\u7ae0\u3002",
    "untitled": UNTITLED,
    "author_ph": "\u6ca1\u6709\u8bc6\u522b\u5230\u4f5c\u8005\u53ef\u4ee5\u7559\u7a7a",
    "body_ph": "\u6b63\u6587",
    "featured": "\u4e0e\u6587\u4ef6\u540d\u63a5\u8fd1",
    "kind_ad": "\u50cf\u5e7f\u544a",
    "kind_notice": "\u542f\u4e8b",
    "kind_article": "\u6587\u7ae0",
    "masthead": "\u62a5\u5934",
    "working": "\u6b63\u5728\u8bc6\u522b",
    "done": "\u8bc6\u522b\u5b8c\u6210",
    "failed": "\u8bc6\u522b\u5931\u8d25",
    "saved": "\u5df2\u4fdd\u5b58",
    "inbox_note": "\u4e5f\u53ef\u4ee5\u76f4\u63a5\u628a\u6587\u4ef6\u653e\u5230 F \u6216 inbox \u6587\u4ef6\u5939\u3002",
}
