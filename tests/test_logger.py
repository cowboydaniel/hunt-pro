from logger import setup_logger

def test_logger_accepts_string_category(tmp_path):
    log_dir = tmp_path / "logs"
    logger = setup_logger(log_dir=log_dir)

    logger.info("String category entry", category="DATA", extra_field="value")

    for handler in logger.logger.handlers:
        handler.flush()

    log_file = log_dir / "huntpro.log"
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "String category entry" in content
    assert '"category": "DATA"' in content
    assert '"field_extra_field": "value"' in content
