import pytest


def test_classify_spare_part_request_turkish():
    from app.services.email_classifier import classify_email

    result = classify_email(
        subject="Yedek Parca Talebi",
        body="Merhaba, aşağıdaki yedek parçalar için teklif almak istiyoruz. ABC123 sensör 5 adet.",
    )
    assert result["category"] == "spare_part_request"
    assert result["confidence"] > 0.5


def test_classify_spare_part_request_english():
    from app.services.email_classifier import classify_email

    result = classify_email(
        subject="Spare Part Quotation Request",
        body="Hello, we would like a quotation for the following spare parts: sensor ABC123 qty 3.",
    )
    assert result["category"] == "spare_part_request"
    assert result["confidence"] > 0.5


def test_classify_complaint():
    from app.services.email_classifier import classify_email

    result = classify_email(
        subject="Şikayet - Geç Teslimat",
        body="Siparişimiz hala teslim edilmedi. Bu durumdan çok memnuniyetsiziz. Sorun çözülmeli.",
    )
    assert result["category"] in ["complaint", "order_status"]


def test_classify_price_inquiry():
    from app.services.email_classifier import classify_email

    result = classify_email(
        subject="Fiyat Listesi",
        body="Güncel fiyat listenizi gönderebilir misiniz? Bütçemiz sınırlı, indirim yapabilir misiniz?",
    )
    assert result["category"] in ["price_inquiry", "spare_part_request"]
    assert result["price_sensitivity"] is True


def test_classify_empty_email():
    from app.services.email_classifier import classify_email

    result = classify_email(subject="", body="")
    assert result["category"] == "general_inquiry"
    assert result["confidence"] > 0
