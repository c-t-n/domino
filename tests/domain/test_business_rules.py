import pytest

from domino.domain.business_rule import BusinessRule, BusinessRuleViolation


class DummyRule(BusinessRule):
    rule_id = "test"
    error_message = "Failed test rule"

    def rule(self, param: bool) -> bool:
        return param


class DummyRuleWithParam(BusinessRule):
    rule_id = "test_with_params"
    error_message = "Failed test rule"

    def rule(self, param1: bool = True, param2: str = "test") -> bool:
        return param1 and param2 == "test"


class TestBusinessRule:
    def test_rule_passes(self):
        DummyRule(True)

    def test_rule_fails(self):
        with pytest.raises(BusinessRuleViolation):
            DummyRule(False)

    def test_dump_exception_as_json(self):
        with pytest.raises(BusinessRuleViolation) as exc_infos:
            DummyRule(False)

        assert exc_infos.value.to_json() == {
            "id": "test",
            "message": "Failed test rule",
        }


class TestBusinessRuleWithParams:
    def test_rule_passes(self):
        DummyRuleWithParam()

    def test_rule_fails(self):
        with pytest.raises(BusinessRuleViolation):
            DummyRuleWithParam(param1=False)

    def test_rule_passes_with_params(self):
        DummyRuleWithParam(True, "test")

    def test_rule_fails_with_params(self):
        with pytest.raises(BusinessRuleViolation):
            DummyRuleWithParam(False, "not_test")

    def test_dump_exception_as_json(self):
        with pytest.raises(BusinessRuleViolation) as exc_infos:
            DummyRuleWithParam(False)

        assert exc_infos.value.to_json() == {
            "id": "test_with_params",
            "message": "Failed test rule",
        }