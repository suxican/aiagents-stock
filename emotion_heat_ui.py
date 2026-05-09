"""
情绪热度：嵌套展示第三方站点「自在量化」首页。
"""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

EMBED_URL = "https://www.zizizaizai.com/home"


def display_emotion_heat():
    st.title("🔥 情绪热度")
    st.markdown(f"**[在新窗口打开 自在量化 ↗]({EMBED_URL})**")

    components.html(
        f"""
        <iframe
            src="{EMBED_URL}"
            width="100%"
            height="920"
            style="border:0;border-radius:8px;min-height:75vh;width:100%;"
            title="自在量化"
            loading="lazy"
            referrerpolicy="no-referrer-when-downgrade"
            allow="fullscreen"
        ></iframe>
        """,
        height=940,
        scrolling=True,
    )


if __name__ == "__main__":
    display_emotion_heat()
