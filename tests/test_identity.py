from storage.identity import domain_from_url, stable_fingerprint


def test_domain_from_url():
    assert domain_from_url("https://www.zoomit.ir/archive?pageNumber=1") == "zoomit"
    assert domain_from_url("https://www.kojaro.com/archive?pageNumber=1") == "kojaro"
    assert domain_from_url("https://www.zoomon.ir/archive?pageNumber=1") == "zoomon"


def test_fingerprint_is_stable():
    assert stable_fingerprint(["a", "b"]) == stable_fingerprint(["a", "b"])
    assert stable_fingerprint(["a", "b"]) != stable_fingerprint(["b", "a"])
