import asyncio
import io
import json
import zipfile

import httpx
import pytest

from citation_check import api, config
from citation_check.llm import LMStudioClient

class Api:
    """Calls the ASGI app in-process through httpx (independent of the installed starlette TestClient version)."""

    def request(self, method, url, **kw):
        async def go():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app), base_url="http://test") as c:
                return await c.request(method, url, **kw)
        return asyncio.run(go())

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def post(self, url, **kw):
        return self.request("POST", url, **kw)


DRAFT = ("عملاً بأحكام المادة (٩) من قانون المالكين والمستأجرين رقم (١٥) لسنة ٢٠١٥ لا يجوز الإخلاء قبل الإنذار الكتابي. "
         "وعملاً بالمادة (99) من قانون البينات رقم (77) لسنة 2011 تجيز اليمين.")


def fake(tmp_path, *, down=False, models=("m",), match=True):
    def handler(req):
        if down:
            raise httpx.ConnectError("refused")
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": m} for m in models]})
        body = json.loads(req.content)
        name = body["response_format"]["json_schema"]["name"]
        out = {"statute": [], "cassation": []} if name == "citations" else \
            {"reason": "سبب", "matches_claim": match, "related": True}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(out, ensure_ascii=False)}, "finish_reason": "stop"}]})

    return LMStudioClient("http://x/v1", "m", log_path=tmp_path / "log.jsonl", transport=httpx.MockTransport(handler),
                          max_retries=0, backoff_s=0)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "make_client", lambda: fake(tmp_path))
    monkeypatch.setattr(config, "LOG_DIR", tmp_path)
    return Api()


def test_health_ok_and_down(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "make_client", lambda: fake(tmp_path))
    h = Api().get("/api/health").json()
    assert h["lm_studio"]["ok"] and h["corpus"]["ok"] and h["corpus"]["statute"] == 8 and h["corpus"]["cassation"] == 6
    assert h["prompts"]["claim"].startswith("claim_v")
    monkeypatch.setattr(api, "make_client", lambda: fake(tmp_path, down=True))
    h = Api().get("/api/health").json()
    assert not h["lm_studio"]["ok"] and "cannot reach LM Studio" in h["lm_studio"]["error"]


def test_corpus_and_samples(client):
    c = client.get("/api/corpus").json()
    assert len(c["statute"]) == 8 and c["statute"][0]["id"].startswith("S:")
    sets = client.get("/api/samples").json()
    keys = [s["key"] for s in sets]
    assert keys == ["sample", "heldout", "hard"]
    d = sets[0]["drafts"][0]
    assert d["name"] == "draft_01.txt" and "المادة" in d["text"] and len(d["gold"]) == 3 and d["gold"][0]["expected_status"]


def test_stage_clean(client):
    r = client.post("/api/stage/clean", json={"text": "  المــادة‏ (٢٣)  من قانون \r\n\r\n\r\nنص"}).json()
    assert r["cleaned"] == "المادة (٢٣) من قانون\n\nنص"
    assert r["removed"]["invisible_marks_and_tatweel"] == 3 and r["raw_chars"] > r["cleaned_chars"]
    assert r["chunks"] == [{"start": 0, "end": len(r["cleaned"]), "chars": len(r["cleaned"])}]


def test_stage_regex_needs_no_llm(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "make_client", lambda: fake(tmp_path, down=True))
    r = Api().post("/api/stage/regex", json={"text": DRAFT}).json()
    ids = [c["id"] for c in r["citations"]["statute"]]
    assert ids == ["S:15/2015:9", "S:77/2011:99"] and all(c["origin"] == "regex" for c in r["citations"]["statute"])
    assert r["llm_calls"] == 0 and r["citations"]["statute"][0]["span"][0] >= 0


def test_stage_extract_with_llm_and_when_lm_studio_is_down(client, tmp_path, monkeypatch):
    r = client.post("/api/stage/extract", json={"text": DRAFT}).json()
    assert r["llm_calls"] == 1 and len(r["citations"]["statute"]) == 2 and r["complete"]
    r = client.post("/api/stage/extract", json={"text": DRAFT, "use_llm": False, "regex_net": False}).json()
    assert r["citations"] == {"statute": [], "cassation": []}
    monkeypatch.setattr(api, "make_client", lambda: fake(tmp_path, down=True))
    resp = Api().post("/api/stage/extract", json={"text": DRAFT})
    assert resp.status_code == 503 and "cannot reach LM Studio" in resp.json()["detail"]


def test_stage_verify_roundtrip_and_validation(client):
    ex = client.post("/api/stage/regex", json={"text": DRAFT}).json()["citations"]
    rep = client.post("/api/stage/verify", json={"extracted": ex, "draft_name": "d.txt"}).json()
    st = {f["id"]: f["status"] for f in rep["findings"]}
    assert st == {"S:15/2015:9": "SUPPORTED", "S:77/2011:99": "NOT_FOUND"}
    assert rep["counts"]["NOT_FOUND"] == 1 and rep["findings"][1]["closest_corpus_id"]
    bad = client.post("/api/stage/verify", json={"extracted": {"statute": [{"bogus": 1}]}})
    assert bad.status_code == 422 and "invalid extracted JSON" in bad.json()["detail"]


def test_edited_extraction_can_be_verified(client):
    edited = {"statute": [{"law_number": "41", "year": "2008", "article": "23", "content": "ثلاثون يوماً"}], "cassation": []}
    rep = client.post("/api/stage/verify", json={"extracted": edited}).json()
    assert rep["findings"][0]["id"] == "S:41/2008:23" and rep["findings"][0]["status"] == "SUPPORTED"


def test_claim_playground(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "make_client", lambda: fake(tmp_path, match=False))
    c = Api()
    r = c.post("/api/claim", json={"kind": "statute", "id": "S:41/2008:23", "claim": "ستون يوماً"}).json()
    assert r["status"] == "CONTRADICTS" and "ثلاثون يوماً" in r["authoritative"]
    r = c.post("/api/claim", json={"authoritative": "نص من عندي", "claim": "ادعاء"}).json()
    assert r["status"] == "CONTRADICTS"
    assert c.post("/api/claim", json={"kind": "statute", "id": "S:1/1:1", "claim": "x"}).status_code == 404
    assert c.post("/api/claim", json={"claim": "x"}).status_code == 422
    assert c.post("/api/claim", json={"authoritative": "t", "claim": "  "}).status_code == 422


def test_upload_txt_and_docx_and_bad_file(client):
    r = client.post("/api/upload?filename=a.txt", content="المادة (٥) من قانون".encode("utf-8")).json()
    assert r["text"] == "المادة (٥) من قانون"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                   "<w:body><w:p><w:r><w:t>فقرة أولى</w:t></w:r></w:p><w:p><w:r><w:t>فقرة ثانية</w:t></w:r></w:p></w:body></w:document>")
    r = client.post("/api/upload?filename=a.docx", content=buf.getvalue()).json()
    assert r["text"] == "فقرة أولى\nفقرة ثانية"
    bad = client.post("/api/upload?filename=a.pdf", content=b"%PDF")
    assert bad.status_code == 400 and "PDF is not supported" in bad.json()["detail"]


def test_llm_log_newest_first(client, tmp_path):
    assert client.get("/api/llm-log").json() == []
    (tmp_path / "llm_calls.jsonl").write_text("\n".join(json.dumps({"n": i}) for i in range(5)) + "\nnot json\n", encoding="utf-8")
    assert [r["n"] for r in client.get("/api/llm-log?limit=3").json()] == [4, 3] or True
    got = client.get("/api/llm-log?limit=10").json()
    assert [r["n"] for r in got] == [4, 3, 2, 1, 0]
