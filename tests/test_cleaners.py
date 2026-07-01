from law_agent.data.cleaners.common import clean_text


def test_clean_text_removes_mechanical_noise_without_rewriting_articles() -> None:
    raw = (
        "中华人民共和国个人信息保护法\r\n"
        "中华人民共和国个人信息保护法\r\n"
        "\u0000第一条  为了保护个人信息权益，规范个人信息处理活动。\r\n"
        "\r\n"
        "\r\n"
        "第二条  自然人的个人信息受法律保护。   \r\n"
    )

    result = clean_text(raw, title="中华人民共和国个人信息保护法")

    assert result.text.count("中华人民共和国个人信息保护法") == 1
    assert "第一条  为了保护个人信息权益，规范个人信息处理活动。" in result.text
    assert "第二条  自然人的个人信息受法律保护。" in result.text
    assert result.rule_hits["duplicate_title"] == 1
    assert result.rule_hits["control_chars"] == 1

