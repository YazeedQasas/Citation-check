"""Build the held-out evaluation set (data/eval/): drafts with PLANTED errors and their gold statuses.

Every citation sentence is paired with its gold label here, so the drafts and gold.json cannot drift apart.
Statuses are relative to data/corpus/corpus.json (the synthetic seed corpus):
  SUPPORTED   real ID, correct claim          CONTRADICTS  real ID, claim says something different/opposite
  AMBIGUOUS   real ID, claim on another topic NOT_FOUND    ID not in the corpus (fabricated / near-miss)
Sentences without a label are DISTRACTORS: things that look like citations but are not (must NOT be extracted).
Phrasings deliberately differ from data/drafts/ (slash forms, no 'رقم', numbers in words, English, party submissions).
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "eval"


def g(kind, id, status, lang="ar"):
    return {"kind": kind, "id": id, "expected_status": status, "lang": lang}


DRAFTS = {
    "E01.txt": [
        ("المحكمة: بعد الاطلاع على أوراق الدعوى وسماع المرافعة، وحيث إن المدعي (المؤجر) يطلب إخلاء المأجور وبدل أجرة متأخرة، وقد تمسك بإثبات عقد الإيجار الشفهي بالبينة الشخصية.", None),
        ("ووفقاً للمادة (12) من قانون البينات رقم 77 لسنة 2011 فإن التصرفات التي تتجاوز قيمتها خمسة آلاف دينار لا تثبت إلا بالكتابة ما لم يوجد مبدأ ثبوت بالكتابة.", g("statute", "S:77/2011:12", "SUPPORTED")),
        ("وقد سبق أن صدر في النزاع نفسه قرار محكمة الاستئناف رقم (12) لسنة 2019 بإعادة الأوراق إلى محكمة البداية لاستكمال البينات.", None),
        ("وقد أكدت محكمة النقض في الطعن رقم ٨٧ لسنة ٢٠١٨ أن الإنذار الكتابي شرط لازم لإخلاء المأجور وأن علم المستأجر لا يغني عنه.", g("cassation", "C:87/2018", "SUPPORTED")),
        ("كما استند المدعي إلى المادة (99) من قانون البينات رقم (77) لسنة 2011 التي تجيز توجيه اليمين الحاسمة في أي مرحلة من مراحل الدعوى.", g("statute", "S:77/2011:99", "NOT_FOUND")),
        ("لذلك قررت المحكمة رد الدعوى وتضمين المدعي الرسوم والمصاريف.", None),
    ],
    "E02.txt": [
        ("المحكمة: بعد الاطلاع على لائحة الاستئناف والرد عليها، وحيث إن الحكم المستأنف تبلّغه المستأنف بتاريخ ٣/٣/٢٠٢٤ وقُدّم الاستئناف بتاريخ ٢٥/٤/٢٠٢٤.", None),
        ("ومن حيث الشكل، فإن المادة (٢٣) من قانون أصول المحاكمات رقم (٤١) لسنة ٢٠٠٨ تحدد مدة الاستئناف بثلاثين يوماً تلي تبليغ الحكم.", g("statute", "S:41/2008:23", "SUPPORTED")),
        ("وهذا ما أخذت به محكمة النقض (نقض حقوق ١٢٠٣/٢٠١٧) حين اعتبرت ميعاد الاستئناف حتمياً وتقضي به المحكمة من تلقاء نفسها.", g("cassation", "C:1203/2017", "SUPPORTED")),
        ("وأضاف وكيل المستأنف أن محكمة النقض قضت في قرارها رقم (1204) لسنة 2017 بجواز قبول الاستئناف المتأخر لعذر مشروع، وهو قول لا تؤيده المحكمة.", g("cassation", "C:1204/2017", "NOT_FOUND")),
        ("لذلك قررت المحكمة رد الاستئناف شكلاً.", None),
    ],
    "E03.txt": [
        ("المحكمة: بعد المداولة، وحيث إن المدعي يطالب برد مبلغ عشرين ألف دينار قيمة قرض، وأنكر المدعى عليه الدين.", None),
        ("وبموجب نص المادة 15 من قانون البينات رقم (77) لسنة 2011 يكون الإقرار القضائي حجة على المقر وحده ولا يتعدى أثره إلى غيره.", g("statute", "S:77/2011:15", "SUPPORTED")),
        ("The claimant argues that the Court of Cassation held in Decision No. 456 of 2015 that an admission made in another case is a conclusive judicial admission.", g("cassation", "C:456/2015", "CONTRADICTS", "en")),
        ("وعليه، فإن المادة (12) من قانون البينات رقم (77) لسنة 2011 تجيز إثبات الدين مهما بلغت قيمته بشهادة الشهود.", g("statute", "S:77/2011:12", "CONTRADICTS")),
        ("وقد نصت المادة (5) من عقد القرض المبرم بين الطرفين على أن يُسدَّد المبلغ على أقساط شهرية متساوية.", None),
        ("لذلك قررت المحكمة إلزام المدعى عليه بالمبلغ المطالب به.", None),
    ],
    "E04.txt": [
        ("المحكمة: بعد الاطلاع على البينات، وحيث إن المؤجر أقام الدعوى بطلب إخلاء المأجور قبل انتهاء مدة العقد.", None),
        ("تنص المادة (9) من قانون المالكين والمستأجرين رقم 15 لسنة 2015 على عدم جواز طلب الإخلاء أثناء مدة العقد إلا لإخلال جوهري يسبقه إنذار كتابي ومهلة لا تقل عن ثلاثين يوماً.", g("statute", "S:15/2015:9", "SUPPORTED")),
        ("وقد زعم المؤجر أن محكمة النقض قضت في قرارها رقم (٨٧) لسنة ٢٠١٨ بأن الإخلاء لا يحتاج إلى إنذار كتابي متى علم المستأجر بالمخالفة.", g("cassation", "C:87/2018", "CONTRADICTS")),
        ("كما أن المادة (14) من قانون المالكين والمستأجرين رقم (15) لسنة 2015 تحدد سن الأهلية للتقاضي بثماني عشرة سنة.", g("statute", "S:15/2015:14", "AMBIGUOUS")),
        ("لذلك قررت المحكمة رد الدعوى.", None),
    ],
    "E05.txt": [
        ("المحكمة: بعد الاطلاع على لوائح الدعوى، وحيث إن المدعية تطالب بثمن بضاعة وردتها قبل سبع سنوات، ودفع المدعى عليه بالتقادم.", None),
        ("وقد تم تسجيل هذه الدعوى برقم (445) لسنة 2023 أمام محكمة البداية الحقوقية.", None),
        ("والمادة (40) من قانون التجارة (63 لسنة 2009) تقرر تقادم الدعاوى التجارية بمضي خمس سنوات.", g("statute", "S:63/2009:40", "SUPPORTED")),
        ("وقررت محكمة النقض بقرارها رقم (349) لسنة 2020 أن المطالبة الودية لا تقطع التقادم التجاري.", g("cassation", "C:349/2020", "SUPPORTED")),
        ("وفي القرار رقم (2210) لسنة 2019 قررت محكمة النقض أن الفوائد التأخيرية لا تتجاوز السعر القانوني.", g("cassation", "C:2210/2019", "AMBIGUOUS")),
        ("لذلك قررت المحكمة رد الدعوى لتقادمها.", None),
    ],
    "E06.txt": [
        ("المحكمة: بعد المداولة قانوناً، وحيث إن الطرفين تبادلا الدفوع بشأن الميعاد والتقادم.", None),
        ("وتنص المادة (23) من قانون أصول المحاكمات رقم (41) لسنة 2008 على أن ميعاد الاستئناف ستون يوماً من تاريخ التبليغ.", g("statute", "S:41/2008:23", "CONTRADICTS")),
        ("وعملاً بالمادة (٤٠) من قانون التجارة رقم (٦٣) لسنة ٢٠٠٩ تتقادم الدعاوى التجارية بمرور عشر سنوات.", g("statute", "S:63/2009:40", "CONTRADICTS")),
        ("كما تحدد المادة 15 من قانون البينات رقم 77 لسنة 2011 رسوم الاستئناف المستحقة على المستأنف.", g("statute", "S:77/2011:15", "AMBIGUOUS")),
        ("In Cassation Decision No. 912 of 2014 the Court held that arbitrary dismissal entitles the worker to compensation even under an open-ended contract.", g("cassation", "C:912/2014", "SUPPORTED", "en")),
        ("لذلك قررت المحكمة ما يلي.", None),
    ],
    "E07.txt": [
        ("المحكمة: بعد الاطلاع على أوراق الدعوى العمالية، وحيث إن العامل يطالب بالتعويض عن إنهاء عقد عمله.", None),
        ("The employer relied on Article 31 of the Labour Law No. 8 of 2013, which requires thirty days' written notice before terminating an open-ended contract.", g("statute", "S:8/2013:31", "SUPPORTED", "en")),
        ("ثم أضاف أن المادة (32) من القانون ذاته تجيز الفصل الفوري في أي حال ودون أي إشعار.", g("statute", "S:8/2013:32", "NOT_FOUND")),
        ("He also cited Cassation Decision No. 7788 of 2022, which held that electronic signatures are binding on the parties.", g("cassation", "C:7788/2022", "NOT_FOUND", "en")),
        ("والمادة الخامسة عشرة من قانون البينات رقم (77) لسنة 2011 تقرر أن الإقرار القضائي حجة قاطعة على المقر.", g("statute", "S:77/2011:15", "SUPPORTED")),
        ("لذلك قررت المحكمة الحكم للعامل بالتعويض.", None),
    ],
    "E08.txt": [
        ("المحكمة: بعد الاطلاع على لائحة الدعوى وبيّنات الطرفين، وحيث إن النزاع يدور حول إخلاء مأجور تجاري.", None),
        ("كما استند المدعي إلى المادة (5) من قانون المنافسة رقم (22) لسنة 2017 التي تمنع الاحتكار في السوق.", g("statute", "S:22/2017:5", "NOT_FOUND")),
        ("ووفقاً للمادة (9) من قانون المالكين والمستأجرين رقم (15) لسنة 2015 يجوز للمؤجر طلب الإخلاء في أي وقت ودون إنذار.", g("statute", "S:15/2015:9", "CONTRADICTS")),
        ("Cassation Appeal No. 349 of 2020 confirmed the minimum wage for domestic workers.", g("cassation", "C:349/2020", "AMBIGUOUS", "en")),
        ("وفي قرارها رقم (1203) لسنة 2017 اعتبرت محكمة النقض ميعاد الاستئناف حتمياً يسقط الحق في الطعن بفواته.", g("cassation", "C:1203/2017", "SUPPORTED")),
        ("لذلك قررت المحكمة رد الدعوى.", None),
    ],
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    gold = {"_note": "Held-out evaluation set with planted errors, built by scripts/build_eval_set.py. Do not tune prompts/regex on it without re-measuring on fresh drafts."}
    for name, paras in DRAFTS.items():
        (OUT / name).write_text("\n\n".join(t for t, _ in paras) + "\n", encoding="utf-8")
        gold[name] = [lab for _, lab in paras if lab]
        ids = [(l["kind"], l["id"]) for l in gold[name]]
        assert len(ids) == len(set(ids)), f"{name}: duplicate gold ID (one status per ID per draft)"
    (OUT / "gold.json").write_text(json.dumps(gold, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    n = sum(len(v) for k, v in gold.items() if not k.startswith("_"))
    print(f"wrote {len(DRAFTS)} drafts, {n} gold citations -> {OUT}")


if __name__ == "__main__":
    main()
