from citation_check import config
from citation_check.extraction.loader import load_draft
from citation_check.extraction.patterns import find_cassation_candidates, find_statute_candidates
from citation_check.schema import build_cassation_id, build_statute_id


def stat_ids(text):
    return [build_statute_id(c.fields["law_number"], c.fields["year"], c.fields["article"]) for c in find_statute_candidates(text)]


def cass_ids(text):
    return [build_cassation_id(c.fields["appeal_number"], c.fields["year"]) for c in find_cassation_candidates(text)]


def test_arabic_statute_variants():
    assert stat_ids("عملاً بأحكام المادة (9) من قانون رقم (15) لسنة 2015") == ["S:15/2015:9"]
    assert stat_ids("استناداً إلى نص المادة (٢٣) فقرة (٢) من قانون أصول المحاكمات رقم (٤١) لسنة ٢٠٠٨") == ["S:41/2008:23"]
    assert stat_ids("وفق المادة (۱٥) من قانون رقم (۷۷) لسنة ۲۰۱۱") == ["S:77/2011:15"]
    assert stat_ids("المادة (٢٣ مكرر) من القانون رقم (٤١) لسنة ٢٠٠٨") == ["S:41/2008:23bis"]


def test_plural_articles_and_same_law():
    t = "عملاً بالمادة (٥٥) من قانون الشركات رقم (٢٢) لسنة ٢٠٠٦. وسنداً للمادتين (٥٦) و(٥٦ مكرر) من القانون ذاته."
    assert stat_ids(t) == ["S:22/2006:55", "S:22/2006:56", "S:22/2006:56bis"]


def test_same_law_with_cassation_in_between():
    t = ("المادة (۳۱) من قانون رقم (۸) لسنة ۲۰۱۳ لا يجوز. وقد استقر قضاء محكمة النقض في القرار رقم (۹۱۲) لسنة ۲۰۱۴. "
         "كما يستحق أجر العمل الإضافي عملاً بأحكام المادة (۷۷) من القانون ذاته.")
    assert stat_ids(t) == ["S:8/2013:31", "S:8/2013:77"]


def test_english_statutes():
    assert stat_ids("pursuant to Article (40) of Commercial Law No. (63) of 2009, which") == ["S:63/2009:40"]
    assert stat_ids("Article 31 bis of Labour Law No. 8 of 2013 requires") == ["S:8/2013:31bis"]
    assert stat_ids("Article 14 of Insurance Law No. 9 of 2004 and Article 15 of the same law") == ["S:9/2004:14", "S:9/2004:15"]


def test_article_in_words():
    assert stat_ids("سنداً إلى المادة الثالثة والعشرين مكرراً من القانون رقم (٤١) لسنة ٢٠٠٨") == ["S:41/2008:23bis"]


def test_no_false_statute_without_law_reference():
    assert stat_ids("وحيث إن المادة (5) من العقد تنص على شروط الدفع") == []


def test_cassation_variants():
    assert cass_ids("وهو ما استقر عليه اجتهاد محكمة النقض في قرارها رقم (87) لسنة 2018 الصادر بتاريخ 20/2/2018") == ["C:87/2018"]
    assert cass_ids("وفي ذلك قضت محكمة النقض بأن كذا (نقض حقوق رقم ١٢٠٣ لسنة ٢٠١٧)") == ["C:1203/2017"]
    assert cass_ids("The Court of Cassation held in Decision No. 118/2012 dated 3 May 2012") == ["C:118/2012"]
    assert cass_ids("she relied on Cassation Appeal No. 349 of 2020 on the basis") == ["C:349/2020"]


def test_cassation_context_after_the_number():
    assert cass_ids("وفي القرار رقم (2210) لسنة 2019 قررت محكمة النقض أن الفوائد لا تتجاوز السعر القانوني") == ["C:2210/2019"]
    # a bare case number is not a citation even if the Court of Cassation is mentioned nearby
    assert cass_ids("وقد تم تسجيل هذه الدعوى برقم (445) لسنة 2023 أمام محكمة النقض") == []
    assert cass_ids("الدعوى رقم (445) لسنة 2023 المنظورة أمام محكمة البداية") == []


def test_cassation_ignores_other_courts_and_laws():
    assert cass_ids("وبعد الاطلاع على قرار محكمة الاستئناف رقم (٣٣) لسنة ٢٠١٨، وحيث استقر قضاء محكمة النقض على أن البينة") == []
    assert cass_ids("المادة (9) من قانون رقم (15) لسنة 2015 وقد قضت محكمة النقض") == []


def test_sample_drafts_recall_and_precision_of_the_safety_net():
    import json
    gold = json.loads((config.DRAFTS_DIR / "gold.json").read_text(encoding="utf-8"))
    found = missed = extra = 0
    for name, items in gold.items():
        if name.startswith("_"):
            continue
        d = load_draft(config.DRAFTS_DIR / name)
        got = set(stat_ids(d.text)) | set(cass_ids(d.text))
        want = {i["id"] for i in items}
        found += len(got & want); missed += len(want - got); extra += len(got - want)
    assert extra == 0, "regex net must not invent citations"
    assert found >= 20, (found, missed)   # of 22; the rest is left to the LLM
